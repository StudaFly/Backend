"""
Unit tests for timeline_service.py.
DB session and the parcours generation are mocked — no real DB or Claude API calls.
"""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MOBILITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _make_mobility(user_id=USER_ID):
    return SimpleNamespace(
        id=MOBILITY_ID,
        user_id=user_id,
        type="erasmus",
        departure_date=date(2025, 9, 1),
        destination=SimpleNamespace(city="Barcelone", country="Espagne"),
    )


def _make_task(title="Apply for Erasmus", category="admin", deadline=date(2025, 6, 1)):
    return SimpleNamespace(
        id=uuid.uuid4(),
        mobility_id=MOBILITY_ID,
        title=title,
        description="Submit your application",
        category=category,
        deadline=deadline,
        is_completed=False,
        priority=1,
    )


def _make_db(mobility, tasks):
    mobility_result = MagicMock()
    mobility_result.scalar_one_or_none.return_value = mobility
    tasks_result = MagicMock()
    tasks_result.scalars.return_value.all.return_value = tasks
    mock_db = AsyncMock()
    mock_db.execute.side_effect = [mobility_result, tasks_result]
    return mock_db


@pytest.mark.asyncio
async def test_get_timeline_ensures_parcours_then_returns_tasks():
    from src.app.services import timeline_service

    mobility = _make_mobility()
    tasks = [_make_task(), _make_task(title="Book flights", category="practical")]
    mock_db = _make_db(mobility, tasks)

    with patch(
        "src.app.services.timeline_service.task_generation_service.ensure_tasks",
        new_callable=AsyncMock,
    ) as mock_ensure:
        result = await timeline_service.get_timeline(mock_db, USER_ID, MOBILITY_ID)

    mock_ensure.assert_awaited_once_with(mock_db, mobility)
    assert [t.title for t in result] == ["Apply for Erasmus", "Book flights"]


@pytest.mark.asyncio
async def test_get_timeline_raises_not_found():
    from src.app.core.exceptions import NotFoundError
    from src.app.services import timeline_service

    mock_db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = result_mock

    with pytest.raises(NotFoundError):
        await timeline_service.get_timeline(mock_db, USER_ID, MOBILITY_ID)


@pytest.mark.asyncio
async def test_get_timeline_raises_forbidden_for_wrong_user():
    from src.app.core.exceptions import ForbiddenError
    from src.app.services import timeline_service

    mock_db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = _make_mobility(user_id=OTHER_USER_ID)
    mock_db.execute.return_value = result_mock

    with (
        patch(
            "src.app.services.timeline_service.task_generation_service.ensure_tasks",
            new_callable=AsyncMock,
        ) as mock_ensure,
        pytest.raises(ForbiddenError),
    ):
        await timeline_service.get_timeline(mock_db, USER_ID, MOBILITY_ID)
    mock_ensure.assert_not_awaited()
