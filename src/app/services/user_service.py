from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz.actor import load_actor
from src.app.core.exceptions import NotFoundError
from src.app.models.enums import AccountType, EnrollmentStatus, OrgRole
from src.app.models.organization import Organization
from src.app.models.student_enrollment import StudentEnrollment
from src.app.models.user import User
from src.app.schemas.organization import OrganizationSummary
from src.app.schemas.user import UserRead, UserUpdate

_LEGACY_ROLES = {
    AccountType.STUDENT: "student",
    AccountType.ORG_STAFF: "admin",
    AccountType.PLATFORM_ADMIN: "superadmin",
}


async def get_organization_context(
    db: AsyncSession, user: User
) -> tuple[Organization | None, OrgRole | None]:
    if user.account_type == AccountType.ORG_STAFF:
        actor = await load_actor(db, user)
        if actor.membership is not None and actor.membership.is_active:
            return actor.organization, actor.org_role
        return None, None
    if user.account_type == AccountType.STUDENT:
        organization = await db.scalar(
            select(Organization)
            .join(StudentEnrollment, StudentEnrollment.organization_id == Organization.id)
            .where(
                StudentEnrollment.student_id == user.id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        return organization, None
    return None, None


async def build_user_read(db: AsyncSession, user: User) -> UserRead:
    organization, org_role = await get_organization_context(db, user)
    return UserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        account_type=user.account_type,
        org_role=org_role,
        organization=OrganizationSummary.model_validate(organization) if organization else None,
        role=_LEGACY_ROLES[user.account_type],
        institution_id=organization.id if organization else None,
        is_premium=user.is_premium,
        email_verified=user.email_verified,
        oauth_provider=user.oauth_provider,
        avatar_emoji=user.avatar_emoji,
        phone=user.phone,
        enable_notifications=user.enable_notifications,
        created_at=user.created_at,
    )


async def get_by_id(db: AsyncSession, user_id: UUID) -> UserRead:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return await build_user_read(db, user)


async def update(db: AsyncSession, user_id: UUID, payload: UserUpdate) -> UserRead:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")

    data = payload.model_dump(exclude_unset=True)

    first_name = data.pop("first_name", None)
    last_name = data.pop("last_name", None)
    if first_name is not None or last_name is not None:
        existing_parts = user.name.split(" ", 1)
        existing_first = existing_parts[0]
        existing_last = existing_parts[1] if len(existing_parts) > 1 else ""
        new_first = first_name if first_name is not None else existing_first
        new_last = last_name if last_name is not None else existing_last
        user.name = f"{new_first} {new_last}".strip()

    data.pop("profile_picture_uri", None)
    data.pop("institution", None)

    for field, value in data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return await build_user_read(db, user)


async def delete(db: AsyncSession, user_id: UUID) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    await db.delete(user)
    await db.commit()
