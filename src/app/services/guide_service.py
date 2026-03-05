from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.guide import GuideContent


async def get_guide(db: AsyncSession, destination_id: UUID) -> GuideContent:
    # TODO: check destination.guide_content cache, call ai_service if empty
    raise NotImplementedError
