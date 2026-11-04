import logging
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
from src.app.schemas.user import (
    AuthResponse,
    GoogleAuthRequest,
    UserCreate,
    UserLogin,
    UserRead,
)
from src.app.services import cache_service, google_oauth_service

logger = logging.getLogger(__name__)

_VERIFY_TTL = 24 * 3600
_REFRESH_TTL = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


async def _issue_tokens(user: User, *, is_new_user: bool = False) -> AuthResponse:
    access_token = create_access_token(user.id)
    refresh_token, jti = create_refresh_token(user.id)
    await cache_service.set(f"auth:refresh:{user.id}", jti, ttl=_REFRESH_TTL)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserRead.model_validate(user),
        is_new_user=is_new_user,
    )


async def register(db: AsyncSession, payload: UserCreate) -> AuthResponse:
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

    return await _issue_tokens(user)


async def login(db: AsyncSession, payload: UserLogin) -> AuthResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.password_hash:
        raise UnauthorizedError("Invalid email or password")

    if not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    return await _issue_tokens(user)


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> AuthResponse:
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
    return await _issue_tokens(user)


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


async def google_login(db: AsyncSession, payload: GoogleAuthRequest) -> AuthResponse:
    id_token = payload.id_token or await google_oauth_service.exchange_code(payload.code)
    identity = await google_oauth_service.verify_id_token(id_token)
    if not identity.email_verified:
        raise UnauthorizedError("The email address of this Google account is not verified")

    try:
        user, is_new_user = await _find_or_create_google_user(db, identity)
    except IntegrityError:
        # Two simultaneous first sign-ins: the other request created the account.
        await db.rollback()
        user, is_new_user = await _find_or_create_google_user(db, identity)

    return await _issue_tokens(user, is_new_user=is_new_user)


async def _find_or_create_google_user(
    db: AsyncSession, identity: google_oauth_service.GoogleIdentity
) -> tuple[User, bool]:
    user = await db.scalar(select(User).where(User.google_id == identity.sub))
    if user:
        return user, False

    # Same email as an existing account (email/password…): Google verified the
    # address, so the Google account is linked to it. The password stays valid.
    user = await db.scalar(select(User).where(func.lower(User.email) == identity.email.lower()))
    if user:
        user.google_id = identity.sub
        user.email_verified = True
        user.oauth_provider = user.oauth_provider or "google"
        await db.commit()
        await db.refresh(user)
        return user, False

    user = User(
        email=identity.email,
        name=identity.name or identity.email.split("@")[0],
        password_hash=None,
        email_verified=True,
        oauth_provider="google",
        google_id=identity.sub,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, True


# TODO: Microsoft / Apple sign-in, same shape as google_login.
