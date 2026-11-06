from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import NotFoundError
from src.app.models.destination import Destination
from src.app.models.mobility import Mobility
from src.app.schemas.mobility import MobilityCreate, MobilityRead, MobilityUpdate
from src.app.services import task_generation_service


async def list_by_user(db: AsyncSession, user_id: UUID) -> list[MobilityRead]:
    result = await db.execute(
        select(Mobility).where(Mobility.user_id == user_id).order_by(Mobility.created_at.desc())
    )
    mobilities = result.scalars().all()
    return [MobilityRead.model_validate(m) for m in mobilities]


async def create(db: AsyncSession, user_id: UUID, payload: MobilityCreate) -> MobilityRead:
    destination = await db.get(Destination, payload.destination_id)
    if not destination:
        raise NotFoundError("Destination not found")

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
    await db.flush()
    db.add_all(await task_generation_service.build_tasks(mobility, destination))
    await db.commit()
    await db.refresh(mobility)
    return MobilityRead.model_validate(mobility)


async def _get_owned(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> Mobility:
    mobility = await db.scalar(
        select(Mobility).where(Mobility.id == mobility_id, Mobility.user_id == user_id)
    )
    if not mobility:
        raise NotFoundError("Mobility not found")
    return mobility


async def get_by_id(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> MobilityRead:
    mobility = await _get_owned(db, user_id, mobility_id)
    return MobilityRead.model_validate(mobility)


async def update(
    db: AsyncSession, user_id: UUID, mobility_id: UUID, payload: MobilityUpdate
) -> MobilityRead:
    mobility = await _get_owned(db, user_id, mobility_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(mobility, field, value)
    await db.commit()
    await db.refresh(mobility)
    return MobilityRead.model_validate(mobility)


async def delete(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> None:
    mobility = await _get_owned(db, user_id, mobility_id)
    await db.delete(mobility)
    await db.commit()
