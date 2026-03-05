from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.user import UserCreate, UserLogin


async def register(db: AsyncSession, payload: UserCreate) -> dict:
    # TODO: check email uniqueness, hash password, create user, send verification email
    raise NotImplementedError


async def login(db: AsyncSession, payload: UserLogin) -> dict:
    # TODO: fetch user by email, verify password, create tokens, store refresh in Redis
    raise NotImplementedError


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> dict:
    # TODO: validate refresh token from Redis, create new token pair
    raise NotImplementedError


async def logout(db: AsyncSession, user_id: UUID, refresh_token: str) -> None:
    # TODO: invalidate refresh token in Redis
    raise NotImplementedError


async def forgot_password(db: AsyncSession, email: str) -> None:
    # TODO: generate reset token (UUID), store in Redis with 1h TTL, send email via SES
    raise NotImplementedError


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    # TODO: validate reset token from Redis (single-use), update password hash
    raise NotImplementedError


async def verify_email(db: AsyncSession, token: str) -> None:
    # TODO: validate email verification token, mark user.email_verified = True
    raise NotImplementedError


async def oauth_login(db: AsyncSession, provider: str, code: str) -> dict:
    # TODO: exchange OAuth code for tokens, upsert user, return JWT tokens
    raise NotImplementedError
