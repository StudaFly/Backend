from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.task import TaskCreate, TaskRead, TaskUpdate


async def list_tasks(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> list[TaskRead]:
    # TODO: fetch all tasks for mobility, verify ownership
    raise NotImplementedError


async def create_task(
    db: AsyncSession, user_id: UUID, mobility_id: UUID, payload: TaskCreate
) -> TaskRead:
    # TODO: create task, verify mobility ownership
    raise NotImplementedError


async def update_task(
    db: AsyncSession, user_id: UUID, task_id: UUID, payload: TaskUpdate
) -> TaskRead:
    # TODO: update task, verify ownership via mobility
    raise NotImplementedError


async def complete_task(db: AsyncSession, user_id: UUID, task_id: UUID) -> TaskRead:
    # TODO: mark task as completed
    raise NotImplementedError


async def delete_task(db: AsyncSession, user_id: UUID, task_id: UUID) -> None:
    # TODO: delete task, verify ownership
    raise NotImplementedError
