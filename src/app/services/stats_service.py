from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.destination import Destination
from src.app.models.user import User
from src.app.schemas.reference import PublicStats
from src.app.services.task_generation_service import load_templates


async def get_public_stats(db: AsyncSession) -> PublicStats:
    destinations = await db.scalar(select(func.count(Destination.id)))
    countries = await db.scalar(select(func.count(func.distinct(Destination.country))))
    students = await db.scalar(select(func.count(User.id)).where(User.role == "student"))
    return PublicStats(
        countries=countries or 0,
        destinations=destinations or 0,
        students=students or 0,
        preparation_steps=len(load_templates()["tasks"]),
    )
