from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import ConflictError, NotFoundError
from src.app.models.destination import Destination
from src.app.schemas.destination import (
    DestinationCreate,
    DestinationDetail,
    DestinationFacts,
    DestinationRead,
)


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
        image_url=payload.image_url,
        summary=payload.summary,
        facts=payload.facts.model_dump(exclude_none=True) if payload.facts else None,
    )
    db.add(destination)
    await db.commit()
    await db.refresh(destination)
    return DestinationRead.model_validate(destination)


def to_detail(destination: Destination) -> DestinationDetail:
    return DestinationDetail(
        id=destination.id,
        country=destination.country,
        city=destination.city,
        image_url=destination.image_url,
        summary=destination.summary,
        facts=DestinationFacts.model_validate(destination.facts) if destination.facts else None,
        has_budget=bool(destination.cost_of_living),
        has_guide=bool(destination.guide_content),
    )


async def get_by_id(db: AsyncSession, destination_id: UUID) -> DestinationDetail:
    destination = await db.get(Destination, destination_id)
    if not destination:
        raise NotFoundError("Destination not found")
    return to_detail(destination)
