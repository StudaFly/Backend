from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.mobility import Mobility
from src.app.schemas.mobility import MobilityCreate, MobilityRead, MobilityUpdate


async def list_by_user(db: AsyncSession, user_id: UUID) -> list[MobilityRead]:
    # TODO: query mobilities for user_id
    raise NotImplementedError


async def create(db: AsyncSession, user_id: UUID, payload: MobilityCreate) -> MobilityRead:
    # TODO: create mobility, trigger AI prefetch worker
    raise NotImplementedError


async def get_by_id(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> Mobility:
    # TODO: fetch mobility, verify ownership (raise ForbiddenError if not owner)
    raise NotImplementedError


async def update(
    db: AsyncSession, user_id: UUID, mobility_id: UUID, payload: MobilityUpdate
) -> MobilityRead:
    # TODO: update mobility fields
    raise NotImplementedError


async def delete(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> None:
    # TODO: delete mobility and cascade
    raise NotImplementedError
