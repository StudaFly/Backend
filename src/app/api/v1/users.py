from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_current_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.user import UserRead, UserUpdate
from src.app.services import user_service

router = APIRouter()


@router.get("/me", response_model=ResponseBase[UserRead])
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[UserRead]:
    user = await user_service.get_by_id(db, current_user.id)
    return ResponseBase(data=user, message="OK")


@router.patch("/me", response_model=ResponseBase[UserRead])
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[UserRead]:
    user = await user_service.update(db, current_user.id, payload)
    return ResponseBase(data=user, message="Profile updated successfully")


@router.delete("/me", status_code=204)
async def delete_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await user_service.delete(db, current_user.id)
