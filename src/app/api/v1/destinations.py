from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_current_user, require_admin
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.destination import DestinationCreate, DestinationRead
from src.app.services import destination_service

router = APIRouter()


@router.get("/", response_model=ResponseBase[list[DestinationRead]])
async def list_destinations(
    query: str | None = Query(
        default=None, description="Search by city or country (case-insensitive)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[list[DestinationRead]]:
    destinations = await destination_service.list_all(db, query=query)
    return ResponseBase(data=destinations, message="Destinations retrieved successfully")


@router.post("/", response_model=ResponseBase[DestinationRead], status_code=201)
async def create_destination(
    payload: DestinationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ResponseBase[DestinationRead]:
    destination = await destination_service.create(db, payload=payload)
    return ResponseBase(data=destination, message="Destination created successfully")


@router.get("/{destination_id}", response_model=ResponseBase[DestinationRead])
async def get_destination(
    destination_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[DestinationRead]:
    destination = await destination_service.get_by_id(db, destination_id=destination_id)
    return ResponseBase(data=destination, message="OK")
