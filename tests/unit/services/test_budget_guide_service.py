"""
Unit tests for budget_service.py and guide_service.py (reference data, no AI).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.app.core.exceptions import NotFoundError
from src.app.services import budget_service, guide_service

DESTINATION_ID = uuid.UUID("11111111-0001-0001-0001-000000000001")


def _destination(cost_of_living=None, guide_content=None):
    return SimpleNamespace(
        id=DESTINATION_ID,
        city="Barcelone",
        country="Espagne",
        cost_of_living=cost_of_living,
        guide_content=guide_content,
    )


def _db(destination):
    mock_db = AsyncMock()
    mock_db.get.return_value = destination
    return mock_db


COST = {
    "currency": "EUR",
    "monthly_budget": {"min": 900, "max": 1300},
    "rent": {"shared": 500, "studio": 850},
    "food": 280,
    "transport": 55,
    "misc": 160,
}

GUIDE = {
    "overview": "Ville méditerranéenne.",
    "housing": "Idealista, Fotocasa.",
    "transport": "T-Casual.",
    "tips": ["Mercadona est le moins cher", 42],
    "useful_contacts": {"urgences": "112", "police": "091"},
}


@pytest.mark.asyncio
async def test_budget_maps_reference_data():
    budget = await budget_service.get_budget_estimate(_db(_destination(COST)), DESTINATION_ID)

    assert budget.destination_id == DESTINATION_ID
    assert (budget.monthly_total_min, budget.monthly_total_max) == (900, 1300)
    lines = {c.key: (c.amount_min, c.amount_max) for c in budget.breakdown}
    assert lines == {
        "housing": (500, 850),
        "food": (280, 280),
        "transport": (55, 55),
        "leisure": (160, 160),
    }


@pytest.mark.asyncio
async def test_budget_totals_fall_back_to_breakdown_sum():
    cost = {k: v for k, v in COST.items() if k != "monthly_budget"}
    budget = await budget_service.get_budget_estimate(_db(_destination(cost)), DESTINATION_ID)
    assert budget.monthly_total_min == 500 + 280 + 55 + 160
    assert budget.monthly_total_max == 850 + 280 + 55 + 160


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", [None, _destination(cost_of_living=None)])
async def test_budget_not_found(destination):
    with pytest.raises(NotFoundError):
        await budget_service.get_budget_estimate(_db(destination), DESTINATION_ID)


@pytest.mark.asyncio
async def test_guide_maps_reference_data():
    guide = await guide_service.get_guide(_db(_destination(guide_content=GUIDE)), DESTINATION_ID)

    assert [s.key for s in guide.sections] == ["overview", "housing", "transport"]
    assert guide.sections[0].title == "Présentation"
    assert guide.tips == ["Mercadona est le moins cher"]
    assert guide.emergency_contacts == {"urgences": "112", "police": "091"}


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", [None, _destination(guide_content=None)])
async def test_guide_not_found(destination):
    with pytest.raises(NotFoundError):
        await guide_service.get_guide(_db(destination), DESTINATION_ID)
