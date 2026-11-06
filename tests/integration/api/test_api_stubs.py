"""
Error-contract tests at the HTTP level (no database needed).

- Endpoints that are not implemented yet answer 501 NOT_IMPLEMENTED (never a 500).
- Protected endpoints answer 401 without a token.
- Every error uses the {"error": {"code", "message"}} envelope.
"""

import pytest
from fastapi.testclient import TestClient
from src.app.main import app

client = TestClient(app, raise_server_exceptions=False)

PREFIX = "/api/v1"
FAKE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", f"{PREFIX}/auth/oauth/microsoft"),
        ("post", f"{PREFIX}/auth/oauth/apple"),
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}/documents"),
        ("post", f"{PREFIX}/mobilities/{FAKE_ID}/documents"),
        ("get", f"{PREFIX}/documents/{FAKE_ID}"),
        ("delete", f"{PREFIX}/documents/{FAKE_ID}"),
    ],
)
def test_unimplemented_endpoint_returns_501(method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", f"{PREFIX}/auth/logout"),
        ("get", f"{PREFIX}/users/me"),
        ("patch", f"{PREFIX}/users/me"),
        ("delete", f"{PREFIX}/users/me"),
        ("get", f"{PREFIX}/mobilities"),
        ("post", f"{PREFIX}/mobilities"),
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}"),
        ("patch", f"{PREFIX}/mobilities/{FAKE_ID}"),
        ("delete", f"{PREFIX}/mobilities/{FAKE_ID}"),
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}/timeline"),
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}/tasks"),
        ("patch", f"{PREFIX}/tasks/{FAKE_ID}"),
        ("delete", f"{PREFIX}/tasks/{FAKE_ID}"),
        ("get", f"{PREFIX}/notifications"),
        ("get", f"{PREFIX}/notifications/unread-count"),
        ("post", f"{PREFIX}/notifications/read-all"),
        ("patch", f"{PREFIX}/notifications/{FAKE_ID}/read"),
        ("delete", f"{PREFIX}/notifications/{FAKE_ID}"),
        ("post", f"{PREFIX}/notifications/push-tokens"),
        ("post", f"{PREFIX}/auth/mfa/setup"),
        ("post", f"{PREFIX}/auth/mfa/verify"),
        ("get", f"{PREFIX}/admin/overview"),
        ("get", f"{PREFIX}/admin/users"),
        ("get", f"{PREFIX}/admin/organizations"),
        ("get", f"{PREFIX}/admin/audit-logs"),
    ],
)
def test_protected_endpoint_without_token_returns_401(method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_returns_401_with_error_envelope():
    response = client.get(f"{PREFIX}/users/me", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_unknown_route_returns_404_with_error_envelope():
    response = client.get(f"{PREFIX}/destinations/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_validation_error_uses_envelope_and_hides_input():
    response = client.post(
        f"{PREFIX}/auth/register",
        json={"email": "not-an-email", "password": "secret-short", "name": "A"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"].startswith("email:")
    assert all("input" not in detail for detail in error["details"])
    assert "secret-short" not in response.text


@pytest.mark.parametrize(
    "body",
    [{}, {"idToken": "a", "code": "b"}, {"idToken": ""}],
    ids=["empty", "both", "blank"],
)
def test_google_oauth_requires_exactly_one_credential(body):
    response = client.post(f"{PREFIX}/auth/oauth/google", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_google_oauth_not_configured_returns_503(monkeypatch):
    from src.app.core.config import settings

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    response = client.post(f"{PREFIX}/auth/oauth/google", json={"idToken": "token"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OAUTH_NOT_CONFIGURED"
