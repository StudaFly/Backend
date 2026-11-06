from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ForbiddenError, UnauthorizedError
from src.app.db.session import get_db

security = HTTPBearer(auto_error=False)


async def get_access_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    from src.app.core.security import decode_token

    if credentials is None:
        raise UnauthorizedError("Authentication required")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise UnauthorizedError("Invalid or expired token") from None
    if payload.get("sub") is None or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")
    return payload


async def get_current_user(
    payload: dict = Depends(get_access_payload),
    db: AsyncSession = Depends(get_db),
):
    from src.app.models.enums import UserStatus
    from src.app.models.user import User

    try:
        user_uuid = UUID(payload["sub"])
    except ValueError:
        raise UnauthorizedError("Invalid or expired token") from None

    user = await db.get(User, user_uuid)
    if not user:
        raise UnauthorizedError("User not found")

    if user.status != UserStatus.ACTIVE or payload.get("token_version") != user.token_version:
        raise UnauthorizedError("Invalid or expired token")

    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    if credentials is None:
        return None
    return await get_current_user(await get_access_payload(credentials), db)


async def require_premium(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    from src.app.services.entitlements import premium_for

    if not (await premium_for(db, current_user.id)).active:
        raise ForbiddenError("Premium subscription required")
    return current_user
