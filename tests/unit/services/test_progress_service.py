"""Unit tests for progress_service.compute_progress (dashboard figures computed by the API)."""

import uuid
from datetime import date
from types import SimpleNamespace

from src.app.services.progress_service import compute_progress

TODAY = date(2026, 9, 30)
MOBILITY = SimpleNamespace(id=uuid.uuid4(), departure_date=date(2026, 11, 16))


def _task(title, category, deadline, done=False, priority=1):
    return SimpleNamespace(
        id=uuid.uuid4(),
        mobility_id=MOBILITY.id,
        title=title,
        description=None,
        category=category,
        deadline=deadline,
        is_completed=done,
        priority=priority,
    )


TASKS = [
    _task("Passeport", "admin", date(2026, 9, 1), done=True),
    _task("Visa", "admin", date(2026, 9, 20)),  # overdue
    _task("Logement", "housing", date(2026, 10, 5)),
    _task("Banque", "finance", date(2026, 10, 20)),
    _task("Bagages", "practical", date(2026, 11, 13)),
    _task("Sans date", "practical", None),
]


def test_counts_percent_and_countdown():
    progress = compute_progress(MOBILITY, TASKS, TODAY)
    assert progress.total_tasks == 6
    assert progress.completed_tasks == 1
    assert progress.percent == 17
    assert progress.days_until_departure == 47
    assert progress.overdue_tasks == 1


def test_next_tasks_are_the_three_first_pending_with_deadline():
    progress = compute_progress(MOBILITY, TASKS, TODAY)
    assert [t.title for t in progress.next_tasks] == ["Visa", "Logement", "Banque"]


def test_by_category_follows_reference_order_and_skips_empty():
    progress = compute_progress(MOBILITY, TASKS, TODAY)
    assert [(c.category, c.label, c.done, c.total) for c in progress.by_category] == [
        ("admin", "Admin", 1, 2),
        ("finance", "Finance", 0, 1),
        ("housing", "Logement", 0, 1),
        ("practical", "Pratique", 0, 2),
    ]


def test_empty_parcours():
    progress = compute_progress(MOBILITY, [], TODAY)
    assert progress.percent == 0
    assert progress.next_tasks == []
    assert progress.by_category == []
