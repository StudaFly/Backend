from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.core.exceptions import ForbiddenError, NotFoundError
from src.app.core.reference import TASK_CATEGORIES
from src.app.models.mobility import Mobility
from src.app.models.task import Task
from src.app.schemas.progress import CategoryProgress, MobilityProgress
from src.app.schemas.task import TaskRead
from src.app.services import task_generation_service

NEXT_TASKS_COUNT = 3


async def get_progress(
    db: AsyncSession, user_id: UUID, mobility_id: UUID, today: date | None = None
) -> MobilityProgress:
    today = today or date.today()
    result = await db.execute(
        select(Mobility)
        .options(selectinload(Mobility.destination))
        .where(Mobility.id == mobility_id)
    )
    mobility = result.scalar_one_or_none()
    if not mobility:
        raise NotFoundError("Mobility not found")
    if mobility.user_id != user_id:
        raise ForbiddenError()

    await task_generation_service.ensure_tasks(db, mobility)
    tasks_result = await db.execute(
        select(Task)
        .where(Task.mobility_id == mobility_id)
        .order_by(Task.deadline.asc().nulls_last(), Task.priority.asc())
    )
    tasks = list(tasks_result.scalars().all())
    return compute_progress(mobility, tasks, today)


def compute_progress(mobility: Mobility, tasks: list[Task], today: date) -> MobilityProgress:
    completed = [t for t in tasks if t.is_completed]
    pending_with_deadline = [t for t in tasks if not t.is_completed and t.deadline]

    by_category = []
    for category in TASK_CATEGORIES:
        in_category = [t for t in tasks if t.category == category["key"]]
        if in_category:
            by_category.append(
                CategoryProgress(
                    category=category["key"],
                    label=category["label"],
                    done=sum(1 for t in in_category if t.is_completed),
                    total=len(in_category),
                )
            )

    return MobilityProgress(
        mobility_id=mobility.id,
        total_tasks=len(tasks),
        completed_tasks=len(completed),
        percent=round(len(completed) * 100 / len(tasks)) if tasks else 0,
        days_until_departure=(mobility.departure_date - today).days,
        overdue_tasks=sum(1 for t in pending_with_deadline if t.deadline < today),
        by_category=by_category,
        next_tasks=[TaskRead.model_validate(t) for t in pending_with_deadline[:NEXT_TASKS_COUNT]],
    )
