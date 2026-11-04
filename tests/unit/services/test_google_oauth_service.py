"""
Unit tests for google_oauth_service: ID tokens are signed with a local RSA key and
Google's endpoints (certs, token exchange) are served by an httpx MockTransport.
"""

import time

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from src.app.core.exceptions import ServiceUnavailableError, UnauthorizedError
from src.app.services import google_oauth_service

CLIENT_ID = "web-client-id.apps.googleusercontent.com"
KID = "test-key-1"


def _private_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


PRIVATE_PEM = _private_pem()
OTHER_PRIVATE_PEM = _private_pem()


def _public_jwk(private_pem: bytes, kid: str) -> dict:
    public = jwk.construct(private_pem, "RS256").public_key().to_dict()
    return {**public, "kid": kid, "use": "sig", "alg": "RS256"}


def _claims(**overrides) -> dict:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-123",
        "email": "lucas@gmail.com",
        "email_verified": True,
        "name": "Lucas Martin",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


def _token(claims: dict | None = None, *, kid: str = KID, private_pem: bytes = PRIVATE_PEM) -> str:
    return jwt.encode(claims or _claims(), private_pem, algorithm="RS256", headers={"kid": kid})


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(google_oauth_service.settings, "GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(google_oauth_service.settings, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setitem(google_oauth_service._certs_cache, "keys", [])
    monkeypatch.setitem(google_oauth_service._certs_cache, "expires_at", 0.0)


@pytest.fixture
def google(monkeypatch):
    """Fake Google endpoints. Tests tweak `state` to change the answers."""
    state = {
        "keys": [_public_jwk(PRIVATE_PEM, KID)],
        "certs_calls": 0,
        "token_status": 200,
        "token_body": {"id_token": "id-token-from-google"},
        "token_requests": [],
        "network_error": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if state["network_error"]:
            raise httpx.ConnectError("boom", request=request)
        if request.url == google_oauth_service.GOOGLE_CERTS_URL:
            state["certs_calls"] += 1
            return httpx.Response(
                200, json={"keys": state["keys"]}, headers={"cache-control": "max-age=600"}
            )
        if request.url == google_oauth_service.GOOGLE_TOKEN_URL:
            state["token_requests"].append(request)
            return httpx.Response(state["token_status"], json=state["token_body"])
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        google_oauth_service.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return state


# ── verify_id_token ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_token_returns_identity(google):
    identity = await google_oauth_service.verify_id_token(_token())
    assert identity.sub == "google-sub-123"
    assert identity.email == "lucas@gmail.com"
    assert identity.email_verified is True
    assert identity.name == "Lucas Martin"


@pytest.mark.asyncio
async def test_token_with_at_hash_is_accepted(google):
    identity = await google_oauth_service.verify_id_token(_token(_claims(at_hash="abc")))
    assert identity.sub == "google-sub-123"


@pytest.mark.asyncio
async def test_unverified_email_flag_is_reported(google):
    identity = await google_oauth_service.verify_id_token(_token(_claims(email_verified=False)))
    assert identity.email_verified is False


@pytest.mark.asyncio
async def test_certs_are_cached(google):
    await google_oauth_service.verify_id_token(_token())
    await google_oauth_service.verify_id_token(_token())
    assert google["certs_calls"] == 1


@pytest.mark.asyncio
async def test_unknown_kid_refreshes_rotated_keys(google):
    await google_oauth_service.verify_id_token(_token())
    google["keys"] = [_public_jwk(OTHER_PRIVATE_PEM, "rotated-key")]

    identity = await google_oauth_service.verify_id_token(
        _token(kid="rotated-key", private_pem=OTHER_PRIVATE_PEM)
    )
    assert identity.sub == "google-sub-123"
    assert google["certs_calls"] == 2


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(lambda: _token(_claims(aud="another-app")), id="wrong-audience"),
        pytest.param(lambda: _token(_claims(iss="https://evil.example")), id="wrong-issuer"),
        pytest.param(lambda: _token(_claims(exp=int(time.time()) - 60)), id="expired"),
        pytest.param(lambda: _token(_claims(email=None)), id="no-email"),
        pytest.param(lambda: _token(private_pem=OTHER_PRIVATE_PEM), id="bad-signature"),
        pytest.param(lambda: _token(kid="unknown-kid"), id="unknown-kid"),
        pytest.param(lambda: "not-a-jwt", id="garbage"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_tokens_are_rejected(google, token_factory):
    with pytest.raises(UnauthorizedError):
        await google_oauth_service.verify_id_token(token_factory())


@pytest.mark.asyncio
async def test_not_configured_returns_503(google, monkeypatch):
    monkeypatch.setattr(google_oauth_service.settings, "GOOGLE_CLIENT_ID", "")
    with pytest.raises(ServiceUnavailableError) as exc:
        await google_oauth_service.verify_id_token(_token())
    assert exc.value.code == "OAUTH_NOT_CONFIGURED"
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_google_unreachable_returns_503(google):
    google["network_error"] = True
    with pytest.raises(ServiceUnavailableError) as exc:
        await google_oauth_service.verify_id_token(_token())
    assert exc.value.code == "OAUTH_PROVIDER_UNAVAILABLE"


# ── exchange_code ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_returns_id_token(google):
    id_token = await google_oauth_service.exchange_code("auth-code")

    assert id_token == "id-token-from-google"
    body = google["token_requests"][0].content.decode()
    assert "code=auth-code" in body
    assert "redirect_uri=postmessage" in body
    assert "grant_type=authorization_code" in body
    assert "client_secret=secret" in body


@pytest.mark.asyncio
async def test_exchange_rejected_code_is_unauthorized(google):
    google["token_status"] = 400
    google["token_body"] = {"error": "invalid_grant"}
    with pytest.raises(UnauthorizedError):
        await google_oauth_service.exchange_code("expired-code")


@pytest.mark.asyncio
async def test_exchange_google_error_is_503(google):
    google["token_status"] = 502
    google["token_body"] = {}
    with pytest.raises(ServiceUnavailableError):
        await google_oauth_service.exchange_code("auth-code")


@pytest.mark.asyncio
async def test_exchange_without_secret_is_not_configured(google, monkeypatch):
    monkeypatch.setattr(google_oauth_service.settings, "GOOGLE_CLIENT_SECRET", "")
    with pytest.raises(ServiceUnavailableError) as exc:
        await google_oauth_service.exchange_code("auth-code")
    assert exc.value.code == "OAUTH_NOT_CONFIGURED"
    assert google["token_requests"] == []
