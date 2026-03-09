import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.app.core.security import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.app.models.user import User
from src.app.schemas.user import TokenResponse, UserCreate, UserLogin, UserRead
from src.app.services import cache_service

logger = logging.getLogger(__name__)

_VERIFY_TTL = 24 * 3600
_REFRESH_TTL = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


async def register(db: AsyncSession, payload: UserCreate) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise ConflictError("An account with this email already exists")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        email_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    verify_token = str(uuid4())
    await cache_service.set(f"auth:verify:{verify_token}", str(user.id), ttl=_VERIFY_TTL)
    logger.info("[DEV] email verification token for %s: %s", user.email, verify_token)

    return user


async def login(db: AsyncSession, payload: UserLogin) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.password_hash:
        raise UnauthorizedError("Invalid email or password")

    if not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    access_token = create_access_token(user.id)
    refresh_token, jti = create_refresh_token(user.id)
    await cache_service.set(f"auth:refresh:{user.id}", jti, ttl=_REFRESH_TTL)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserRead.model_validate(user),
    )


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except ValueError as e:
        raise UnauthorizedError("Invalid refresh token") from e

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid token type")

    user_id = payload["sub"]
    jti = payload.get("jti")

    stored_jti = await cache_service.get(f"auth:refresh:{user_id}")
    if not stored_jti or stored_jti != jti:
        raise UnauthorizedError("Refresh token has been revoked or expired")

    user = await db.get(User, UUID(user_id))
    if not user:
        raise UnauthorizedError("User not found")

    await cache_service.delete(f"auth:refresh:{user_id}")
    new_access = create_access_token(user.id)
    new_refresh, new_jti = create_refresh_token(user.id)
    await cache_service.set(f"auth:refresh:{user.id}", new_jti, ttl=_REFRESH_TTL)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserRead.model_validate(user),
    )


async def logout(user_id: UUID) -> None:
    await cache_service.delete(f"auth:refresh:{user_id}")


async def verify_email(db: AsyncSession, token: str) -> None:
    user_id = await cache_service.get(f"auth:verify:{token}")
    if not user_id:
        raise NotFoundError("Verification token is invalid or has expired")

    user = await db.get(User, UUID(user_id))
    if not user:
        raise NotFoundError("User not found")

    user.email_verified = True
    await db.commit()
    await cache_service.delete(f"auth:verify:{token}")


async def forgot_password(db: AsyncSession, email: str) -> None:
    # TODO: generate reset token, store in Redis, send via SES
    raise NotImplementedError


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    # TODO: validate reset token from Redis (single-use), update password hash
    raise NotImplementedError


async def oauth_login(db: AsyncSession, provider: str, code: str) -> dict:
    # TODO: exchange OAuth code for tokens, upsert user, return JWT tokens
    raise NotImplementedError
