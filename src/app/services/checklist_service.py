import json
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.core.exceptions import ForbiddenError, NotFoundError
from src.app.models.mobility import Mobility
from src.app.models.task import Task
from src.app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from src.app.services.ai import ai_service

VALID_CATEGORIES = {"admin", "finance", "housing", "health", "practical"}


def _validate_category(category: str) -> str:
    return category if category in VALID_CATEGORIES else "admin"


async def _get_mobility_for_user(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> Mobility:
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
    return mobility


async def _get_task_for_user(db: AsyncSession, user_id: UUID, task_id: UUID) -> Task:
    result = await db.execute(
        select(Task).options(selectinload(Task.mobility)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("Task not found")
    if task.mobility.user_id != user_id:
        raise ForbiddenError()
    return task


async def list_tasks(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> list[TaskRead]:
    mobility = await _get_mobility_for_user(db, user_id, mobility_id)

    result = await db.execute(
        select(Task)
        .where(Task.mobility_id == mobility_id)
        .order_by(Task.priority.asc(), Task.deadline.asc().nulls_last())
    )
    tasks = result.scalars().all()

    if not tasks:
        destination = mobility.destination
        ai_tasks = []
        try:
            raw = await ai_service.generate_checklist(
                destination=f"{destination.city}, {destination.country}",
                mobility_type=mobility.type,
                departure_date=str(mobility.departure_date),
            )
            data = json.loads(raw)
            ai_tasks = data.get("tasks", [])
        except Exception:
            pass

        for item in ai_tasks:
            weeks_before = item.get("deadline_weeks_before") or 0
            deadline = None
            if weeks_before and mobility.departure_date:
                deadline = mobility.departure_date - timedelta(weeks=int(weeks_before))
            task = Task(
                mobility_id=mobility_id,
                title=item.get("title", ""),
                description=item.get("description"),
                category=_validate_category(item.get("category", "admin")),
                deadline=deadline,
                is_completed=False,
                priority=item.get("priority", 3),
            )
            db.add(task)
        await db.commit()

        result = await db.execute(
            select(Task)
            .where(Task.mobility_id == mobility_id)
            .order_by(Task.priority.asc(), Task.deadline.asc().nulls_last())
        )
        tasks = result.scalars().all()

    return [TaskRead.model_validate(t) for t in tasks]


async def create_task(
    db: AsyncSession, user_id: UUID, mobility_id: UUID, payload: TaskCreate
) -> TaskRead:
    await _get_mobility_for_user(db, user_id, mobility_id)
    task = Task(
        mobility_id=mobility_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        deadline=payload.deadline,
        is_completed=False,
        priority=payload.priority,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return TaskRead.model_validate(task)


async def update_task(
    db: AsyncSession, user_id: UUID, task_id: UUID, payload: TaskUpdate
) -> TaskRead:
    task = await _get_task_for_user(db, user_id, task_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return TaskRead.model_validate(task)


async def complete_task(db: AsyncSession, user_id: UUID, task_id: UUID) -> TaskRead:
    task = await _get_task_for_user(db, user_id, task_id)
    task.is_completed = True
    await db.commit()
    await db.refresh(task)
    return TaskRead.model_validate(task)


async def delete_task(db: AsyncSession, user_id: UUID, task_id: UUID) -> None:
    task = await _get_task_for_user(db, user_id, task_id)
    await db.delete(task)
    await db.commit()
