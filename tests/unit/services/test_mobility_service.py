"""
Unit tests for mobility_service.create: the parcours is generated with the mobility.
"""

import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.app.core.exceptions import NotFoundError
from src.app.schemas.mobility import MobilityCreate
from src.app.services import mobility_service

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
DESTINATION_ID = uuid.UUID("11111111-0001-0001-0001-000000000001")

PAYLOAD = MobilityCreate(
    destination_id=DESTINATION_ID, type="erasmus", departure_date=date(2027, 1, 15)
)


def _db(destination):
    mock_db = AsyncMock()
    mock_db.get.return_value = destination
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()

    async def fake_refresh(obj):
        obj.id = obj.id or uuid.uuid4()
        obj.created_at = datetime(2026, 9, 30)

    mock_db.refresh.side_effect = fake_refresh
    return mock_db


@pytest.mark.asyncio
async def test_create_generates_parcours_in_same_transaction():
    destination = SimpleNamespace(id=DESTINATION_ID, city="Barcelone", country="Espagne")
    mock_db = _db(destination)
    generated = [MagicMock(), MagicMock()]

    with patch.object(
        mobility_service.task_generation_service,
        "build_tasks",
        new_callable=AsyncMock,
        return_value=generated,
    ) as mock_build:
        result = await mobility_service.create(mock_db, USER_ID, PAYLOAD)

    mock_db.flush.assert_awaited_once()
    mobility = mock_db.add.call_args.args[0]
    mock_build.assert_awaited_once_with(mobility, destination)
    mock_db.add_all.assert_called_once_with(generated)
    mock_db.commit.assert_awaited_once()
    assert result.status == "preparing"
    assert result.user_id == USER_ID


@pytest.mark.asyncio
async def test_create_with_unknown_destination_raises_not_found():
    mock_db = _db(None)
    with pytest.raises(NotFoundError):
        await mobility_service.create(mock_db, USER_ID, PAYLOAD)
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()
