import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, NotFoundError
from src.app.models.enums import (
    AccountType,
    EnrollmentSource,
    EnrollmentStatus,
    OrganizationStatus,
    OrgRole,
)
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User
from src.app.schemas.org import OrgSettingsUpdate
from src.app.schemas.platform_admin import (
    ArchiveResult,
    EnrollmentRead,
    MemberCreate,
    MemberRead,
    MemberUpdate,
    OrganizationAdminRead,
    OrganizationCreate,
    OrganizationUpdate,
)
from src.app.services import audit_service, auth_service, contract_service, user_service
from src.app.services.audit_service import RequestMeta

_JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 10


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")[:100]


def generate_join_code() -> str:
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


async def get_organization(
    db: AsyncSession, organization_id: uuid.UUID, *, lock: bool = False
) -> Organization:
    query = select(Organization).where(Organization.id == organization_id)
    if lock:
        query = query.with_for_update()
    organization = await db.scalar(query)
    if not organization:
        raise NotFoundError("Organization not found")
    return organization


async def _available_slug(db: AsyncSession, base: str, exclude_id: uuid.UUID | None = None) -> str:
    base = base or "organization"
    slug, suffix = base, 2
    while await db.scalar(
        select(Organization.id).where(Organization.slug == slug, Organization.id != exclude_id)
    ):
        slug, suffix = f"{base[:95]}-{suffix}", suffix + 1
    return slug


