"""
Google sign-in: turn what a client got from Google into a verified identity.

- Mobile (native sign-in) sends an ID token directly.
- Web (Google Identity Services popup) sends an authorization code, exchanged here
  with the client secret, which never leaves the backend.

In both cases the ID token is verified locally against Google's public keys.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from jose import JWTError, jwt

from src.app.core.config import settings
from src.app.core.exceptions import ServiceUnavailableError, UnauthorizedError

logger = logging.getLogger(__name__)

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
# Redirect URI expected by Google for codes obtained with a GIS popup (ux_mode="popup").
POPUP_REDIRECT_URI = "postmessage"

_HTTP_TIMEOUT = 10.0
_DEFAULT_CERTS_TTL = 3600
_MAX_AGE_RE = re.compile(r"max-age=(\d+)")

_certs_cache: dict[str, Any] = {"keys": [], "expires_at": 0.0}


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str | None


def _require_configured(*, needs_secret: bool = False) -> None:
    if not settings.GOOGLE_CLIENT_ID or (needs_secret and not settings.GOOGLE_CLIENT_SECRET):
        raise ServiceUnavailableError(
            "Google sign-in is not configured on the server", code="OAUTH_NOT_CONFIGURED"
        )


def _provider_unavailable(exc: Exception) -> ServiceUnavailableError:
    logger.error("Google OAuth unreachable (%s): %s", type(exc).__name__, exc)
    return ServiceUnavailableError(
        "Google is unreachable, please try again later", code="OAUTH_PROVIDER_UNAVAILABLE"
    )


def _cache_ttl(cache_control: str | None) -> int:
    match = _MAX_AGE_RE.search(cache_control or "")
    return int(match.group(1)) if match else _DEFAULT_CERTS_TTL


async def _get_signing_keys(*, force_refresh: bool = False) -> list[dict]:
    now = time.monotonic()
    if not force_refresh and _certs_cache["keys"] and now < _certs_cache["expires_at"]:
        return _certs_cache["keys"]

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.get(GOOGLE_CERTS_URL)
            response.raise_for_status()
    except httpx.HTTPError as e:
        raise _provider_unavailable(e) from e

    keys = response.json().get("keys", [])
    _certs_cache["keys"] = keys
    _certs_cache["expires_at"] = now + _cache_ttl(response.headers.get("cache-control"))
    return keys


def _find_key(keys: list[dict], kid: str | None) -> dict | None:
    return next((key for key in keys if key.get("kid") == kid), None)


async def verify_id_token(id_token: str) -> GoogleIdentity:
    _require_configured()

    try:
        kid = jwt.get_unverified_header(id_token).get("kid")
    except JWTError as e:
        raise UnauthorizedError("Invalid Google token") from e

    key = _find_key(await _get_signing_keys(), kid)
    if key is None:
        # Google rotates its keys: an unknown kid may just mean a stale cache.
        key = _find_key(await _get_signing_keys(force_refresh=True), kid)
    if key is None:
        raise UnauthorizedError("Invalid Google token")

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=settings.GOOGLE_CLIENT_ID,
            # at_hash binds the ID token to an access token we never receive.
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise UnauthorizedError("Invalid or expired Google token") from e

    if claims.get("iss") not in GOOGLE_ISSUERS or not claims.get("sub") or not claims.get("email"):
        raise UnauthorizedError("Invalid Google token")

    return GoogleIdentity(
        sub=claims["sub"],
        email=claims["email"],
        email_verified=claims.get("email_verified") is True,
        name=claims.get("name"),
    )


async def exchange_code(code: str) -> str:
    """Exchange a GIS popup authorization code for an ID token."""
    _require_configured(needs_secret=True)

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": POPUP_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
    except httpx.HTTPError as e:
        raise _provider_unavailable(e) from e

    if response.status_code >= 500:
        raise _provider_unavailable(RuntimeError(f"HTTP {response.status_code}"))
    if response.status_code != 200:
        # invalid_grant (expired / already used code), invalid_client (bad secret)…
        logger.warning("Google code exchange rejected: %s", response.text)
        raise UnauthorizedError("Invalid or expired Google authorization code")

    id_token = response.json().get("id_token")
    if not id_token:
        raise UnauthorizedError("Google did not return an ID token")
    return id_token
