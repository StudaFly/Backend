from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ForbiddenError, UnauthorizedError
from src.app.db.session import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    from src.app.core.security import decode_token
    from src.app.models.user import User

    if credentials is None:
        raise UnauthorizedError("Authentication required")

    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if user_id is None or payload.get("type") != "access":
            raise UnauthorizedError("Invalid or expired token")
        user_uuid = UUID(user_id)
    except ValueError:
        raise UnauthorizedError("Invalid or expired token") from None

    user = await db.get(User, user_uuid)
    if not user:
        raise UnauthorizedError("User not found")

    return user


async def require_premium(current_user=Depends(get_current_user)):
    if not current_user.is_premium:
        raise ForbiddenError("Premium subscription required")
    return current_user


async def require_admin(current_user=Depends(get_current_user)):
    if current_user.role not in ("admin", "superadmin"):
        raise ForbiddenError("Admin role required")
    return current_user
