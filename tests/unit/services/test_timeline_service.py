"""
Unit tests for timeline_service.py.
DB session and ai_service are fully mocked — no real DB or Claude API calls.
"""

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MOBILITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

TIMELINE_JSON = json.dumps(
    {
        "milestones": [
            {
                "title": "Apply for Erasmus",
                "deadline": "2025-06-01",
                "category": "admin",
                "description": "Submit your application",
            },
            {
                "title": "Book flights",
                "deadline": "2025-07-15",
                "category": "practical",
                "description": "Round trip",
            },
        ]
    }
)


def _make_destination():
    dest = MagicMock()
    dest.city = "Barcelona"
    dest.country = "Spain"
    return dest


def _make_mobility(user_id=USER_ID, has_tasks=False):
    mobility = MagicMock()
    mobility.id = MOBILITY_ID
    mobility.user_id = user_id
    mobility.type = "erasmus"
    mobility.departure_date = date(2025, 9, 1)
    mobility.destination = _make_destination()
    mobility.tasks = [MagicMock()] if has_tasks else []
    return mobility


def _make_task(title="Apply for Erasmus", category="admin", deadline=date(2025, 6, 1)):
    task = MagicMock()
    task.id = uuid.uuid4()
    task.mobility_id = MOBILITY_ID
    task.title = title
    task.description = "Submit your application"
    task.category = category
    task.deadline = deadline
    task.is_completed = False
    task.priority = 1
    return task


def _make_db(mobility, tasks):
    mobility_result = MagicMock()
    mobility_result.scalar_one_or_none.return_value = mobility

    tasks_result = MagicMock()
    tasks_result.scalars.return_value.all.return_value = tasks

    call_count = {"n": 0}

    async def side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return mobility_result
        return tasks_result

    mock_db = AsyncMock()
    mock_db.execute.side_effect = side_effect
    return mock_db


@pytest.mark.asyncio
async def test_get_timeline_generates_tasks_on_empty_mobility():
    from src.app.services import timeline_service

    mobility = _make_mobility(has_tasks=False)
    tasks = [_make_task()]
    mock_db = _make_db(mobility, tasks)

    with patch(
        "src.app.services.timeline_service.ai_service.generate_timeline",
        new_callable=AsyncMock,
        return_value=TIMELINE_JSON,
    ):
        result = await timeline_service.get_timeline(mock_db, USER_ID, MOBILITY_ID)

    mock_db.add.assert_called()
    mock_db.commit.assert_called()
    assert len(result) == 1
    assert result[0].title == "Apply for Erasmus"


@pytest.mark.asyncio
async def test_get_timeline_reuses_existing_tasks():
    from src.app.services import timeline_service

    mobility = _make_mobility(has_tasks=True)
    tasks = [_make_task(), _make_task(title="Book flights", category="practical")]
    mock_db = _make_db(mobility, tasks)

    with patch(
        "src.app.services.timeline_service.ai_service.generate_timeline",
        new_callable=AsyncMock,
    ) as mock_ai:
        result = await timeline_service.get_timeline(mock_db, USER_ID, MOBILITY_ID)

    mock_ai.assert_not_called()
    mock_db.add.assert_not_called()
    assert len(result) == 2


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

    mobility = _make_mobility(user_id=OTHER_USER_ID)
    mock_db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mobility
    mock_db.execute.return_value = result_mock

    with pytest.raises(ForbiddenError):
        await timeline_service.get_timeline(mock_db, USER_ID, MOBILITY_ID)


@pytest.mark.asyncio
async def test_get_timeline_handles_invalid_ai_json():
    from src.app.services import timeline_service

    mobility = _make_mobility(has_tasks=False)
    tasks = []
    mock_db = _make_db(mobility, tasks)

    with patch(
        "src.app.services.timeline_service.ai_service.generate_timeline",
        new_callable=AsyncMock,
        return_value="not valid json {{{{",
    ):
        result = await timeline_service.get_timeline(mock_db, USER_ID, MOBILITY_ID)

    mock_db.add.assert_not_called()
    assert result == []
