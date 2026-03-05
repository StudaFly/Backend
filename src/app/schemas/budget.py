from pydantic import BaseModel


class BudgetCategory(BaseModel):
    label: str
    amount_min: float
    amount_max: float
    currency: str = "EUR"


class BudgetEstimate(BaseModel):
    destination_id: str
    city: str
    country: str
    monthly_total_min: float
    monthly_total_max: float
    currency: str = "EUR"
    breakdown: list[BudgetCategory]
    tips: list[str] = []
