from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.core.exceptions import ForbiddenError, NotFoundError
from src.app.models.mobility import Mobility
from src.app.models.task import Task
from src.app.schemas.task import TaskRead
from src.app.services import task_generation_service


async def get_timeline(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> list[TaskRead]:
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
    tasks = tasks_result.scalars().all()
    return [TaskRead.model_validate(t) for t in tasks]
