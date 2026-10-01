import uuid

from src.app.schemas.common import StudaFlyBaseModel


class BudgetCategory(StudaFlyBaseModel):
    key: str
    label: str
    amount_min: float
    amount_max: float
    currency: str = "EUR"


class BudgetEstimate(StudaFlyBaseModel):
    destination_id: uuid.UUID
    city: str
    country: str
    monthly_total_min: float
    monthly_total_max: float
    currency: str = "EUR"
    breakdown: list[BudgetCategory]
    tips: list[str] = []
