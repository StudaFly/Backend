"""Sign-up, per-device sessions and immediate revocation (token_version, suspension)."""

from src.app.core.security import decode_token
from src.app.models.enums import AccountType, OrgRole, UserStatus
from src.app.models.user import User
from src.app.services import auth_service

from tests.db.factories import PASSWORD, auth_headers, make_member, make_organization, make_user


async def _login(api, email: str) -> dict:
    response = await api.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_register_always_creates_a_student(api):
    response = await api.post(
        "/auth/register",
        json={
            "email": "lucas@example.com",
            "password": PASSWORD,
            "name": "Lucas",
            "accountType": "platform_admin",
            "account_type": "org_staff",
            "role": "superadmin",
        },
    )

    assert response.status_code == 201
    user = response.json()["data"]["user"]
    assert user["accountType"] == "student"
    assert user["role"] == "student"
    assert user["organization"] is None


async def test_access_token_carries_role_claims(api, db):
    organization = await make_organization(db)
    member = await make_member(db, organization, OrgRole.MANAGER)
    staff = await db.get(User, member.user_id)
    await db.commit()

    auth = await _login(api, staff.email)
    claims = decode_token(auth["accessToken"])

    assert claims["account_type"] == "org_staff"
    assert claims["org_id"] == str(organization.id)
    assert claims["org_role"] == "manager"
    assert claims["token_version"] == 0
    assert claims["mfa"] is False
    assert claims["sid"] == decode_token(auth["refreshToken"])["sid"]


async def test_each_device_keeps_its_own_session(api, db):
    student = await make_user(db)
    await db.commit()

    web = await _login(api, student.email)
    phone = await _login(api, student.email)

    # Signing in on the phone did not revoke the web session…
    web_refreshed = await api.post("/auth/refresh", json={"refreshToken": web["refreshToken"]})
    assert web_refreshed.status_code == 200

    # …and logging out of the web leaves the phone signed in.
    logout = await api.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {web_refreshed.json()['data']['accessToken']}"},
    )
    assert logout.status_code == 200
    rejected = await api.post(
        "/auth/refresh", json={"refreshToken": web_refreshed.json()["data"]["refreshToken"]}
    )
    assert rejected.status_code == 401
    phone_refreshed = await api.post("/auth/refresh", json={"refreshToken": phone["refreshToken"]})
    assert phone_refreshed.status_code == 200


async def test_rotated_refresh_token_cannot_be_reused(api, db):
    student = await make_user(db)
    await db.commit()
    auth = await _login(api, student.email)

    first = await api.post("/auth/refresh", json={"refreshToken": auth["refreshToken"]})
    replay = await api.post("/auth/refresh", json={"refreshToken": auth["refreshToken"]})

    assert first.status_code == 200
    assert replay.status_code == 401


async def test_revoking_all_sessions_rejects_existing_tokens(api, db):
    student = await make_user(db)
    await db.commit()
    web = await _login(api, student.email)
    phone = await _login(api, student.email)

    await auth_service.revoke_all_sessions(student)
    await db.commit()

    me = await api.get("/users/me", headers={"Authorization": f"Bearer {web['accessToken']}"})
    assert me.status_code == 401
    for session in (web, phone):
        refreshed = await api.post("/auth/refresh", json={"refreshToken": session["refreshToken"]})
        assert refreshed.status_code == 401


async def test_suspended_account_is_locked_out(api, db, fake_cache):
    student = await make_user(db)
    await db.commit()
    auth = await _login(api, student.email)

    student.status = UserStatus.SUSPENDED
    await db.commit()

    login = await api.post("/auth/login", json={"email": student.email, "password": PASSWORD})
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "ACCOUNT_SUSPENDED"
    me = await api.get("/users/me", headers={"Authorization": f"Bearer {auth['accessToken']}"})
    assert me.status_code == 401
    refreshed = await api.post("/auth/refresh", json={"refreshToken": auth["refreshToken"]})
    assert refreshed.status_code == 401
    assert not fake_cache, "the refused refresh also drops the session"


async def test_account_pending_deletion_cannot_sign_in(api, db):
    student = await make_user(db, status=UserStatus.PENDING_DELETION)
    await db.commit()

    login = await api.post("/auth/login", json={"email": student.email, "password": PASSWORD})

    assert login.status_code == 403
    assert login.json()["error"]["code"] == "ACCOUNT_PENDING_DELETION"


async def test_login_records_last_login(api, db):
    student = await make_user(db)
    await db.commit()

    await _login(api, student.email)

    await db.refresh(student)
    assert student.last_login_at is not None


async def test_token_issued_for_an_older_token_version_is_rejected(api, db):
    student = await make_user(db, account_type=AccountType.STUDENT)
    headers = auth_headers(student)
    student.token_version = 3
    await db.commit()

    response = await api.get("/users/me", headers=headers)

    assert response.status_code == 401