async def _counts(db: AsyncSession, organization_ids: list[uuid.UUID]) -> dict:
    members = dict(
        (
            await db.execute(
                select(OrganizationMember.organization_id, func.count())
                .where(
                    OrganizationMember.organization_id.in_(organization_ids),
                    OrganizationMember.is_active,
                )
                .group_by(OrganizationMember.organization_id)
            )
        ).all()
    )
    students = dict(
        (
            await db.execute(
                select(StudentEnrollment.organization_id, func.count())
                .where(
                    StudentEnrollment.organization_id.in_(organization_ids),
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
                .group_by(StudentEnrollment.organization_id)
            )
        ).all()
    )
    return {"members": members, "students": students}


def _to_read(organization: Organization, counts: dict) -> OrganizationAdminRead:
    read = OrganizationAdminRead.model_validate(organization)
    read.member_count = counts["members"].get(organization.id, 0)
    read.active_student_count = counts["students"].get(organization.id, 0)
    return read


async def read_organization(db: AsyncSession, organization_id: uuid.UUID) -> OrganizationAdminRead:
    organization = await get_organization(db, organization_id)
    return _to_read(organization, await _counts(db, [organization.id]))


async def list_organizations(
    db: AsyncSession,
    *,
    page: int,
    per_page: int,
    q: str | None = None,
    status: OrganizationStatus | None = None,
) -> tuple[list[OrganizationAdminRead], int]:
    filters = []
    if q:
        pattern = f"%{q}%"
        filters.append(or_(Organization.name.ilike(pattern), Organization.slug.ilike(pattern)))
    if status:
        filters.append(Organization.status == status)

    total = await db.scalar(select(func.count(Organization.id)).where(*filters))
    organizations = list(
        await db.scalars(
            select(Organization)
            .where(*filters)
            .order_by(Organization.name, Organization.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    counts = await _counts(db, [o.id for o in organizations])
    return [_to_read(o, counts) for o in organizations], total or 0


async def create_organization(
    db: AsyncSession, actor: User, payload: OrganizationCreate, meta: RequestMeta
) -> OrganizationAdminRead:
    manager = await user_service.create_account(
        db, payload.manager.email, payload.manager.name, AccountType.ORG_STAFF
    )
    organization = Organization(
        name=payload.name,
        slug=await _available_slug(db, payload.slug or slugify(payload.name)),
        logo_url=payload.logo_url,
        branding=payload.branding,
        settings=payload.settings,
        join_code=generate_join_code(),
        created_by=actor.id,
    )
    db.add(organization)
    await db.flush()
    member = OrganizationMember(
        organization_id=organization.id, user_id=manager.id, org_role=OrgRole.MANAGER
    )
    db.add(member)
    await db.flush()
    audit_service.record(
        db,
        actor=actor,
        action="organization.create",
        target_type="organization",
        target_id=organization.id,
        organization_id=organization.id,
        changes={"slug": organization.slug, "manager_user_id": str(manager.id)},
        meta=meta,
    )
    await db.commit()
    await auth_service.send_password_setup(manager)
    return await read_organization(db, organization.id)


async def update_organization(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    payload: OrganizationUpdate | OrgSettingsUpdate,
    meta: RequestMeta,
) -> OrganizationAdminRead:
    organization = await get_organization(db, organization_id, lock=True)
    data = payload.model_dump(exclude_unset=True)
    if data.get("slug"):
        if await _available_slug(db, data["slug"], exclude_id=organization.id) != data["slug"]:
            raise ConflictError("This slug is already used", code="SLUG_TAKEN")

    changes = {}
    for field, value in data.items():
        if value is None and field in ("name", "slug", "branding", "settings"):
            continue
        if getattr(organization, field) != value:
            changes[field] = [getattr(organization, field), value]
            setattr(organization, field, value)
    if changes:
        audit_service.record(
            db,
            actor=actor,
            action="organization.update",
            target_type="organization",
            target_id=organization.id,
            organization_id=organization.id,
            changes=changes,
            meta=meta,
        )
    await db.commit()
    return await read_organization(db, organization.id)


async def _active_manager_count(
    db: AsyncSession, organization_id: uuid.UUID, excluding_member_id: uuid.UUID | None = None
) -> int:
    filters = [
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.org_role == OrgRole.MANAGER,
        OrganizationMember.is_active,
    ]
    if excluding_member_id:
        filters.append(OrganizationMember.id != excluding_member_id)
    return await db.scalar(select(func.count(OrganizationMember.id)).where(*filters)) or 0


async def ensure_another_active_manager(
    db: AsyncSession, organization: Organization, member: OrganizationMember
) -> None:
    if (
        organization.status != OrganizationStatus.ACTIVE
        or member.org_role != OrgRole.MANAGER
        or not member.is_active
    ):
        return
    if await _active_manager_count(db, organization.id, excluding_member_id=member.id) == 0:
        raise ConflictError(
            "An active organization needs at least one active manager: appoint another first",
            code="LAST_MANAGER",
        )


async def set_status(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    new_status: OrganizationStatus,
    meta: RequestMeta,
) -> OrganizationAdminRead:
    organization = await get_organization(db, organization_id, lock=True)
    previous = organization.status
    if previous == new_status:
        return await read_organization(db, organization.id)
    if (
        new_status == OrganizationStatus.ACTIVE
        and await _active_manager_count(db, organization.id) == 0
    ):
        raise ConflictError(
            "Reactivate or appoint a manager before reactivating the organization",
            code="LAST_MANAGER",
        )

    organization.status = new_status
    action = (
        "organization.reactivate"
        if new_status == OrganizationStatus.ACTIVE
        else "organization.suspend"
    )
    audit_service.record(
        db,
        actor=actor,
        action=action,
        target_type="organization",
        target_id=organization.id,
        organization_id=organization.id,
        changes={"status": [previous.value, new_status.value]},
        meta=meta,
    )
    await db.commit()
    return await read_organization(db, organization.id)


async def archive_organization(
    db: AsyncSession, actor: User, organization_id: uuid.UUID, meta: RequestMeta
) -> ArchiveResult:
    organization = await get_organization(db, organization_id, lock=True)
    if organization.status == OrganizationStatus.ARCHIVED:
        raise ConflictError("This organization is already archived")
    previous = organization.status
    now = datetime.now(UTC)

    enrollments = list(
        await db.scalars(
            select(StudentEnrollment).where(
                StudentEnrollment.organization_id == organization.id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
    )
    for enrollment in enrollments:
        enrollment.status = EnrollmentStatus.REVOKED
        enrollment.ended_at = now
        enrollment.ended_by = actor.id

    rows = (
        await db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == organization.id,
                OrganizationMember.is_active,
            )
        )
    ).all()
    for member, user in rows:
        member.is_active = False
        await auth_service.revoke_all_sessions(user)

    organization.status = OrganizationStatus.ARCHIVED
    audit_service.record(
        db,
        actor=actor,
        action="organization.archive",
        target_type="organization",
        target_id=organization.id,
        organization_id=organization.id,
        changes={
            "status": [previous.value, OrganizationStatus.ARCHIVED.value],
            "revoked_enrollments": len(enrollments),
            "deactivated_member_ids": [str(member.id) for member, _ in rows],
        },
        meta=meta,
    )
    await db.commit()
    return ArchiveResult(
        organization=await read_organization(db, organization.id),
        deactivated_members=[_member_read(member, user) for member, user in rows],
    )


def _member_read(member: OrganizationMember, user: User) -> MemberRead:
    return MemberRead(
        id=member.id,
        user_id=user.id,
        email=user.email,
        name=user.name,
        org_role=member.org_role,
        is_active=member.is_active,
        user_status=user.status,
        created_at=member.created_at,
    )


async def list_members(db: AsyncSession, organization_id: uuid.UUID) -> list[MemberRead]:
    await get_organization(db, organization_id)
    rows = (
        await db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.org_role, User.name)
        )
    ).all()
    return [_member_read(member, user) for member, user in rows]


async def _get_member(
    db: AsyncSession, organization_id: uuid.UUID, member_id: uuid.UUID
) -> tuple[OrganizationMember, User]:
    row = (
        await db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.id == member_id,
                OrganizationMember.organization_id == organization_id,
            )
        )
    ).first()
    if not row:
        raise NotFoundError("Member not found")
    return row[0], row[1]


