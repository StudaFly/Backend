"""
Unit tests for AI prompts.
Verify that each build() function generates a prompt containing
the expected parameters (destination, mobility type, date).
No Claude API calls — purely local tests.
"""

from src.app.services.ai.prompts import base, budget, checklist, day_zero, guide, timeline


def test_build_context():
    result = base.build_context("Barcelona", "erasmus", "2025-09-01")
    assert "Barcelona" in result
    assert "erasmus" in result
    assert "2025-09-01" in result


def test_format_response():
    result = base.format_response("  hello world  ")
    assert result == "hello world"


def test_checklist_build():
    result = checklist.build("Berlin", "stage", "2025-06-15")
    assert "Berlin" in result
    assert "stage" in result
    assert checklist.SYSTEM != ""


def test_timeline_build():
    result = timeline.build("Madrid", "erasmus", "2025-09-01")
    assert "Madrid" in result
    assert "erasmus" in result
    assert timeline.SYSTEM != ""


def test_budget_build():
    result = budget.build("Rome", "Italy")
    assert "Rome" in result
    assert "Italy" in result
    assert budget.SYSTEM != ""


def test_guide_build():
    result = guide.build("Lisbon", "Portugal")
    assert "Lisbon" in result
    assert "Portugal" in result
    assert guide.SYSTEM != ""


def test_day_zero_build():
    result = day_zero.build("Amsterdam", "Netherlands", "stage")
    assert "Amsterdam" in result
    assert "Netherlands" in result
    assert day_zero.SYSTEM != ""
