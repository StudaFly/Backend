"""
Unit tests for checklist_service.py.
DB session and ai_service are fully mocked — no real DB or Claude API calls.
"""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MOBILITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
TASK_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")


def _make_destination():
    return SimpleNamespace(city="Berlin", country="Germany")


def _make_mobility(user_id=USER_ID):
    return SimpleNamespace(
        id=MOBILITY_ID,
        user_id=user_id,
        type="stage",
        departure_date=date(2025, 6, 15),
        destination=_make_destination(),
    )


def _make_task_orm(user_id=USER_ID):
    return SimpleNamespace(
        id=TASK_ID,
        mobility_id=MOBILITY_ID,
        title="Get passport",
        description="Renew if needed",
        category="admin",
        deadline=date(2025, 3, 22),
        is_completed=False,
        priority=2,
        mobility=_make_mobility(user_id=user_id),
    )


@pytest.mark.asyncio
async def test_list_tasks_ensures_parcours_then_returns_tasks():
    from src.app.services import checklist_service

    mobility = _make_mobility()
    existing_task = _make_task_orm()

    mobility_result = MagicMock()
    mobility_result.scalar_one_or_none.return_value = mobility
    tasks_result = MagicMock()
    tasks_result.scalars.return_value.all.return_value = [existing_task]

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [mobility_result, tasks_result]

    with patch(
        "src.app.services.checklist_service.task_generation_service.ensure_tasks",
        new_callable=AsyncMock,
    ) as mock_ensure:
        result = await checklist_service.list_tasks(mock_db, USER_ID, MOBILITY_ID)

    mock_ensure.assert_awaited_once_with(mock_db, mobility)
    assert len(result) == 1
    assert result[0].title == "Get passport"


@pytest.mark.asyncio
async def test_list_tasks_raises_not_found():
    from src.app.core.exceptions import NotFoundError
    from src.app.services import checklist_service

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = r

    with pytest.raises(NotFoundError):
        await checklist_service.list_tasks(mock_db, USER_ID, MOBILITY_ID)


@pytest.mark.asyncio
async def test_list_tasks_raises_forbidden():
    from src.app.core.exceptions import ForbiddenError
    from src.app.services import checklist_service

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = _make_mobility(user_id=OTHER_USER_ID)
    mock_db.execute.return_value = r

    with pytest.raises(ForbiddenError):
        await checklist_service.list_tasks(mock_db, USER_ID, MOBILITY_ID)


@pytest.mark.asyncio
async def test_create_task_success():
    from src.app.schemas.task import TaskCreate
    from src.app.services import checklist_service

    mobility = _make_mobility()
    new_task = _make_task_orm()
    new_task.title = "Custom task"
    new_task.description = None
    new_task.deadline = None
    new_task.priority = 1

    mobility_result = MagicMock()
    mobility_result.scalar_one_or_none.return_value = mobility

    mock_db = AsyncMock()
    mock_db.execute.return_value = mobility_result
    mock_db.refresh.side_effect = lambda obj: None

    with patch("src.app.services.checklist_service.Task", return_value=new_task):
        payload = TaskCreate(title="Custom task", category="admin", priority=1)
        await checklist_service.create_task(mock_db, USER_ID, MOBILITY_ID, payload)

    mock_db.add.assert_called_once_with(new_task)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_success():
    from src.app.schemas.task import TaskUpdate
    from src.app.services import checklist_service

    task = _make_task_orm()

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = r
    mock_db.refresh.side_effect = lambda obj: None

    payload = TaskUpdate(title="Updated title")
    await checklist_service.update_task(mock_db, USER_ID, TASK_ID, payload)

    assert task.title == "Updated title"
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_forbidden():
    from src.app.core.exceptions import ForbiddenError
    from src.app.schemas.task import TaskUpdate
    from src.app.services import checklist_service

    task = _make_task_orm(user_id=OTHER_USER_ID)

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = r

    with pytest.raises(ForbiddenError):
        await checklist_service.update_task(mock_db, USER_ID, TASK_ID, TaskUpdate(title="x"))


@pytest.mark.asyncio
async def test_complete_task_sets_flag():
    from src.app.services import checklist_service

    task = _make_task_orm()
    task.is_completed = False

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = r
    mock_db.refresh.side_effect = lambda obj: None

    await checklist_service.complete_task(mock_db, USER_ID, TASK_ID)

    assert task.is_completed is True
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_task_success():
    from src.app.services import checklist_service

    task = _make_task_orm()

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = r

    await checklist_service.delete_task(mock_db, USER_ID, TASK_ID)

    mock_db.delete.assert_called_once_with(task)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_task_forbidden():
    from src.app.core.exceptions import ForbiddenError
    from src.app.services import checklist_service

    task = _make_task_orm(user_id=OTHER_USER_ID)

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = r

    with pytest.raises(ForbiddenError):
        await checklist_service.delete_task(mock_db, USER_ID, TASK_ID)


@pytest.mark.asyncio
async def test_delete_task_not_found():
    from src.app.core.exceptions import NotFoundError
    from src.app.services import checklist_service

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = r

    with pytest.raises(NotFoundError):
        await checklist_service.delete_task(mock_db, USER_ID, TASK_ID)