async def add_member(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    payload: MemberCreate,
    meta: RequestMeta,
) -> MemberRead:
    organization = await get_organization(db, organization_id, lock=True)
    if organization.status == OrganizationStatus.ARCHIVED:
        raise ConflictError("This organization is archived", code="ORGANIZATION_ARCHIVED")

    user = await db.scalar(select(User).where(User.email == payload.email))
    created = user is None
    if created:
        user = await user_service.create_account(
            db, payload.email, payload.name, AccountType.ORG_STAFF
        )
    elif user.account_type != AccountType.ORG_STAFF or await db.scalar(
        select(OrganizationMember.id).where(OrganizationMember.user_id == user.id)
    ):
        raise ConflictError("This email already belongs to another account", code="ACCOUNT_EXISTS")

    member = OrganizationMember(
        organization_id=organization.id, user_id=user.id, org_role=payload.org_role
    )
    db.add(member)
    await db.flush()
    await auth_service.revoke_all_sessions(user)
    audit_service.record(
        db,
        actor=actor,
        action="member.create",
        target_type="member",
        target_id=member.id,
        organization_id=organization.id,
        changes={"user_id": str(user.id), "org_role": payload.org_role.value},
        meta=meta,
    )
    await db.commit()
    if created:
        await auth_service.send_password_setup(user)
    await db.refresh(member)
    return _member_read(member, user)


async def update_member(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberUpdate,
    meta: RequestMeta,
) -> MemberRead:
    organization = await get_organization(db, organization_id, lock=True)
    member, user = await _get_member(db, organization.id, member_id)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)

    demoted = data.get("org_role", member.org_role) != OrgRole.MANAGER
    deactivated = data.get("is_active", member.is_active) is False
    if demoted or deactivated:
        await ensure_another_active_manager(db, organization, member)

    changes = {}
    for field, value in data.items():
        previous = getattr(member, field)
        if previous != value:
            changes[field] = [
                previous.value if isinstance(previous, OrgRole) else previous,
                value.value if isinstance(value, OrgRole) else value,
            ]
            setattr(member, field, value)
    if changes:
        await auth_service.revoke_all_sessions(user)
        audit_service.record(
            db,
            actor=actor,
            action="member.update",
            target_type="member",
            target_id=member.id,
            organization_id=organization.id,
            changes=changes,
            meta=meta,
        )
    await db.commit()
    await db.refresh(member)
    return _member_read(member, user)


