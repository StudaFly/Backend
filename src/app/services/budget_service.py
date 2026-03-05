from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.budget import BudgetEstimate


async def get_budget_estimate(db: AsyncSession, destination_id: UUID) -> BudgetEstimate:
    # TODO: check destination cache, call ai_service if not cached
    raise NotImplementedError
