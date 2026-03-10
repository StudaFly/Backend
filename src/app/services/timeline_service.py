import json
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.core.exceptions import ForbiddenError, NotFoundError
from src.app.models.mobility import Mobility
from src.app.models.task import Task
from src.app.schemas.task import TaskRead
from src.app.services.ai import ai_service

VALID_CATEGORIES = {"admin", "finance", "housing", "health", "practical"}


def _validate_category(category: str) -> str:
    return category if category in VALID_CATEGORIES else "admin"


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


async def get_timeline(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> list[TaskRead]:
    result = await db.execute(
        select(Mobility)
        .options(selectinload(Mobility.destination), selectinload(Mobility.tasks))
        .where(Mobility.id == mobility_id)
    )
    mobility = result.scalar_one_or_none()

    if not mobility:
        raise NotFoundError("Mobility not found")
    if mobility.user_id != user_id:
        raise ForbiddenError()

    if not mobility.tasks:
        destination = mobility.destination
        milestones = []
        try:
            raw = await ai_service.generate_timeline(
                destination=f"{destination.city}, {destination.country}",
                mobility_type=mobility.type,
                departure_date=str(mobility.departure_date),
            )
            data = json.loads(raw)
            milestones = data.get("milestones", [])
        except Exception:
            pass

        for milestone in milestones:
            task = Task(
                mobility_id=mobility_id,
                title=milestone.get("title", ""),
                description=milestone.get("description"),
                category=_validate_category(milestone.get("category", "admin")),
                deadline=_parse_date(milestone.get("deadline")),
                is_completed=False,
                priority=1,
            )
            db.add(task)
        await db.commit()

    tasks_result = await db.execute(
        select(Task)
        .where(Task.mobility_id == mobility_id)
        .order_by(Task.deadline.asc().nulls_last(), Task.priority.asc())
    )
    tasks = tasks_result.scalars().all()
    return [TaskRead.model_validate(t) for t in tasks]
