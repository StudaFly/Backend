from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import get_db
from src.app.schemas.budget import BudgetEstimate
from src.app.schemas.common import ResponseBase
from src.app.services import budget_service

router = APIRouter()


@router.get("/{destination_id}/budget", response_model=ResponseBase[BudgetEstimate])
async def get_budget(
    destination_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ResponseBase[BudgetEstimate]:
    budget = await budget_service.get_budget_estimate(db, destination_id)
    return ResponseBase(data=budget, message="OK")
