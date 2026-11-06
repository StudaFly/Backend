from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.authz.actor import Actor, load_actor
from src.app.core.dependencies import get_access_payload, get_current_user
from src.app.core.exceptions import ForbiddenError, StudaFlyException
from src.app.db.session import get_db
from src.app.models.enums import AccountType, OrganizationStatus, OrgRole
from src.app.models.user import User
from src.app.services import contract_service
from src.app.services.contract_service import ContractState


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


_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def require_org_role(*org_roles: OrgRole):
    async def dependency(
        request: Request,
        actor: Actor = Depends(require_account_type(AccountType.ORG_STAFF)),
        db: AsyncSession = Depends(get_db),
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

        state, _ = await contract_service.contract_state(db, organization.id)
        if state == ContractState.BLOCKED:
            raise StudaFlyException(
                "Your school's contract is suspended or cancelled",
                code="CONTRACT_INACTIVE",
                status_code=403,
            )
        if state == ContractState.READ_ONLY and request.method not in _READ_METHODS:
            raise StudaFlyException(
                "Your school's contract has expired: read-only access",
                code="CONTRACT_EXPIRED",
                status_code=403,
            )
        return actor

    return dependency


async def require_platform_admin(
    actor: Actor = Depends(require_account_type(AccountType.PLATFORM_ADMIN)),
    token: dict = Depends(get_access_payload),
) -> Actor:
    if not (token.get("mfa") is True and actor.user.mfa_enabled):
        raise StudaFlyException(
            "Multi-factor authentication required", code="MFA_REQUIRED", status_code=403
        )
    return actor
