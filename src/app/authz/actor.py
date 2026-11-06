import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.enums import AccountType, OrgRole
from src.app.models.organization import Organization
from src.app.models.organization_member import OrganizationMember
from src.app.models.user import User


@dataclass(frozen=True)
class Actor:
    user: User
    membership: OrganizationMember | None = None
    organization: Organization | None = None

    @property
    def account_type(self) -> AccountType:
        return self.user.account_type

    @property
    def org_role(self) -> OrgRole | None:
        return self.membership.org_role if self.membership else None

    @property
    def organization_id(self) -> uuid.UUID | None:
        return self.organization.id if self.organization else None


async def load_actor(db: AsyncSession, user: User) -> Actor:
    if user.account_type != AccountType.ORG_STAFF:
        return Actor(user=user)

    row = (
        await db.execute(
            select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == user.id)
        )
    ).first()
    if row is None:
        return Actor(user=user)
    membership, organization = row
    return Actor(user=user, membership=membership, organization=organization)
