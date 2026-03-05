from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.user import User
from src.app.schemas.user import UserRead, UserUpdate


async def get_by_id(db: AsyncSession, user_id: UUID) -> User:
    # TODO: fetch user or raise NotFoundError
    raise NotImplementedError


async def update(db: AsyncSession, user_id: UUID, payload: UserUpdate) -> UserRead:
    # TODO: update user fields, return updated UserRead
    raise NotImplementedError


async def delete(db: AsyncSession, user_id: UUID) -> None:
    # TODO: delete user and all associated data (RGPD)
    raise NotImplementedError
