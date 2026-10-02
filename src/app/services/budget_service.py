from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import NotFoundError
from src.app.models.destination import Destination
from src.app.schemas.budget import BudgetCategory, BudgetEstimate


def _number(value) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _range(value) -> tuple[float, float]:
    if isinstance(value, dict):
        low, high = _number(value.get("min")), _number(value.get("max"))
        return (low or high, high or low)
    amount = _number(value)
    return amount, amount


def _rent_range(rent) -> tuple[float, float]:
    if isinstance(rent, dict) and ("shared" in rent or "studio" in rent):
        low = _number(rent.get("shared") or rent.get("studio"))
        high = _number(rent.get("studio") or rent.get("shared"))
        return low, high
    return _range(rent)


async def get_budget_estimate(db: AsyncSession, destination_id: UUID) -> BudgetEstimate:
    destination = await db.get(Destination, destination_id)
    if not destination:
        raise NotFoundError("Destination not found")
    cost = destination.cost_of_living
    if not cost:
        raise NotFoundError("No budget data available for this destination")

    currency = cost.get("currency", "EUR")
    lines = [
        ("housing", "Logement", _rent_range(cost.get("rent"))),
        ("food", "Nourriture", _range(cost.get("food"))),
        ("transport", "Transport", _range(cost.get("transport"))),
        ("leisure", "Loisirs et divers", _range(cost.get("misc"))),
    ]
    breakdown = [
        BudgetCategory(key=key, label=label, amount_min=low, amount_max=high, currency=currency)
        for key, label, (low, high) in lines
    ]

    total_min, total_max = _range(cost.get("monthly_budget"))
    return BudgetEstimate(
        destination_id=destination.id,
        city=destination.city,
        country=destination.country,
        monthly_total_min=total_min or sum(c.amount_min for c in breakdown),
        monthly_total_max=total_max or sum(c.amount_max for c in breakdown),
        currency=currency,
        breakdown=breakdown,
    )
