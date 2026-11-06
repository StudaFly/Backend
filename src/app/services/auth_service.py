import hashlib
import logging
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import (
    ConflictError,
    NotFoundError,
    StudaFlyException,
    UnauthorizedError,
)
from src.app.core.security import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.app.models.enums import AccountType, UserStatus
from src.app.models.user import User
from src.app.schemas.user import AuthResponse, GoogleAuthRequest, UserCreate, UserLogin
from src.app.services import cache_service, google_oauth_service, user_service

logger = logging.getLogger(__name__)

_VERIFY_TTL = 24 * 3600
_REFRESH_TTL = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
_PASSWORD_SETUP_TTL = 7 * 24 * 3600
_PASSWORD_RESET_TTL = 3600

_BLOCKED_STATUSES = {
    UserStatus.SUSPENDED: ("ACCOUNT_SUSPENDED", "This account is suspended"),
    UserStatus.PENDING_DELETION: (
        "ACCOUNT_PENDING_DELETION",
        "This account is scheduled for deletion",
    ),
}


def _session_key(user_id: UUID | str, session_id: str) -> str:
    return f"auth:session:{user_id}:{session_id}"


def _password_token_key(token: str) -> str:
    return f"auth:password:{hashlib.sha256(token.encode()).hexdigest()}"


def _ensure_can_sign_in(user: User) -> None:
    if user.status in _BLOCKED_STATUSES:
        code, message = _BLOCKED_STATUSES[user.status]
        raise StudaFlyException(message, code=code, status_code=403)


async def issue_tokens(
    db: AsyncSession,
    user: User,
    session_id: str | None = None,
    mfa: bool = False,
    is_new_user: bool = False,
) -> AuthResponse:
    session_id = session_id or str(uuid4())
    mfa = mfa and user.account_type == AccountType.PLATFORM_ADMIN and user.mfa_enabled
    user_read = await user_service.build_user_read(db, user)
    access_token = create_access_token(
        user.id,
        session_id=session_id,
        token_version=user.token_version,
        account_type=user.account_type.value,
        org_id=user_read.organization.id if user_read.organization else None,
        org_role=user_read.org_role.value if user_read.org_role else None,
        mfa=mfa,
    )
    refresh_token, jti = create_refresh_token(
        user.id, session_id=session_id, token_version=user.token_version, mfa=mfa
    )
    await cache_service.set(_session_key(user.id, session_id), jti, ttl=_REFRESH_TTL)
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_read,
        mfa_required=user.account_type == AccountType.PLATFORM_ADMIN and not mfa,
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
        account_type=AccountType.STUDENT,
        email_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    verify_token = str(uuid4())
    await cache_service.set(f"auth:verify:{verify_token}", str(user.id), ttl=_VERIFY_TTL)
    logger.info("[DEV] email verification token for %s: %s", user.email, verify_token)

    return await issue_tokens(db, user)


async def login(db: AsyncSession, payload: UserLogin) -> AuthResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.password_hash:
        raise UnauthorizedError("Invalid email or password")

    if not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    _ensure_can_sign_in(user)

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)
    return await issue_tokens(db, user)


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> AuthResponse:
    try:
        payload = decode_token(refresh_token)
    except ValueError as e:
        raise UnauthorizedError("Invalid refresh token") from e

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid token type")

    user_id = payload["sub"]
    session_id = payload.get("sid")
    if not session_id:
        raise UnauthorizedError("Refresh token has been revoked or expired")

    stored_jti = await cache_service.get(_session_key(user_id, session_id))
    if not stored_jti or stored_jti != payload.get("jti"):
        raise UnauthorizedError("Refresh token has been revoked or expired")

    user = await db.get(User, UUID(user_id))
    if not user:
        raise UnauthorizedError("User not found")
    if user.status != UserStatus.ACTIVE or payload.get("token_version") != user.token_version:
        await cache_service.delete(_session_key(user_id, session_id))
        raise UnauthorizedError("Refresh token has been revoked or expired")

    return await issue_tokens(db, user, session_id=session_id, mfa=bool(payload.get("mfa")))


async def logout(user_id: UUID, session_id: str | None) -> None:
    if session_id:
        await cache_service.delete(_session_key(user_id, session_id))


async def revoke_all_sessions(user: User) -> None:
    user.token_version += 1
    await cache_service.delete_pattern(_session_key(user.id, "*"))


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


async def send_password_setup(user: User) -> str:
    token = secrets.token_urlsafe(32)
    await cache_service.set(_password_token_key(token), str(user.id), ttl=_PASSWORD_SETUP_TTL)
    logger.info("[DEV] password setup token for %s: %s", user.email, token)
    return token


async def forgot_password(db: AsyncSession, email: str) -> None:
    user = await db.scalar(select(User).where(User.email == email))
    if not user or user.status != UserStatus.ACTIVE:
        return
    token = secrets.token_urlsafe(32)
    await cache_service.set(_password_token_key(token), str(user.id), ttl=_PASSWORD_RESET_TTL)
    logger.info("[DEV] password reset token for %s: %s", user.email, token)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    key = _password_token_key(token)
    user_id = await cache_service.get(key)
    user = await db.get(User, UUID(user_id)) if user_id else None
    if not user or user.status != UserStatus.ACTIVE:
        raise NotFoundError("This link is invalid or has expired")

    user.password_hash = hash_password(new_password)
    user.email_verified = True
    await revoke_all_sessions(user)
    await db.commit()
    await cache_service.delete(key)


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

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)
    return await issue_tokens(db, user, is_new_user=is_new_user)


async def _find_or_create_google_user(
    db: AsyncSession, identity: google_oauth_service.GoogleIdentity
) -> tuple[User, bool]:
    user = await db.scalar(select(User).where(User.google_id == identity.sub))
    if user:
        _ensure_can_sign_in(user)
        return user, False

    # Same email as an existing account (email/password…): Google verified the
    # address, so the Google account is linked to it. The password stays valid.
    user = await db.scalar(select(User).where(func.lower(User.email) == identity.email.lower()))
    if user:
        _ensure_can_sign_in(user)
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
        account_type=AccountType.STUDENT,
        email_verified=True,
        oauth_provider="google",
        google_id=identity.sub,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, True


# TODO: Microsoft / Apple sign-in, same shape as google_login.
