"""Google sign-in on the real schema: issued tokens follow the per-device session and role rules."""

from unittest.mock import AsyncMock

import pytest
from src.app.models.enums import AccountType, UserStatus
from src.app.services import google_oauth_service
from src.app.services.google_oauth_service import GoogleIdentity

from tests.db.factories import make_platform_admin, make_user


@pytest.fixture
def google_identity(monkeypatch):
    def use(email: str, sub: str = "google-sub-1") -> None:
        identity = GoogleIdentity(sub=sub, email=email, email_verified=True, name="Google User")
        monkeypatch.setattr(
            google_oauth_service, "verify_id_token", AsyncMock(return_value=identity)
        )

    return use


async def _google_login(api):
    return await api.post("/auth/oauth/google", json={"idToken": "google-id-token"})


async def test_a_new_google_account_gets_a_working_student_session(api, google_identity):
    google_identity("new.student@example.com")

    response = await _google_login(api)
    data = response.json()["data"]
    headers = {"Authorization": f"Bearer {data['accessToken']}"}
    me = await api.get("/users/me", headers=headers)
    refreshed = await api.post("/auth/refresh", json={"refreshToken": data["refreshToken"]})

    assert response.status_code == 200
    assert data["isNewUser"] is True
    assert data["user"]["accountType"] == "student"
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "new.student@example.com"
    assert refreshed.status_code == 200


async def test_an_existing_account_is_linked_and_keeps_its_type(api, db, google_identity):
    staff = await make_user(db, AccountType.ORG_STAFF, email="staff@example.com")
    await db.commit()
    google_identity("Staff@Example.com")

    response = await _google_login(api)
    data = response.json()["data"]

    assert response.status_code == 200
    assert data["isNewUser"] is False
    assert data["user"]["id"] == str(staff.id)
    assert data["user"]["accountType"] == "org_staff"


async def test_a_suspended_account_cannot_sign_in_with_google(api, db, google_identity):
    await make_user(db, email="suspended@example.com", status=UserStatus.SUSPENDED)
    await db.commit()
    google_identity("suspended@example.com")

    response = await _google_login(api)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_SUSPENDED"


async def test_a_platform_admin_still_needs_mfa_after_google(api, db, google_identity):
    await make_platform_admin(db, email="admin@example.com")
    await db.commit()
    google_identity("admin@example.com")

    response = await _google_login(api)
    data = response.json()["data"]
    overview = await api.get(
        "/admin/overview", headers={"Authorization": f"Bearer {data['accessToken']}"}
    )

    assert data["mfaRequired"] is True
    assert overview.status_code == 403
    assert overview.json()["error"]["code"] == "MFA_REQUIRED"
