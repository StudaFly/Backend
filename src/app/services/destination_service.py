from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, NotFoundError
from src.app.models.destination import Destination
from src.app.schemas.destination import DestinationCreate, DestinationRead


async def list_all(db: AsyncSession, query: str | None = None) -> list[DestinationRead]:
    stmt = select(Destination)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(
                Destination.city.ilike(like),
                Destination.country.ilike(like),
            )
        )
    stmt = stmt.order_by(Destination.country, Destination.city)
    result = await db.execute(stmt)
    destinations = result.scalars().all()
    return [DestinationRead.model_validate(d) for d in destinations]


async def create(db: AsyncSession, payload: DestinationCreate) -> DestinationRead:
    existing = await db.scalar(
        select(Destination).where(
            Destination.city == payload.city,
            Destination.country == payload.country,
        )
    )
    if existing:
        raise ConflictError(f"{payload.city}, {payload.country} already exists")

    destination = Destination(
        country=payload.country,
        city=payload.city,
    )
    db.add(destination)
    await db.commit()
    await db.refresh(destination)
    return DestinationRead.model_validate(destination)


async def get_by_id(db: AsyncSession, destination_id: UUID) -> DestinationRead:
    destination = await db.get(Destination, destination_id)
    if not destination:
        raise NotFoundError("Destination not found")
    return DestinationRead.model_validate(destination)
