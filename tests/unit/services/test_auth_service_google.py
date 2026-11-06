"""
Unit tests for auth_service.google_login: account creation, retrieval and linking.
Google verification is mocked (see test_google_oauth_service.py), as is the database.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from src.app.core.exceptions import StudaFlyException, UnauthorizedError
from src.app.models.enums import AccountType, UserStatus
from src.app.models.user import User
from src.app.schemas.user import GoogleAuthRequest
from src.app.services import auth_service
from src.app.services.google_oauth_service import GoogleIdentity

IDENTITY = GoogleIdentity(
    sub="google-sub-123", email="Lucas@Gmail.com", email_verified=True, name="Lucas Martin"
)


def _user(**overrides) -> User:
    fields = {
        "id": uuid.uuid4(),
        "email": "lucas@gmail.com",
        "password_hash": "bcrypt-hash",
        "name": "Lucas M.",
        "account_type": AccountType.STUDENT,
        "status": UserStatus.ACTIVE,
        "email_verified": False,
        "oauth_provider": None,
        "google_id": None,
        "enable_notifications": True,
        "created_at": datetime(2026, 1, 1),
    }
    fields.update(overrides)
    return User(**fields)


def _db(*scalar_results):
    db = AsyncMock()
    db.scalar.side_effect = list(scalar_results)
    db.add = MagicMock()

    async def fake_refresh(user):
        # Column defaults are applied by the database on INSERT.
        user.id = user.id or uuid.uuid4()
        user.account_type = user.account_type or AccountType.STUDENT
        user.status = user.status or UserStatus.ACTIVE
        user.enable_notifications = user.enable_notifications is not False
        user.created_at = user.created_at or datetime(2026, 11, 4)

    db.refresh.side_effect = fake_refresh
    return db


async def _fake_issue_tokens(db, user, is_new_user=False, **_):
    return SimpleNamespace(
        user=user, is_new_user=is_new_user, access_token="access", refresh_token="refresh"
    )


@pytest.fixture(autouse=True)
def google():
    with (
        patch.object(
            auth_service.google_oauth_service,
            "verify_id_token",
            new_callable=AsyncMock,
            return_value=IDENTITY,
        ) as verify,
        patch.object(
            auth_service.google_oauth_service,
            "exchange_code",
            new_callable=AsyncMock,
            return_value="exchanged-id-token",
        ) as exchange,
        patch.object(auth_service, "issue_tokens", side_effect=_fake_issue_tokens),
    ):
        yield {"verify": verify, "exchange": exchange}


@pytest.mark.asyncio
async def test_first_sign_in_creates_account():
    db = _db(None, None)

    auth = await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    created = db.add.call_args.args[0]
    assert created.email == "Lucas@Gmail.com"
    assert created.name == "Lucas Martin"
    assert created.password_hash is None
    assert created.google_id == "google-sub-123"
    assert created.oauth_provider == "google"
    assert created.email_verified is True
    assert created.account_type == AccountType.STUDENT
    assert created.last_login_at is not None
    assert auth.is_new_user is True
    assert auth.access_token and auth.refresh_token
    assert auth.user.oauth_provider == "google"


@pytest.mark.asyncio
async def test_name_falls_back_to_email_prefix(google):
    google["verify"].return_value = GoogleIdentity(
        sub="s", email="anna@uni.fr", email_verified=True, name=None
    )
    db = _db(None, None)

    await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    assert db.add.call_args.args[0].name == "anna"


@pytest.mark.asyncio
async def test_known_google_account_signs_in():
    existing = _user(google_id="google-sub-123", oauth_provider="google", email_verified=True)
    db = _db(existing)

    auth = await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    assert auth.user.id == existing.id
    assert auth.is_new_user is False
    assert existing.last_login_at is not None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_existing_email_account_is_linked():
    existing = _user()
    db = _db(None, existing)

    auth = await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    assert existing.google_id == "google-sub-123"
    assert existing.email_verified is True
    assert existing.oauth_provider == "google"
    assert existing.password_hash == "bcrypt-hash"
    db.add.assert_not_called()
    assert auth.user.id == existing.id
    assert auth.is_new_user is False


@pytest.mark.asyncio
async def test_linking_keeps_the_original_provider():
    existing = _user(oauth_provider="microsoft")
    db = _db(None, existing)

    await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    assert existing.oauth_provider == "microsoft"
    assert existing.google_id == "google-sub-123"


@pytest.mark.asyncio
async def test_unverified_google_email_is_rejected(google):
    google["verify"].return_value = GoogleIdentity(
        sub="s", email="x@y.com", email_verified=False, name=None
    )
    db = _db()

    with pytest.raises(UnauthorizedError):
        await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))
    db.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_code_is_exchanged_then_verified(google):
    db = _db(None, None)

    await auth_service.google_login(db, GoogleAuthRequest(code="auth-code"))

    google["exchange"].assert_awaited_once_with("auth-code")
    google["verify"].assert_awaited_once_with("exchanged-id-token")


@pytest.mark.asyncio
async def test_id_token_is_verified_without_exchange(google):
    db = _db(None, None)

    await auth_service.google_login(db, GoogleAuthRequest(id_token="native-token"))

    google["exchange"].assert_not_awaited()
    google["verify"].assert_awaited_once_with("native-token")


@pytest.mark.asyncio
async def test_concurrent_first_sign_in_retries_lookup():
    created_meanwhile = _user(google_id="google-sub-123", oauth_provider="google")
    db = _db(None, None, created_meanwhile)
    db.commit.side_effect = [IntegrityError("INSERT", {}, Exception("duplicate")), None]

    auth = await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    db.rollback.assert_awaited_once()
    assert auth.user.id == created_meanwhile.id
    assert auth.is_new_user is False


@pytest.mark.asyncio
async def test_suspended_google_account_is_refused():
    existing = _user(google_id="google-sub-123", status=UserStatus.SUSPENDED)
    db = _db(existing)

    with pytest.raises(StudaFlyException) as error:
        await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    assert error.value.code == "ACCOUNT_SUSPENDED"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_account_pending_deletion_is_not_linked():
    existing = _user(status=UserStatus.PENDING_DELETION)
    db = _db(None, existing)

    with pytest.raises(StudaFlyException) as error:
        await auth_service.google_login(db, GoogleAuthRequest(id_token="tok"))

    assert error.value.code == "ACCOUNT_PENDING_DELETION"
    assert existing.google_id is None
    db.commit.assert_not_awaited()
