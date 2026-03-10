from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ForbiddenError, NotFoundError
from src.app.models.mobility import Mobility
from src.app.schemas.mobility import MobilityCreate, MobilityRead, MobilityUpdate


async def list_by_user(db: AsyncSession, user_id: UUID) -> list[MobilityRead]:
    result = await db.execute(
        select(Mobility).where(Mobility.user_id == user_id).order_by(Mobility.created_at.desc())
    )
    mobilities = result.scalars().all()
    return [MobilityRead.model_validate(m) for m in mobilities]


async def create(db: AsyncSession, user_id: UUID, payload: MobilityCreate) -> MobilityRead:
    mobility = Mobility(
        user_id=user_id,
        destination_id=payload.destination_id,
        type=payload.type,
        departure_date=payload.departure_date,
        return_date=payload.return_date,
        school=payload.school,
        status="preparing",
    )
    db.add(mobility)
    await db.commit()
    await db.refresh(mobility)
    return MobilityRead.model_validate(mobility)


async def get_by_id(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> MobilityRead:
    mobility = await db.get(Mobility, mobility_id)
    if not mobility:
        raise NotFoundError("Mobility not found")
    if mobility.user_id != user_id:
        raise ForbiddenError()
    return MobilityRead.model_validate(mobility)


async def update(
    db: AsyncSession, user_id: UUID, mobility_id: UUID, payload: MobilityUpdate
) -> MobilityRead:
    mobility = await db.get(Mobility, mobility_id)
    if not mobility:
        raise NotFoundError("Mobility not found")
    if mobility.user_id != user_id:
        raise ForbiddenError()
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(mobility, field, value)
    await db.commit()
    await db.refresh(mobility)
    return MobilityRead.model_validate(mobility)


async def delete(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> None:
    mobility = await db.get(Mobility, mobility_id)
    if not mobility:
        raise NotFoundError("Mobility not found")
    if mobility.user_id != user_id:
        raise ForbiddenError()
    await db.delete(mobility)
    await db.commit()
