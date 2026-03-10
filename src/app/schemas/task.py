import uuid
from datetime import date
from typing import Literal

from src.app.schemas.common import StudaFlyBaseModel

TaskCategory = Literal["admin", "finance", "housing", "health", "practical"]


class TaskCreate(StudaFlyBaseModel):
    title: str
    description: str | None = None
    category: TaskCategory
    deadline: date | None = None
    priority: int = 0


class TaskRead(StudaFlyBaseModel):
    id: uuid.UUID
    mobility_id: uuid.UUID
    title: str
    description: str | None
    category: str
    deadline: date | None
    is_completed: bool
    priority: int


class TaskUpdate(StudaFlyBaseModel):
    title: str | None = None
    description: str | None = None
    category: TaskCategory | None = None
    deadline: date | None = None
    priority: int | None = None
    is_completed: bool | None = None