async def remove_member(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    organization = await get_organization(db, organization_id, lock=True)
    member, user = await _get_member(db, organization.id, member_id)
    await ensure_another_active_manager(db, organization, member)

    await db.delete(member)
    await auth_service.revoke_all_sessions(user)
    audit_service.record(
        db,
        actor=actor,
        action="member.remove",
        target_type="member",
        target_id=member.id,
        organization_id=organization.id,
        changes={"user_id": str(user.id), "org_role": member.org_role.value},
        meta=meta,
    )
    await db.commit()


def _enrollment_read(enrollment: StudentEnrollment, student: User) -> EnrollmentRead:
    return EnrollmentRead(
        id=enrollment.id,
        student_id=student.id,
        email=student.email,
        name=student.name,
        status=enrollment.status,
        source=enrollment.source,
        joined_at=enrollment.joined_at,
        ended_at=enrollment.ended_at,
    )


async def list_enrollments(
    db: AsyncSession, organization_id: uuid.UUID, status: EnrollmentStatus | None
) -> list[EnrollmentRead]:
    await get_organization(db, organization_id)
    filters = [StudentEnrollment.organization_id == organization_id]
    if status:
        filters.append(StudentEnrollment.status == status)
    rows = (
        await db.execute(
            select(StudentEnrollment, User)
            .join(User, User.id == StudentEnrollment.student_id)
            .where(*filters)
            .order_by(StudentEnrollment.joined_at.desc())
        )
    ).all()
    return [_enrollment_read(enrollment, student) for enrollment, student in rows]


async def enroll_student(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    student_id: uuid.UUID,
    source: EnrollmentSource,
    meta: RequestMeta,
    *,
    commit: bool = True,
) -> EnrollmentRead:
    organization = await get_organization(db, organization_id, lock=True)
    if organization.status != OrganizationStatus.ACTIVE:
        raise ConflictError(
            "Students can only join an active organization", code="ORGANIZATION_INACTIVE"
        )
    student = await db.get(User, student_id)
    if not student:
        raise NotFoundError("Student not found")
    if student.account_type != AccountType.STUDENT:
        raise ConflictError("Only a student account can be enrolled", code="NOT_A_STUDENT")
    if await db.scalar(
        select(StudentEnrollment.id).where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    ):
        raise ConflictError(
            "This student already belongs to an organization", code="ALREADY_ENROLLED"
        )
    await contract_service.ensure_can_enroll(db, organization.id)

    enrollment = StudentEnrollment(
        organization_id=organization.id, student_id=student.id, source=source
    )
    db.add(enrollment)
    await db.flush()
    audit_service.record(
        db,
        actor=actor,
        action="enrollment.create",
        target_type="enrollment",
        target_id=enrollment.id,
        organization_id=organization.id,
        changes={"student_id": str(student.id), "source": source.value},
        meta=meta,
    )
    if commit:
        await db.commit()
        await db.refresh(enrollment)
    return _enrollment_read(enrollment, student)


async def revoke_enrollment(
    db: AsyncSession,
    actor: User,
    organization_id: uuid.UUID,
    student_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    await get_organization(db, organization_id)
    enrollment = await db.scalar(
        select(StudentEnrollment).where(
            StudentEnrollment.organization_id == organization_id,
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if not enrollment:
        raise NotFoundError("Enrollment not found")

    enrollment.status = EnrollmentStatus.REVOKED
    enrollment.ended_at = datetime.now(UTC)
    enrollment.ended_by = actor.id
    audit_service.record(
        db,
        actor=actor,
        action="enrollment.revoke",
        target_type="enrollment",
        target_id=enrollment.id,
        organization_id=organization_id,
        changes={"student_id": str(student_id), "status": ["active", "revoked"]},
        meta=meta,
    )
    await db.commit()


async def rotate_join_code(
    db: AsyncSession, actor: User, organization_id: uuid.UUID, meta: RequestMeta
) -> str:
    organization = await get_organization(db, organization_id, lock=True)
    organization.join_code = generate_join_code()
    audit_service.record(
        db,
        actor=actor,
        action="organization.rotate_join_code",
        target_type="organization",
        target_id=organization.id,
        organization_id=organization.id,
        meta=meta,
    )
    await db.commit()
    return organization.join_code


def normalize_join_code(code: str) -> str:
    return re.sub(r"[\s-]", "", code).upper()


async def find_by_join_code(db: AsyncSession, code: str) -> Organization:
    organization = await db.scalar(
        select(Organization).where(
            Organization.join_code == normalize_join_code(code),
            Organization.status == OrganizationStatus.ACTIVE,
        )
    )
    if not organization:
        raise NotFoundError("No school matches this code")
    return organization


async def join_by_code(
    db: AsyncSession, student: User, code: str, meta: RequestMeta
) -> Organization:
    organization = await find_by_join_code(db, code)
    await enroll_student(db, student, organization.id, student.id, EnrollmentSource.JOIN_CODE, meta)
    return organization


async def leave_organization(db: AsyncSession, student: User, meta: RequestMeta) -> None:
    enrollment = await db.scalar(
        select(StudentEnrollment)
        .where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.status == EnrollmentStatus.ACTIVE,
        )
        .with_for_update()
    )
    if not enrollment:
        raise NotFoundError("You are not enrolled in any organization")

    enrollment.status = EnrollmentStatus.LEFT
    enrollment.ended_at = datetime.now(UTC)
    enrollment.ended_by = student.id
    audit_service.record(
        db,
        actor=student,
        action="enrollment.leave",
        target_type="enrollment",
        target_id=enrollment.id,
        organization_id=enrollment.organization_id,
        changes={"status": ["active", "left"]},
        meta=meta,
    )
    await db.commit()
