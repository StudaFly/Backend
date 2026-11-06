"""Two-step sign-in of platform admins: password, then TOTP (or a backup code)."""

from datetime import datetime

import pyotp
import pytest
from src.app.core.security import decode_token
from src.app.models.enums import AccountType
from src.app.models.user import User
from src.app.services import mfa_service

from tests.db.factories import PASSWORD, auth_headers, make_user


def _bearer(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['accessToken']}"}


async def _login(api, user: User) -> dict:
    response = await api.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _enroll_totp(api, auth: dict) -> tuple[pyotp.TOTP, dict]:
    setup = await api.post("/auth/mfa/setup", headers=_bearer(auth))
    assert setup.status_code == 200, setup.text
    totp = pyotp.TOTP(setup.json()["data"]["secret"])
    activated = await api.post(
        "/auth/mfa/activate", json={"code": totp.now()}, headers=_bearer(auth)
    )
    assert activated.status_code == 200, activated.text
    return totp, activated.json()["data"]


@pytest.fixture
async def admin(db):
    user = await make_user(db, AccountType.PLATFORM_ADMIN)
    await db.commit()
    return user


async def test_first_sign_in_requires_mfa_setup_before_admin_routes(api, admin):
    auth = await _login(api, admin)

    assert auth["mfaRequired"] is True
    assert auth["user"]["mfaEnabled"] is False
    refused = await api.get("/admin/overview", headers=_bearer(auth))
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "MFA_REQUIRED"

    setup = await api.post("/auth/mfa/setup", headers=_bearer(auth))
    data = setup.json()["data"]
    assert data["otpauthUri"].startswith("otpauth://totp/StudaFly:")

    _, activated = await _enroll_totp(api, auth)
    assert len(activated["backupCodes"]) == mfa_service.BACKUP_CODE_COUNT
    assert activated["mfaRequired"] is False
    assert decode_token(activated["accessToken"])["mfa"] is True
    overview = await api.get("/admin/overview", headers=_bearer(activated))
    assert overview.status_code == 200


async def test_secret_is_stored_encrypted_and_backup_codes_hashed(api, db, admin):
    auth = await _login(api, admin)
    _, activated = await _enroll_totp(api, auth)

    await db.refresh(admin)
    secret = mfa_service.decrypt_secret(admin.mfa_secret)
    assert secret not in admin.mfa_secret
    assert not set(activated["backupCodes"]) & set(admin.mfa_backup_codes)


async def test_next_sign_in_verifies_a_code(api, admin):
    totp, _ = await _enroll_totp(api, await _login(api, admin))
    auth = await _login(api, admin)

    assert auth["mfaRequired"] is True
    verified = await api.post(
        "/auth/mfa/verify",
        json={"code": totp.at(datetime.now(), counter_offset=1)},
        headers=_bearer(auth),
    )

    assert verified.status_code == 200, verified.text
    assert verified.json()["data"]["mfaRequired"] is False
    assert decode_token(verified.json()["data"]["accessToken"])["mfa"] is True


async def test_refresh_keeps_the_mfa_claim(api, admin):
    _, activated = await _enroll_totp(api, await _login(api, admin))

    refreshed = await api.post("/auth/refresh", json={"refreshToken": activated["refreshToken"]})

    assert decode_token(refreshed.json()["data"]["accessToken"])["mfa"] is True


async def test_a_totp_code_cannot_be_replayed(api, admin):
    totp, _ = await _enroll_totp(api, await _login(api, admin))
    auth = await _login(api, admin)
    code = totp.at(datetime.now(), counter_offset=1)

    first = await api.post("/auth/mfa/verify", json={"code": code}, headers=_bearer(auth))
    replay = await api.post("/auth/mfa/verify", json={"code": code}, headers=_bearer(auth))

    assert first.status_code == 200
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "INVALID_MFA_CODE"


async def test_a_backup_code_works_once(api, admin):
    _, activated = await _enroll_totp(api, await _login(api, admin))
    auth = await _login(api, admin)
    backup_code = activated["backupCodes"][0]

    first = await api.post("/auth/mfa/verify", json={"code": backup_code}, headers=_bearer(auth))
    again = await api.post("/auth/mfa/verify", json={"code": backup_code}, headers=_bearer(auth))

    assert first.status_code == 200
    assert again.status_code == 400


async def test_attempts_are_limited(api, admin):
    await _enroll_totp(api, await _login(api, admin))
    auth = await _login(api, admin)

    statuses = [
        (
            await api.post("/auth/mfa/verify", json={"code": "000000"}, headers=_bearer(auth))
        ).status_code
        for _ in range(mfa_service.MAX_ATTEMPTS + 1)
    ]

    assert statuses[: mfa_service.MAX_ATTEMPTS] == [400] * mfa_service.MAX_ATTEMPTS
    assert statuses[-1] == 429


async def test_mfa_routes_are_reserved_to_platform_admins(api, db):
    student = await make_user(db)
    await db.commit()

    for path in ("/auth/mfa/setup", "/auth/mfa/verify", "/auth/mfa/activate"):
        response = await api.post(path, json={"code": "123456"}, headers=auth_headers(student))
        assert response.status_code == 403, path


async def test_other_accounts_never_need_mfa(api, db):
    student = await make_user(db)
    await db.commit()

    assert (await _login(api, student))["mfaRequired"] is False
