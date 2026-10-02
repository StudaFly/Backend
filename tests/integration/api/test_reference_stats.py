"""HTTP tests for /reference, /stats, /health and /mobilities/{id}/progress (services mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from src.app.main import app
from src.app.schemas.progress import MobilityProgress
from src.app.schemas.reference import PublicStats

client = TestClient(app, raise_server_exceptions=False)
PREFIX = "/api/v1"


def _patch_services(database: bool, cache: bool):
    return (
        patch(
            "src.app.core.services_status.check_database",
            new_callable=AsyncMock,
            return_value=database,
        ),
        patch(
            "src.app.core.services_status.check_cache", new_callable=AsyncMock, return_value=cache
        ),
    )


def test_health_is_reachable_under_the_api_prefix():
    db, cache = _patch_services(True, True)
    with db, cache:
        r = client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    assert r.json()["data"] == {"status": "healthy", "services": {"database": "ok", "cache": "ok"}}


def test_health_reports_unreachable_database_with_503():
    db, cache = _patch_services(False, True)
    with db, cache:
        r = client.get(f"{PREFIX}/health")
    assert r.status_code == 503
    error = r.json()["error"]
    assert error["code"] == "SERVICE_UNAVAILABLE"
    assert error["details"] == {"database": "unreachable", "cache": "ok"}
    assert "make services" in error["message"]


def test_reference_exposes_the_shared_labels():
    r = client.get(f"{PREFIX}/reference")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [t["key"] for t in data["mobilityTypes"]] == [
        "erasmus",
        "stage",
        "semestre",
        "double_diplome",
    ]
    assert {"key": "health", "label": "Santé"} in data["taskCategories"]
    assert data["taskPriorities"][0] == {"value": 1, "label": "Haute"}
    assert "🎓" in data["avatarEmojis"]


def test_reference_keys_match_the_api_enums():
    from typing import get_args

    from src.app.core import reference
    from src.app.schemas.mobility import MobilityType
    from src.app.schemas.task import TaskCategory

    assert [t["key"] for t in reference.MOBILITY_TYPES] == list(get_args(MobilityType))
    assert [c["key"] for c in reference.TASK_CATEGORIES] == sorted(
        get_args(TaskCategory), key=[c["key"] for c in reference.TASK_CATEGORIES].index
    )
    assert {c["key"] for c in reference.TASK_CATEGORIES} == set(get_args(TaskCategory))


def test_stats_returns_real_counts():
    stats = PublicStats(countries=24, destinations=38, students=3, preparation_steps=30)
    with patch(
        "src.app.services.stats_service.get_public_stats",
        new_callable=AsyncMock,
        return_value=stats,
    ):
        r = client.get(f"{PREFIX}/stats")
    assert r.status_code == 200
    assert r.json()["data"] == {
        "countries": 24,
        "destinations": 38,
        "students": 3,
        "preparationSteps": 30,
    }


def test_progress_requires_authentication():
    r = client.get(f"{PREFIX}/mobilities/{uuid.uuid4()}/progress")
    assert r.status_code == 401


def test_progress_returns_dashboard_figures():
    from src.app.core.dependencies import get_current_user

    user = MagicMock(id=uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: user
    mobility_id = uuid.uuid4()
    progress = MobilityProgress(
        mobility_id=mobility_id,
        total_tasks=20,
        completed_tasks=5,
        percent=25,
        days_until_departure=47,
        overdue_tasks=2,
        by_category=[],
        next_tasks=[],
    )
    try:
        with patch(
            "src.app.services.progress_service.get_progress",
            new_callable=AsyncMock,
            return_value=progress,
        ) as mock_progress:
            r = client.get(f"{PREFIX}/mobilities/{mobility_id}/progress")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()["data"]
    assert body["percent"] == 25
    assert body["daysUntilDeparture"] == 47
    assert body["overdueTasks"] == 2
    mock_progress.assert_awaited_once()
