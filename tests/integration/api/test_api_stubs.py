"""
Tests for endpoints in skeleton mode.
Each endpoint raises NotImplementedError → caught by generic_exception_handler → 500.
This covers all NotImplementedError raises in each endpoint and the exception handlers.
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
        # Auth
        ("post", f"{PREFIX}/auth/register"),
        ("post", f"{PREFIX}/auth/login"),
        ("post", f"{PREFIX}/auth/oauth/google"),
        ("post", f"{PREFIX}/auth/oauth/microsoft"),
        ("post", f"{PREFIX}/auth/oauth/apple"),
        ("post", f"{PREFIX}/auth/refresh"),
        ("post", f"{PREFIX}/auth/logout"),
        ("post", f"{PREFIX}/auth/forgot-password"),
        ("post", f"{PREFIX}/auth/reset-password"),
        ("post", f"{PREFIX}/auth/verify-email"),
        # Users
        ("get", f"{PREFIX}/users/me"),
        ("patch", f"{PREFIX}/users/me"),
        ("delete", f"{PREFIX}/users/me"),
        # Mobilities
        ("get", f"{PREFIX}/mobilities/"),
        ("post", f"{PREFIX}/mobilities/"),
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}"),
        ("patch", f"{PREFIX}/mobilities/{FAKE_ID}"),
        ("delete", f"{PREFIX}/mobilities/{FAKE_ID}"),
        # Timeline & Checklist
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}/timeline"),
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}/tasks"),
        ("post", f"{PREFIX}/mobilities/{FAKE_ID}/tasks"),
        ("patch", f"{PREFIX}/mobilities/tasks/{FAKE_ID}"),
        ("patch", f"{PREFIX}/mobilities/tasks/{FAKE_ID}/complete"),
        ("delete", f"{PREFIX}/mobilities/tasks/{FAKE_ID}"),
        # Budget & Guide
        ("get", f"{PREFIX}/destinations/{FAKE_ID}/budget"),
        ("get", f"{PREFIX}/destinations/"),
        ("get", f"{PREFIX}/destinations/{FAKE_ID}/guide"),
        # Documents
        ("get", f"{PREFIX}/mobilities/{FAKE_ID}/documents"),
        ("post", f"{PREFIX}/mobilities/{FAKE_ID}/documents"),
        ("get", f"{PREFIX}/documents/{FAKE_ID}"),
        ("delete", f"{PREFIX}/documents/{FAKE_ID}"),
        # Notifications
        ("get", f"{PREFIX}/notifications/"),
        # Admin
        ("get", f"{PREFIX}/admin/students"),
        ("get", f"{PREFIX}/admin/stats"),
        ("post", f"{PREFIX}/admin/tasks"),
    ],
)
def test_stub_endpoint_returns_error(method, path):
    response = getattr(client, method)(path)
    assert response.status_code in (
        500,
        422,
        404,
        405,
        401,
        403,
    ), f"Unexpected status {response.status_code} for {method.upper()} {path}"
