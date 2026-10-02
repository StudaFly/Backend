"""
Unit tests for task_generation_service.py (parcours generation).
Templates are the real JSON file; the AI and the DB session are mocked.
"""

import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.app.services import task_generation_service as svc

MOBILITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TODAY = date(2026, 9, 30)
DEPARTURE = date(2027, 6, 1)


def _titles(tasks):
    return {t.title for t in tasks}


def _build(mobility_type="erasmus", country="Espagne", departure=DEPARTURE, today=TODAY):
    return svc.build_template_tasks(MOBILITY_ID, mobility_type, departure, country, today=today)


def _mobility(mobility_type="erasmus"):
    return SimpleNamespace(id=MOBILITY_ID, type=mobility_type, departure_date=DEPARTURE)


def _destination(country="Espagne"):
    return SimpleNamespace(city="Barcelone", country=country)


def test_template_file_is_consistent():
    data = svc.load_templates()
    valid_types = {"erasmus", "stage", "semestre", "double_diplome"}
    for task in data["tasks"]:
        assert task["title"].strip()
        assert task["category"] in svc.VALID_CATEGORIES
        assert task["priority"] in (1, 2, 3)
        assert isinstance(task["days_before_departure"], int)
        assert set(task.get("mobility_types", [])) <= valid_types
        assert task.get("zone") in (None, "eu", "non_eu")


@pytest.mark.parametrize("mobility_type", ["erasmus", "stage", "semestre", "double_diplome"])
def test_every_mobility_type_gets_a_base_parcours(mobility_type):
    tasks = _build(mobility_type)
    assert 15 <= len(tasks) <= 22
    assert all(t.mobility_id == MOBILITY_ID and t.is_completed is False for t in tasks)
    assert {t.category for t in tasks} <= svc.VALID_CATEGORIES


def test_tasks_are_adapted_to_mobility_type():
    erasmus = _titles(_build("erasmus"))
    stage = _titles(_build("stage"))
    assert "Signer le contrat pédagogique (Learning Agreement)" in erasmus
    assert "Signer le contrat pédagogique (Learning Agreement)" not in stage
    assert "Signer la convention de stage" in stage
    assert "Signer la convention de stage" not in erasmus


def test_tasks_are_adapted_to_destination_zone():
    eu = _titles(_build(country="Espagne"))
    non_eu = _titles(_build(country="Canada"))
    ceam = "Demander la carte européenne d'assurance maladie (CEAM)"
    visa = "Déposer la demande de visa"
    assert ceam in eu and visa not in eu
    assert visa in non_eu and ceam not in non_eu


def test_deadlines_are_computed_from_departure_date():
    tasks = {t.title: t for t in _build()}
    passport = tasks["Vérifier la validité du passeport ou de la carte d'identité"]
    arrival = tasks["Accomplir les formalités d'arrivée"]
    assert passport.deadline == date(2027, 1, 2)
    assert arrival.deadline == date(2027, 6, 8)


def test_compute_deadline_regular_case():
    assert svc.compute_deadline(date(2027, 6, 1), 30, TODAY) == date(2027, 5, 2)


def test_compute_deadline_late_signup_is_due_today():
    assert svc.compute_deadline(date(2026, 10, 30), 90, TODAY) == TODAY


def test_compute_deadline_after_arrival_is_not_clamped():
    assert svc.compute_deadline(date(2026, 10, 30), -7, TODAY) == date(2026, 11, 6)


def test_compute_deadline_past_departure_is_not_clamped():
    assert svc.compute_deadline(date(2026, 1, 1), 30, TODAY) == date(2025, 12, 2)


AI_JSON = json.dumps(
    {
        "tasks": [
            {
                "title": "Get passport",
                "category": "admin",
                "priority": 5,
                "deadline_weeks_before": 2,
            },
            {"title": "Weird category", "category": "unknown", "priority": 1},
            {"title": "  ", "category": "admin"},
        ]
    }
)


@pytest.mark.asyncio
async def test_build_tasks_uses_templates_when_ai_disabled():
    with (
        patch.object(svc.settings, "AI_TASK_GENERATION_ENABLED", False),
        patch.object(svc.ai_service, "generate_checklist", new_callable=AsyncMock) as mock_ai,
    ):
        tasks = await svc.build_tasks(_mobility(), _destination())
    mock_ai.assert_not_called()
    assert "Trouver un logement" in _titles(tasks)


@pytest.mark.asyncio
async def test_build_tasks_uses_ai_when_enabled():
    with (
        patch.object(svc.settings, "AI_TASK_GENERATION_ENABLED", True),
        patch.object(
            svc.ai_service, "generate_checklist", new_callable=AsyncMock, return_value=AI_JSON
        ),
    ):
        tasks = await svc.build_tasks(_mobility(), _destination())
    assert [t.title for t in tasks] == ["Get passport", "Weird category"]
    assert tasks[0].priority == 3
    assert tasks[0].deadline == date(2027, 5, 18)
    assert tasks[1].category == "practical"
    assert tasks[1].deadline is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ai_mock",
    [
        AsyncMock(side_effect=RuntimeError("credit balance is too low")),
        AsyncMock(return_value="not json at all"),
        AsyncMock(return_value='{"tasks": []}'),
    ],
)
async def test_build_tasks_falls_back_to_templates(ai_mock):
    with (
        patch.object(svc.settings, "AI_TASK_GENERATION_ENABLED", True),
        patch.object(svc.ai_service, "generate_checklist", ai_mock),
    ):
        tasks = await svc.build_tasks(_mobility(), _destination())
    assert "Trouver un logement" in _titles(tasks)


@pytest.mark.asyncio
async def test_ensure_tasks_does_nothing_when_tasks_exist():
    mock_db = AsyncMock()
    mock_db.scalar.return_value = 12
    mock_db.add_all = MagicMock()
    mobility = _mobility()
    mobility.destination = _destination()

    await svc.ensure_tasks(mock_db, mobility)

    mock_db.add_all.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_tasks_generates_parcours_when_empty():
    mock_db = AsyncMock()
    mock_db.scalar.return_value = 0
    mock_db.add_all = MagicMock()
    mobility = _mobility()
    mobility.destination = _destination()

    with patch.object(svc.settings, "AI_TASK_GENERATION_ENABLED", False):
        await svc.ensure_tasks(mock_db, mobility)

    added = mock_db.add_all.call_args.args[0]
    assert len(added) >= 15
    mock_db.commit.assert_awaited_once()
