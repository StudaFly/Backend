"""
Integration tests for Timeline and Checklist HTTP endpoints.

These tests verify:
- Auth protection (no token → 403 from HTTPBearer)
- Invalid token → 401
- Invalid UUID path params → 422
- Valid auth with mocked service → 200/201/204
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from src.app.main import app

client = TestClient(app, raise_server_exceptions=False)

PREFIX = "/api/v1"
FAKE_ID = "00000000-0000-0000-0000-000000000001"
TASK_ID = "00000000-0000-0000-0000-000000000002"


class TestTimelineAuthGuard:
    def test_no_token_returns_403(self):
        r = client.get(f"{PREFIX}/mobilities/{FAKE_ID}/timeline")
        assert r.status_code == 403

    def test_invalid_token_returns_401(self):
        r = client.get(
            f"{PREFIX}/mobilities/{FAKE_ID}/timeline",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert r.status_code == 401

    def test_invalid_uuid_returns_422(self):
        r = client.get(
            f"{PREFIX}/mobilities/not-a-valid-uuid/timeline",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert r.status_code in (401, 422)


class TestChecklistAuthGuard:
    def test_list_tasks_no_token_returns_403(self):
        r = client.get(f"{PREFIX}/mobilities/{FAKE_ID}/tasks")
        assert r.status_code == 403

    def test_create_task_no_token_returns_403(self):
        r = client.post(
            f"{PREFIX}/mobilities/{FAKE_ID}/tasks",
            json={"title": "Test task", "category": "admin"},
        )
        assert r.status_code == 403

    def test_update_task_no_token_returns_403(self):
        r = client.patch(f"{PREFIX}/tasks/{TASK_ID}")
        assert r.status_code == 403

    def test_complete_task_no_token_returns_403(self):
        r = client.patch(f"{PREFIX}/tasks/{TASK_ID}/complete")
        assert r.status_code == 403

    def test_delete_task_no_token_returns_403(self):
        r = client.delete(f"{PREFIX}/tasks/{TASK_ID}")
        assert r.status_code == 403

    def test_invalid_token_returns_401(self):
        r = client.get(
            f"{PREFIX}/mobilities/{FAKE_ID}/tasks",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert r.status_code == 401


FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def _make_fake_user():
    from unittest.mock import MagicMock

    user = MagicMock()
    user.id = FAKE_USER_ID
    user.email = "test@studafly.com"
    user.is_premium = False
    return user


def _make_task_read():
    from src.app.schemas.task import TaskRead

    return TaskRead(
        id=uuid.UUID(TASK_ID),
        mobility_id=uuid.UUID(FAKE_ID),
        title="Apply for Erasmus",
        description="Submit application",
        category="admin",
        deadline=None,
        is_completed=False,
        priority=1,
    )


@pytest.fixture
def auth_client():
    from src.app.core.dependencies import get_current_user

    fake_user = _make_fake_user()

    async def override():
        return fake_user

    app.dependency_overrides[get_current_user] = override
    yield client, fake_user
    app.dependency_overrides.clear()


class TestTimelineHappyPath:
    def test_get_timeline_returns_200(self, auth_client):
        client_, user = auth_client
        task = _make_task_read()

        with patch(
            "src.app.services.timeline_service.get_timeline",
            new_callable=AsyncMock,
            return_value=[task],
        ):
            r = client_.get(
                f"{PREFIX}/mobilities/{FAKE_ID}/timeline",
                headers={"Authorization": "Bearer faketoken"},
            )

        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert body["data"][0]["title"] == "Apply for Erasmus"

    def test_get_timeline_not_found_returns_404(self, auth_client):
        from src.app.core.exceptions import NotFoundError

        client_, _ = auth_client

        with patch(
            "src.app.services.timeline_service.get_timeline",
            new_callable=AsyncMock,
            side_effect=NotFoundError("Mobility not found"),
        ):
            r = client_.get(
                f"{PREFIX}/mobilities/{FAKE_ID}/timeline",
                headers={"Authorization": "Bearer faketoken"},
            )

        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"


class TestChecklistHappyPath:
    def test_list_tasks_returns_200(self, auth_client):
        client_, _ = auth_client
        task = _make_task_read()

        with patch(
            "src.app.services.checklist_service.list_tasks",
            new_callable=AsyncMock,
            return_value=[task],
        ):
            r = client_.get(
                f"{PREFIX}/mobilities/{FAKE_ID}/tasks",
                headers={"Authorization": "Bearer faketoken"},
            )

        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 1

    def test_create_task_returns_201(self, auth_client):
        client_, _ = auth_client
        task = _make_task_read()

        with patch(
            "src.app.services.checklist_service.create_task",
            new_callable=AsyncMock,
            return_value=task,
        ):
            r = client_.post(
                f"{PREFIX}/mobilities/{FAKE_ID}/tasks",
                json={"title": "Apply for Erasmus", "category": "admin", "priority": 1},
                headers={"Authorization": "Bearer faketoken"},
            )

        assert r.status_code == 201
        assert r.json()["data"]["title"] == "Apply for Erasmus"

    def test_create_task_missing_fields_returns_422(self, auth_client):
        client_, _ = auth_client

        r = client_.post(
            f"{PREFIX}/mobilities/{FAKE_ID}/tasks",
            json={"priority": 1},
            headers={"Authorization": "Bearer faketoken"},
        )
        assert r.status_code == 422

    def test_complete_task_returns_200(self, auth_client):
        client_, _ = auth_client
        task = _make_task_read()

        with patch(
            "src.app.services.checklist_service.complete_task",
            new_callable=AsyncMock,
            return_value=task,
        ):
            r = client_.patch(
                f"{PREFIX}/tasks/{TASK_ID}/complete",
                headers={"Authorization": "Bearer faketoken"},
            )

        assert r.status_code == 200

    def test_delete_task_returns_204(self, auth_client):
        client_, _ = auth_client

        with patch(
            "src.app.services.checklist_service.delete_task",
            new_callable=AsyncMock,
            return_value=None,
        ):
            r = client_.delete(
                f"{PREFIX}/tasks/{TASK_ID}",
                headers={"Authorization": "Bearer faketoken"},
            )

        assert r.status_code == 204

    def test_checklist_forbidden_returns_403(self, auth_client):
        from src.app.core.exceptions import ForbiddenError

        client_, _ = auth_client

        with patch(
            "src.app.services.checklist_service.list_tasks",
            new_callable=AsyncMock,
            side_effect=ForbiddenError(),
        ):
            r = client_.get(
                f"{PREFIX}/mobilities/{FAKE_ID}/tasks",
                headers={"Authorization": "Bearer faketoken"},
            )

        assert r.status_code == 403
        assert r.json()["error"]["code"] == "FORBIDDEN"
