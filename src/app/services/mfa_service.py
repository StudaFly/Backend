import base64
import hashlib
import hmac
import secrets

import pyotp
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.core.exceptions import ConflictError, StudaFlyException
from src.app.models.user import User
from src.app.services import audit_service, cache_service
from src.app.services.audit_service import RequestMeta

ISSUER = "StudaFly"
BACKUP_CODE_COUNT = 8
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW_SECONDS = 300
_USED_CODE_TTL_SECONDS = 90
_BACKUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _fernet() -> Fernet:
    key = settings.MFA_ENCRYPTION_KEY
    if not key:
        if settings.APP_ENV == "production":
            raise RuntimeError("MFA_ENCRYPTION_KEY must be set in production")
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode()).decode()


def _normalize(code: str) -> str:
    return code.replace(" ", "").replace("-", "").upper()


def _hash_backup_code(code: str) -> str:
    return hashlib.sha256(_normalize(code).encode()).hexdigest()


def generate_backup_codes() -> list[str]:
    codes = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = "".join(secrets.choice(_BACKUP_CODE_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def _setup_required() -> StudaFlyException:
    return StudaFlyException(
        "Set up multi-factor authentication first", code="MFA_SETUP_REQUIRED", status_code=409
    )


async def start_setup(db: AsyncSession, user: User) -> tuple[str, str]:
    if user.mfa_enabled:
        raise ConflictError("Multi-factor authentication is already enabled")
    secret = pyotp.random_base32()
    user.mfa_secret = encrypt_secret(secret)
    await db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    return secret, uri


async def activate(db: AsyncSession, user: User, code: str, meta: RequestMeta) -> list[str]:
    if user.mfa_enabled:
        raise ConflictError("Multi-factor authentication is already enabled")
    if not user.mfa_secret:
        raise _setup_required()
    await _check_code(user, code, allow_backup_code=False)

    backup_codes = generate_backup_codes()
    user.mfa_enabled = True
    user.mfa_backup_codes = [_hash_backup_code(c) for c in backup_codes]
    audit_service.record(
        db,
        actor=user,
        action="mfa.enable",
        target_type="user",
        target_id=user.id,
        meta=meta,
    )
    await db.commit()
    return backup_codes


async def verify(db: AsyncSession, user: User, code: str) -> None:
    if not user.mfa_enabled or not user.mfa_secret:
        raise _setup_required()
    await _check_code(user, code, allow_backup_code=True)
    await db.commit()


async def _check_code(user: User, code: str, *, allow_backup_code: bool) -> None:
    attempts_key = f"auth:mfa:attempts:{user.id}"
    if int(await cache_service.get(attempts_key) or 0) >= MAX_ATTEMPTS:
        raise StudaFlyException(
            "Too many invalid codes, try again in a few minutes",
            code="TOO_MANY_ATTEMPTS",
            status_code=429,
        )

    normalized = _normalize(code)
    if len(normalized) == 6 and normalized.isdigit():
        totp = pyotp.TOTP(decrypt_secret(user.mfa_secret))
        used_key = f"auth:mfa:used:{user.id}:{normalized}"
        if totp.verify(normalized, valid_window=1) and not await cache_service.get(used_key):
            await cache_service.set(used_key, "1", ttl=_USED_CODE_TTL_SECONDS)
            await cache_service.delete(attempts_key)
            return
    elif allow_backup_code and user.mfa_backup_codes:
        hashed = _hash_backup_code(normalized)
        match = next((h for h in user.mfa_backup_codes if hmac.compare_digest(h, hashed)), None)
        if match:
            user.mfa_backup_codes = [h for h in user.mfa_backup_codes if h != match]
            await cache_service.delete(attempts_key)
            return

    await cache_service.incr(attempts_key, ATTEMPT_WINDOW_SECONDS)
    raise StudaFlyException("Invalid code", code="INVALID_MFA_CODE", status_code=400)
