from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_current_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.mobility import MobilityCreate, MobilityRead, MobilityUpdate
from src.app.services import mobility_service

router = APIRouter()


@router.get("/", response_model=ResponseBase[list[MobilityRead]])
async def list_mobilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[list[MobilityRead]]:
    mobilities = await mobility_service.list_by_user(db, user_id=current_user.id)
    return ResponseBase(data=mobilities, message="Mobilities retrieved successfully")


@router.post("/", response_model=ResponseBase[MobilityRead], status_code=201)
async def create_mobility(
    payload: MobilityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[MobilityRead]:
    mobility = await mobility_service.create(db, user_id=current_user.id, payload=payload)
    return ResponseBase(data=mobility, message="Mobility created successfully")


@router.get("/{mobility_id}", response_model=ResponseBase[MobilityRead])
async def get_mobility(
    mobility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[MobilityRead]:
    mobility = await mobility_service.get_by_id(
        db, user_id=current_user.id, mobility_id=mobility_id
    )
    return ResponseBase(data=mobility, message="OK")


@router.patch("/{mobility_id}", response_model=ResponseBase[MobilityRead])
async def update_mobility(
    mobility_id: UUID,
    payload: MobilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[MobilityRead]:
    mobility = await mobility_service.update(
        db, user_id=current_user.id, mobility_id=mobility_id, payload=payload
    )
    return ResponseBase(data=mobility, message="Mobility updated successfully")


@router.delete("/{mobility_id}", status_code=204)
async def delete_mobility(
    mobility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await mobility_service.delete(db, user_id=current_user.id, mobility_id=mobility_id)
