from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jose import JWTError, jwt

from src.app.core.config import settings

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: UUID,
    *,
    session_id: str | None = None,
    token_version: int = 0,
    account_type: str = "student",
    org_id: UUID | None = None,
    org_role: str | None = None,
    mfa: bool = False,
) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
        "sid": session_id or str(uuid4()),
        "token_version": token_version,
        "account_type": account_type,
        "org_id": str(org_id) if org_id else None,
        "org_role": org_role,
        "mfa": mfa,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(
    user_id: UUID, *, session_id: str | None = None, token_version: int = 0
) -> tuple[str, str]:
    jti = str(uuid4())
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": jti,
        "sid": session_id or str(uuid4()),
        "token_version": token_version,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256"), jti


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        raise ValueError("Invalid token") from e
