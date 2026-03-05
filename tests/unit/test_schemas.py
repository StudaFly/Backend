"""
Unit tests for Pydantic schemas.
Verify input/output data validation:
required fields, types, constraints (e.g. minimum password length).
No external dependencies (no DB, no Redis).
"""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError
from src.app.schemas.budget import BudgetCategory, BudgetEstimate
from src.app.schemas.common import ErrorDetail, ErrorResponse, PaginatedResponse, ResponseBase
from src.app.schemas.guide import GuideContent, GuideSection
from src.app.schemas.mobility import MobilityCreate, MobilityUpdate
from src.app.schemas.task import TaskCreate, TaskUpdate
from src.app.schemas.user import UserCreate, UserUpdate


def test_user_create_valid():
    u = UserCreate(email="test@example.com", password="password123", name="Test User")
    assert u.email == "test@example.com"
    assert u.name == "Test User"


def test_user_create_password_too_short():
    with pytest.raises(ValidationError):
        UserCreate(email="test@example.com", password="short", name="Test")


def test_user_update():
    u = UserUpdate(name="Updated Name")
    assert u.name == "Updated Name"


def test_mobility_create():
    m = MobilityCreate(
        destination_id=uuid.uuid4(),
        type="erasmus",
        departure_date=date(2025, 9, 1),
    )
    assert m.type == "erasmus"
    assert m.return_date is None


def test_mobility_create_with_return_date():
    m = MobilityCreate(
        destination_id=uuid.uuid4(),
        type="stage",
        departure_date=date(2025, 6, 1),
        return_date=date(2025, 8, 31),
    )
    assert m.return_date == date(2025, 8, 31)


def test_mobility_update():
    u = MobilityUpdate(status="departed")
    assert u.status == "departed"


def test_task_create():
    t = TaskCreate(title="Get visa", category="admin", priority=1)
    assert t.title == "Get visa"
    assert t.priority == 1


def test_task_update():
    u = TaskUpdate(is_completed=True)
    assert u.is_completed is True


def test_budget_estimate():
    b = BudgetEstimate(
        destination_id="some-id",
        city="Berlin",
        country="Germany",
        monthly_total_min=800.0,
        monthly_total_max=1200.0,
        breakdown=[BudgetCategory(label="Rent", amount_min=400.0, amount_max=600.0)],
    )
    assert b.city == "Berlin"
    assert len(b.breakdown) == 1


def test_guide_content():
    g = GuideContent(
        destination_id="some-id",
        city="Madrid",
        country="Spain",
        sections=[GuideSection(title="Culture", content="Friendly people.")],
    )
    assert g.city == "Madrid"
    assert g.sections[0].title == "Culture"


def test_response_base():
    r = ResponseBase(data={"key": "value"})
    assert r.data == {"key": "value"}
    assert r.message == "OK"


def test_paginated_response():
    p = PaginatedResponse(data=[], total=0, page=1, per_page=10)
    assert p.total == 0
    assert p.data == []


def test_error_response():
    e = ErrorResponse(error=ErrorDetail(code="NOT_FOUND", message="Resource not found"))
    assert e.error.code == "NOT_FOUND"
