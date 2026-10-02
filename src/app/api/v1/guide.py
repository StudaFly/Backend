from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import get_db
from src.app.schemas.common import ResponseBase
from src.app.schemas.guide import GuideContent
from src.app.services import guide_service

router = APIRouter()


@router.get("/{destination_id}/guide", response_model=ResponseBase[GuideContent])
async def get_guide(
    destination_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ResponseBase[GuideContent]:
    guide = await guide_service.get_guide(db, destination_id)
    return ResponseBase(data=guide, message="OK")
