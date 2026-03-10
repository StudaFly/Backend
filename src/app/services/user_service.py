from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import NotFoundError
from src.app.models.user import User
from src.app.schemas.user import UserRead, UserUpdate


async def get_by_id(db: AsyncSession, user_id: UUID) -> UserRead:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return UserRead.model_validate(user)


async def update(db: AsyncSession, user_id: UUID, payload: UserUpdate) -> UserRead:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")

    data = payload.model_dump(exclude_unset=True)

    first_name = data.pop("first_name", None)
    last_name = data.pop("last_name", None)
    if first_name is not None or last_name is not None:
        parts = [p for p in [first_name, last_name] if p is not None]
        user.name = " ".join(parts)

    data.pop("profile_picture_uri", None)
    data.pop("institution", None)

    for field, value in data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


async def delete(db: AsyncSession, user_id: UUID) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    await db.delete(user)
    await db.commit()
