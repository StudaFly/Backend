import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, computed_field

from src.app.schemas.common import StudaFlyBaseModel

TaskCategory = Literal["admin", "finance", "housing", "health", "practical"]
TaskPriority = Annotated[int, Field(ge=1, le=3)]


class TaskCreate(StudaFlyBaseModel):
    title: str
    description: str | None = None
    category: TaskCategory
    deadline: date | None = None
    priority: TaskPriority = 2


class TaskRead(StudaFlyBaseModel):
    id: uuid.UUID
    mobility_id: uuid.UUID
    title: str
    description: str | None
    category: str
    deadline: date | None
    is_completed: bool
    priority: int

    @computed_field(alias="daysUntilDeadline")
    @property
    def days_until_deadline(self) -> int | None:
        return (self.deadline - date.today()).days if self.deadline else None


class TaskUpdate(StudaFlyBaseModel):
    title: str | None = None
    description: str | None = None
    category: TaskCategory | None = None
    deadline: date | None = None
    priority: TaskPriority | None = None
    is_completed: bool | None = None
