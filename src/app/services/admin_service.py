from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.task import TaskCreate, TaskRead
from src.app.schemas.user import UserRead


async def list_students(db: AsyncSession, institution_id: UUID) -> list[UserRead]:
    # TODO: fetch all students for the institution
    raise NotImplementedError


async def get_stats(db: AsyncSession, institution_id: UUID) -> dict:
    # TODO: aggregate stats (active mobilities, task completion rates, etc.)
    raise NotImplementedError


async def create_global_task(
    db: AsyncSession, institution_id: UUID, payload: TaskCreate
) -> list[TaskRead]:
    # TODO: add task to all active mobilities of the institution's students
    raise NotImplementedError
