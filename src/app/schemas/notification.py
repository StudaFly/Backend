import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from src.app.models.enums import PushPlatform
from src.app.schemas.common import StrictInput, StudaFlyBaseModel


class NotificationRead(StudaFlyBaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    data: dict[str, Any]
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationList(StudaFlyBaseModel):
    items: list[NotificationRead]
    unread_count: int


class UnreadCount(StudaFlyBaseModel):
    count: int


class ReadAllResult(StudaFlyBaseModel):
    updated: int


class PushTokenRegister(StrictInput):
    # Expo tokens look like "ExponentPushToken[xxxxxxxx]".
    token: str = Field(min_length=10, max_length=255, pattern=r"^Expo(nent)?PushToken\[.+\]$")
    platform: PushPlatform
