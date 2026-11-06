import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.app.core.security import hash_password
from src.app.models.contract import Contract
from src.app.models.destination import Destination
from src.app.models.enums import (
    AccountType,
    ContractStatus,
    EnrollmentSource,
    EnrollmentStatus,
    OrganizationStatus,
    OrgRole,
    UserStatus,
)
from src.app.models.mobility import Mobility
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User
from src.app.schemas.organization import OrganizationSummary
from src.app.schemas.platform_admin import (
    CountsByStatus,
    ManagedMobility,
    ManagedUserCreate,
    ManagedUserDetail,
    ManagedUserRead,
    ManagedUserUpdate,
    PlatformOverview,
    PremiumCounts,
    PremiumGrantCreate,
    PremiumGrantRead,
    UserCounts,
)
from src.app.schemas.user import PremiumRead
from src.app.services import (
    account_service,
    audit_service,
    auth_service,
    entitlements,
    organization_service,
    premium_service,
    user_service,
)
from src.app.services.audit_service import RequestMeta


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return user


async def _get_manageable_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await _get_user(db, user_id)
    if user.account_type == AccountType.PLATFORM_ADMIN:
        raise ForbiddenError("Platform admins are managed with the CLI")
    return user


async def _organization_contexts(
    db: AsyncSession, users: list[User]
) -> dict[uuid.UUID, tuple[Organization, OrgRole | None]]:
    contexts: dict[uuid.UUID, tuple[Organization, OrgRole | None]] = {}
    staff_ids = [u.id for u in users if u.account_type == AccountType.ORG_STAFF]
    student_ids = [u.id for u in users if u.account_type == AccountType.STUDENT]
    if staff_ids:
        rows = await db.execute(
            select(OrganizationMember.user_id, OrganizationMember.org_role, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id.in_(staff_ids), OrganizationMember.is_active)
        )
        for user_id, org_role, organization in rows.all():
            contexts[user_id] = (organization, org_role)
    if student_ids:
        rows = await db.execute(
            select(StudentEnrollment.student_id, Organization)
            .join(Organization, Organization.id == StudentEnrollment.organization_id)
            .where(
                StudentEnrollment.student_id.in_(student_ids),
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        for user_id, organization in rows.all():
            contexts[user_id] = (organization, None)
    return contexts


def _managed_fields(
    user: User,
    context: tuple[Organization, OrgRole | None] | None,
    premium: entitlements.Entitlement,
) -> dict:
    organization, org_role = context or (None, None)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "account_type": user.account_type,
        "status": user.status,
        "org_role": org_role,
        "organization": OrganizationSummary.model_validate(organization) if organization else None,
        "premium": PremiumRead(active=premium.active, source=premium.source, until=premium.until),
        "mfa_enabled": user.mfa_enabled,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


async def list_users(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    q: str | None = None,
    account_type: AccountType | None = None,
    status: UserStatus | None = None,
    organization_id: uuid.UUID | None = None,
) -> tuple[list[ManagedUserRead], int]:
    filters = []
    if q:
        pattern = f"%{q}%"
        filters.append(or_(User.email.ilike(pattern), User.name.ilike(pattern)))
    if account_type:
        filters.append(User.account_type == account_type)
    if status:
        filters.append(User.status == status)
    if organization_id:
        members = select(OrganizationMember.user_id).where(
            OrganizationMember.organization_id == organization_id
        )
        students = select(StudentEnrollment.student_id).where(
            StudentEnrollment.organization_id == organization_id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
        )
        filters.append(or_(User.id.in_(members), User.id.in_(students)))

    total = await db.scalar(select(func.count(User.id)).where(*filters))
    users = list(
        await db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    contexts = await _organization_contexts(db, users)
    premiums = await entitlements.premium_for_users(db, [u.id for u in users])
    return [
        ManagedUserRead(**_managed_fields(u, contexts.get(u.id), premiums[u.id])) for u in users
    ], total or 0


async def get_user_detail(db: AsyncSession, user_id: uuid.UUID) -> ManagedUserDetail:
    user = await _get_user(db, user_id)
    contexts = await _organization_contexts(db, [user])
    rows = await db.execute(
        select(Mobility, Destination)
        .join(Destination, Destination.id == Mobility.destination_id)
        .where(Mobility.user_id == user.id)
        .order_by(Mobility.departure_date.desc())
    )
    mobilities = [
        ManagedMobility(
            id=mobility.id,
            type=mobility.type,
            status=mobility.status,
            departure_date=mobility.departure_date,
            return_date=mobility.return_date,
            city=destination.city,
            country=destination.country,
        )
        for mobility, destination in rows.all()
    ]
    return ManagedUserDetail(
        **_managed_fields(user, contexts.get(user.id), await entitlements.premium_for(db, user.id)),
        premium_grants=await premium_service.list_grants(db, user.id),
        phone=user.phone,
        suspended_at=user.suspended_at,
        suspended_reason=user.suspended_reason,
        deletion_scheduled_at=user.deletion_scheduled_at,
        mobilities=mobilities,
    )


async def create_user(
    db: AsyncSession, actor: User, payload: ManagedUserCreate, meta: RequestMeta
) -> ManagedUserDetail:
    user = await user_service.create_account(db, payload.email, payload.name, payload.account_type)
    if payload.account_type == AccountType.ORG_STAFF:
        organization = await organization_service.get_organization(
            db, payload.organization_id, lock=True
        )
        if organization.status == OrganizationStatus.ARCHIVED:
            raise ConflictError("This organization is archived", code="ORGANIZATION_ARCHIVED")
        db.add(
            OrganizationMember(
                organization_id=organization.id, user_id=user.id, org_role=payload.org_role
            )
        )
    elif payload.organization_id:
        await organization_service.enroll_student(
            db, actor, payload.organization_id, user.id, EnrollmentSource.ADMIN, meta, commit=False
        )

    audit_service.record(
        db,
        actor=actor,
        action="user.create",
        target_type="user",
        target_id=user.id,
        organization_id=payload.organization_id,
        changes={
            "account_type": payload.account_type.value,
            "org_role": payload.org_role.value if payload.org_role else None,
        },
        meta=meta,
    )
    await db.commit()
    await auth_service.send_password_setup(user)
    return await get_user_detail(db, user.id)


async def update_user(
    db: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    payload: ManagedUserUpdate,
    meta: RequestMeta,
) -> ManagedUserDetail:
    user = await _get_manageable_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("email") and data["email"] != user.email:
        if await db.scalar(select(User.id).where(User.email == data["email"])):
            raise ConflictError("An account with this email already exists", code="EMAIL_TAKEN")

    changed = []
    for field, value in data.items():
        if value is None and field != "phone":
            continue
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed.append(field)
    if changed:
        audit_service.record(
            db,
            actor=actor,
            action="user.update",
            target_type="user",
            target_id=user.id,
            changes={"fields": sorted(changed)},
            meta=meta,
        )
    await db.commit()
    return await get_user_detail(db, user.id)


async def suspend_user(
    db: AsyncSession, actor: User, user_id: uuid.UUID, reason: str, meta: RequestMeta
) -> ManagedUserDetail:
    user = await _get_manageable_user(db, user_id)
    if user.status != UserStatus.ACTIVE:
        raise ConflictError("Only an active account can be suspended", code="INVALID_STATUS")

    user.status = UserStatus.SUSPENDED
    user.suspended_at = datetime.now(UTC)
    user.suspended_reason = reason
    await auth_service.revoke_all_sessions(user)
    audit_service.record(
        db,
        actor=actor,
        action="user.suspend",
        target_type="user",
        target_id=user.id,
        changes={"status": [UserStatus.ACTIVE.value, UserStatus.SUSPENDED.value]},
        meta=meta,
    )
    await db.commit()
    return await get_user_detail(db, user.id)


async def reactivate_user(
    db: AsyncSession, actor: User, user_id: uuid.UUID, meta: RequestMeta
) -> ManagedUserDetail:
    user = await _get_manageable_user(db, user_id)
    previous = user.status
    if previous == UserStatus.ACTIVE:
        raise ConflictError("This account is already active", code="INVALID_STATUS")

    user.status = UserStatus.ACTIVE
    user.suspended_at = None
    user.suspended_reason = None
    user.deletion_scheduled_at = None
    audit_service.record(
        db,
        actor=actor,
        action="user.reactivate",
        target_type="user",
        target_id=user.id,
        changes={"status": [previous.value, UserStatus.ACTIVE.value]},
        meta=meta,
    )
    await db.commit()
    return await get_user_detail(db, user.id)


async def schedule_deletion(
    db: AsyncSession, actor: User, user_id: uuid.UUID, meta: RequestMeta
) -> ManagedUserDetail:
    user = await _get_manageable_user(db, user_id)
    await account_service.schedule_deletion(db, actor, user, meta)
    return await get_user_detail(db, user.id)


async def grant_premium(
    db: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    payload: PremiumGrantCreate,
    meta: RequestMeta,
) -> PremiumGrantRead:
    user = await _get_manageable_user(db, user_id)
    return await premium_service.grant(db, actor, user, payload, meta)


async def revoke_premium(
    db: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    grant_id: uuid.UUID,
    reason: str,
    meta: RequestMeta,
) -> PremiumGrantRead:
    await _get_manageable_user(db, user_id)
    return await premium_service.revoke(db, actor, user_id, grant_id, reason, meta)


async def overview(db: AsyncSession) -> PlatformOverview:
    by_type = dict(
        (
            await db.execute(select(User.account_type, func.count()).group_by(User.account_type))
        ).all()
    )
    by_user_status = dict(
        (await db.execute(select(User.status, func.count()).group_by(User.status))).all()
    )
    by_org_status = dict(
        (
            await db.execute(
                select(Organization.status, func.count()).group_by(Organization.status)
            )
        ).all()
    )
    by_contract_status = dict(
        (await db.execute(select(Contract.status, func.count()).group_by(Contract.status))).all()
    )
    grants = await premium_service.active_grant_counts(db)
    return PlatformOverview(
        contracts=CountsByStatus(
            total=sum(by_contract_status.values()),
            by_status={s.value: by_contract_status.get(s, 0) for s in ContractStatus},
        ),
        active_premium_grants=PremiumCounts(**grants),
        users=UserCounts(
            total=sum(by_type.values()),
            by_account_type={t.value: by_type.get(t, 0) for t in AccountType},
            by_status={s.value: by_user_status.get(s, 0) for s in UserStatus},
        ),
        organizations=CountsByStatus(
            total=sum(by_org_status.values()),
            by_status={s.value: by_org_status.get(s, 0) for s in OrganizationStatus},
        ),
    )


async def find_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def grant_platform_admin(
    db: AsyncSession, email: str, name: str | None = None, password: str | None = None
) -> tuple[User, bool]:
    user = await find_by_email(db, email)
    if user and user.account_type == AccountType.PLATFORM_ADMIN:
        return user, False

    if user is None:
        if not password:
            raise ConflictError("A password is required to create a platform admin")
        user = await user_service.create_account(
            db, email, name or email.split("@")[0], AccountType.PLATFORM_ADMIN
        )
        user.password_hash = hash_password(password)
        user.email_verified = True
    else:
        if user.account_type == AccountType.ORG_STAFF and await db.scalar(
            select(OrganizationMember.id).where(OrganizationMember.user_id == user.id)
        ):
            raise ConflictError("This account is an organization member: remove it first")
        if user.account_type == AccountType.STUDENT and (
            await db.scalar(select(Mobility.id).where(Mobility.user_id == user.id).limit(1))
            or await db.scalar(
                select(StudentEnrollment.id).where(
                    StudentEnrollment.student_id == user.id,
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
        ):
            raise ConflictError(
                "This student account has mobilities or an organization: use another email"
            )
        user.account_type = AccountType.PLATFORM_ADMIN
        await auth_service.revoke_all_sessions(user)

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    await db.flush()
    audit_service.record(
        db,
        actor=None,
        action="platform_admin.grant",
        target_type="user",
        target_id=user.id,
        changes={"account_type": AccountType.PLATFORM_ADMIN.value},
    )
    await db.commit()
    return user, True


async def revoke_platform_admin(db: AsyncSession, email: str) -> User:
    user = await find_by_email(db, email)
    if not user or user.account_type != AccountType.PLATFORM_ADMIN:
        raise NotFoundError("No platform admin with this email")

    user.account_type = AccountType.STUDENT
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    await auth_service.revoke_all_sessions(user)
    audit_service.record(
        db,
        actor=None,
        action="platform_admin.revoke",
        target_type="user",
        target_id=user.id,
        changes={"account_type": [AccountType.PLATFORM_ADMIN.value, AccountType.STUDENT.value]},
    )
    await db.commit()
    return user
