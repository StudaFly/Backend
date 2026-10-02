from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_current_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.task import TaskRead
from src.app.services import timeline_service

router = APIRouter()


@router.get("/{mobility_id}/timeline", response_model=ResponseBase[list[TaskRead]])
async def get_timeline(
    mobility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[list[TaskRead]]:
    tasks = await timeline_service.get_timeline(
        db, user_id=current_user.id, mobility_id=mobility_id
    )
    return ResponseBase(data=tasks, message="Timeline generated successfully")
