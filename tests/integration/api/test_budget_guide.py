"""
HTTP tests for GET /destinations/{id}/budget and /guide (service mocked, no DB).
"""

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from src.app.core.exceptions import NotFoundError
from src.app.main import app
from src.app.schemas.budget import BudgetCategory, BudgetEstimate
from src.app.schemas.guide import GuideContent, GuideSection

client = TestClient(app, raise_server_exceptions=False)

PREFIX = "/api/v1"
DESTINATION_ID = uuid.UUID("11111111-0001-0001-0001-000000000001")


def test_get_budget_returns_camel_case_payload():
    budget = BudgetEstimate(
        destination_id=DESTINATION_ID,
        city="Barcelone",
        country="Espagne",
        monthly_total_min=900,
        monthly_total_max=1300,
        breakdown=[BudgetCategory(key="food", label="Nourriture", amount_min=280, amount_max=280)],
    )
    with patch(
        "src.app.services.budget_service.get_budget_estimate",
        new_callable=AsyncMock,
        return_value=budget,
    ):
        r = client.get(f"{PREFIX}/destinations/{DESTINATION_ID}/budget")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["monthlyTotalMin"] == 900
    assert data["breakdown"][0]["amountMax"] == 280


def test_get_guide_returns_sections():
    guide = GuideContent(
        destination_id=DESTINATION_ID,
        city="Barcelone",
        country="Espagne",
        sections=[GuideSection(key="overview", title="Présentation", content="...")],
        emergency_contacts={"urgences": "112"},
    )
    with patch(
        "src.app.services.guide_service.get_guide",
        new_callable=AsyncMock,
        return_value=guide,
    ):
        r = client.get(f"{PREFIX}/destinations/{DESTINATION_ID}/guide")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["sections"][0]["key"] == "overview"
    assert data["emergencyContacts"] == {"urgences": "112"}


def test_get_budget_unknown_destination_returns_404():
    with patch(
        "src.app.services.budget_service.get_budget_estimate",
        new_callable=AsyncMock,
        side_effect=NotFoundError("Destination not found"),
    ):
        r = client.get(f"{PREFIX}/destinations/{DESTINATION_ID}/budget")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_get_guide_invalid_uuid_returns_422():
    r = client.get(f"{PREFIX}/destinations/not-a-uuid/guide")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
