from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import get_current_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.schemas.common import ResponseBase
from src.app.schemas.notification import (
    NotificationList,
    NotificationRead,
    PushTokenRegister,
    ReadAllResult,
    UnreadCount,
)
from src.app.services import notification_service

router = APIRouter()


@router.get("", response_model=ResponseBase[NotificationList])
async def list_notifications(
    unread_only: bool = Query(False, alias="unreadOnly"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[NotificationList]:
    notifications = await notification_service.list_notifications(
        db, current_user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return ResponseBase(data=notifications, message="Notifications retrieved successfully")


@router.get("/unread-count", response_model=ResponseBase[UnreadCount])
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[UnreadCount]:
    count = await notification_service.unread_count(db, current_user.id)
    return ResponseBase(data=UnreadCount(count=count))


@router.post("/read-all", response_model=ResponseBase[ReadAllResult])
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[ReadAllResult]:
    updated = await notification_service.mark_all_read(db, current_user.id)
    return ResponseBase(data=ReadAllResult(updated=updated), message="All notifications read")


@router.post("/push-tokens", status_code=204)
async def register_push_token(
    payload: PushTokenRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await notification_service.register_push_token(
        db, current_user.id, payload.token, payload.platform
    )


@router.delete("/push-tokens", status_code=204)
async def unregister_push_token(
    token: str = Query(min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await notification_service.unregister_push_token(db, current_user.id, token)


@router.patch("/{notification_id}/read", response_model=ResponseBase[NotificationRead])
async def mark_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResponseBase[NotificationRead]:
    notification = await notification_service.mark_read(db, current_user.id, notification_id)
    return ResponseBase(data=notification, message="Notification marked as read")


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await notification_service.delete_notification(db, current_user.id, notification_id)
