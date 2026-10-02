"""Destination profiles: seed data (ex front mock) and how they are applied / served."""

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.app.schemas.mobility import MobilityRead
from src.app.services import budget_service, destination_service, guide_service

PROFILES = json.loads(
    (Path(__file__).parents[2] / "seeds" / "data" / "destination_profiles.json").read_text()
)


def test_profiles_are_complete():
    assert len(PROFILES) == 13
    for profile in PROFILES:
        assert profile["cities"] and profile["image_url"].startswith("https://")
        assert profile["summary"]
        assert set(profile["facts"]) == {
            "language",
            "currency",
            "climate",
            "visa_required",
            "international_students",
        }
        assert (
            profile["cost_of_living"]["monthly_budget"]["min"]
            <= profile["cost_of_living"]["monthly_budget"]["max"]
        )
        assert len(profile["key_steps"]) == 3


def test_profiles_keep_the_decided_city_mapping():
    cities = {p["country"]: p["cities"] for p in PROFILES}
    assert cities["États-Unis"] == ["New York", "Los Angeles", "San Francisco"]
    assert cities["France"] == ["Marseille"]
    assert cities["Canada"] == ["Montréal", "Toronto"]


def test_seed_apply_profile_fills_gaps_only_without_force():
    from seeds.seed import _apply_profile

    profile = PROFILES[0]
    destination = SimpleNamespace(
        image_url="custom.jpg", summary=None, facts=None, guide_content={"overview": "x"}
    )

    assert _apply_profile(destination, profile, force=False) is True
    assert destination.image_url == "custom.jpg"
    assert destination.summary == profile["summary"]
    assert destination.guide_content["key_steps"] == profile["key_steps"]
    assert destination.guide_content["overview"] == "x"
    assert _apply_profile(destination, profile, force=False) is False


def _destination(**overrides):
    base = {
        "id": uuid.uuid4(),
        "city": "Londres",
        "country": "Royaume-Uni",
        "image_url": "https://img",
        "summary": "Résumé",
        "facts": {"language": "Anglais", "visa_required": True, "international_students": 32000},
        "cost_of_living": None,
        "guide_content": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _db(destination):
    db = AsyncMock()
    db.get.return_value = destination
    return db


@pytest.mark.asyncio
async def test_destination_detail_exposes_profile_and_availability():
    detail = await destination_service.get_by_id(
        _db(_destination(cost_of_living={"a": 1})), uuid.uuid4()
    )
    assert detail.facts.visa_required is True
    assert detail.facts.international_students == 32000
    assert detail.has_budget is True and detail.has_guide is False


@pytest.mark.asyncio
async def test_budget_supports_country_ranges_and_currency():
    cost = {
        "currency": "GBP",
        "monthly_budget": {"min": 1130, "max": 2050},
        "rent": {"min": 600, "max": 1100},
        "food": {"min": 250, "max": 400},
        "transport": {"min": 80, "max": 150},
        "misc": {"min": 200, "max": 400},
    }
    budget = await budget_service.get_budget_estimate(
        _db(_destination(cost_of_living=cost)), uuid.uuid4()
    )
    assert budget.currency == "GBP"
    assert (budget.monthly_total_min, budget.monthly_total_max) == (1130, 2050)
    assert [(c.key, c.amount_min, c.amount_max) for c in budget.breakdown] == [
        ("housing", 600, 1100),
        ("food", 250, 400),
        ("transport", 80, 150),
        ("leisure", 200, 400),
    ]


@pytest.mark.asyncio
async def test_guide_exposes_key_steps():
    steps = [{"title": "Visa", "description": "Student Visa", "timing": "-4 mois"}]
    guide = await guide_service.get_guide(
        _db(_destination(guide_content={"overview": "Londres", "key_steps": steps})), uuid.uuid4()
    )
    assert [s.title for s in guide.key_steps] == ["Visa"]


def test_mobility_read_computes_countdown_and_stay_length():
    mobility = MobilityRead(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        destination_id=uuid.uuid4(),
        type="erasmus",
        departure_date=date.today(),
        return_date=None,
        status="preparing",
        created_at=datetime.now(),
    )
    assert mobility.days_until_departure == 0
    assert mobility.stay_months is None
    dumped = mobility.model_dump(by_alias=True)
    assert "daysUntilDeparture" in dumped and "stayMonths" in dumped
