from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.task import TaskRead


async def get_timeline(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> list[TaskRead]:
    # TODO: fetch or generate timeline via ai_service, ordered by deadline
    raise NotImplementedError
