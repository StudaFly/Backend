from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz.actor import Actor, load_actor
from src.app.core.dependencies import get_current_user
from src.app.core.exceptions import ForbiddenError
from src.app.db.session import get_db
from src.app.models.enums import AccountType, OrganizationStatus, OrgRole
from src.app.models.user import User


async def get_actor(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    return await load_actor(db, current_user)


def require_account_type(*account_types: AccountType):
    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.account_type not in account_types:
            raise ForbiddenError("This account cannot access this resource")
        return actor

    return dependency


def require_org_role(*org_roles: OrgRole):

    async def dependency(
        actor: Actor = Depends(require_account_type(AccountType.ORG_STAFF)),
    ) -> Actor:
        membership, organization = actor.membership, actor.organization
        if (
            membership is None
            or organization is None
            or not membership.is_active
            or organization.status != OrganizationStatus.ACTIVE
        ):
            raise ForbiddenError("No active organization membership")
        if org_roles and membership.org_role not in org_roles:
            raise ForbiddenError("Your role in the organization does not allow this action")
        return actor

    return dependency
