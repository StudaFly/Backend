import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel

TaskCategory = Literal["admin", "finance", "housing", "health", "practical"]


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    category: TaskCategory
    deadline: date | None = None
    priority: int = 0


class TaskRead(BaseModel):
    id: uuid.UUID
    mobility_id: uuid.UUID
    title: str
    description: str | None
    category: str
    deadline: date | None
    is_completed: bool
    priority: int

    model_config = {"from_attributes": True}


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: TaskCategory | None = None
    deadline: date | None = None
    priority: int | None = None
    is_completed: bool | None = None
