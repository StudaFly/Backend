"""
Unit tests for the core module.
Covers logging configuration, password hashing and verification
(bcrypt via passlib), as well as JWT token creation and decoding (access + refresh).
"""

import uuid

import pytest
from src.app.core.logging import configure_logging
from src.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_configure_logging():
    configure_logging()


def test_hash_password_returns_hashed():
    plain = "mysecretpassword"
    hashed = hash_password(plain)
    assert hashed != plain
    assert len(hashed) > 0


def test_verify_password_correct():
    plain = "mysecretpassword"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correctpassword")
    assert verify_password("wrongpassword", hashed) is False


def test_create_and_decode_access_token():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "refresh"


def test_decode_invalid_token_raises():
    with pytest.raises(ValueError):
        decode_token("not.a.valid.token")
