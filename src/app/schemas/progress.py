import uuid

from src.app.schemas.common import StudaFlyBaseModel
from src.app.schemas.task import TaskRead


class CategoryProgress(StudaFlyBaseModel):
    category: str
    label: str
    done: int
    total: int


class MobilityProgress(StudaFlyBaseModel):
    mobility_id: uuid.UUID
    total_tasks: int
    completed_tasks: int
    percent: int
    days_until_departure: int
    overdue_tasks: int
    by_category: list[CategoryProgress]
    next_tasks: list[TaskRead]
