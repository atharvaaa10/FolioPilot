from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.errors import UnauthorizedError
from app.services.security import (
    DUMMY_HASH,
    check_needs_rehash,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)

TEST_SECRET = "test-secret-key-for-unit-testing-min-32-chars-long"


def test_hash_and_verify_password() -> None:
    pw = "SuperSecureP@ssw0rd123"
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2id$")
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_dummy_hash_verification() -> None:
    assert DUMMY_HASH.startswith("$argon2id$")
    assert verify_password("arbitrary-attempt", DUMMY_HASH) is False


def test_check_needs_rehash() -> None:
    pw = "TestPassword456"
    hashed = hash_password(pw)
    assert check_needs_rehash(hashed) is False
    assert check_needs_rehash("invalid-hash-string") is False


def test_generate_and_hash_refresh_token() -> None:
    tok1 = generate_refresh_token()
    tok2 = generate_refresh_token()
    assert len(tok1) >= 48
    assert tok1 != tok2

    h1 = hash_token(tok1)
    h2 = hash_token(tok1)
    assert len(h1) == 64
    assert h1 == h2
    assert h1 != hash_token(tok2)


def test_create_and_decode_access_token() -> None:
    now = datetime.now(UTC)
    token = create_access_token(
        user_id="d3b07384-d113-4a44-9388-372a818c34f8",
        secret=TEST_SECRET,
        algorithm="HS256",
        expires_delta=timedelta(minutes=15),
        now=now,
    )
    payload = decode_access_token(token, secret=TEST_SECRET, algorithm="HS256")
    assert payload["sub"] == "d3b07384-d113-4a44-9388-372a818c34f8"
    assert payload["typ"] == "access"
    assert "jti" in payload
    assert payload["iat"] == int(now.timestamp())
    assert payload["exp"] == int((now + timedelta(minutes=15)).timestamp())


def test_decode_access_token_expired() -> None:
    now = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)
    token = create_access_token(
        user_id="user-123",
        secret=TEST_SECRET,
        expires_delta=timedelta(seconds=-10),  # Already expired
        now=now,
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_access_token(token, secret=TEST_SECRET)
    assert exc_info.value.code == "TOKEN_EXPIRED"
    assert exc_info.value.status_code == 401


def test_decode_access_token_tampered() -> None:
    token = create_access_token(
        user_id="user-123",
        secret=TEST_SECRET,
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_access_token(token, secret="different-secret-key-32-chars-long!")
    assert exc_info.value.code == "INVALID_TOKEN"
    assert exc_info.value.status_code == 401


def test_decode_access_token_invalid_typ() -> None:
    # Token with typ="refresh" instead of "access"
    now = datetime.now(UTC)
    payload = {
        "sub": "user-123",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "jti": "some-uuid",
        "typ": "refresh",
    }
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_access_token(token, secret=TEST_SECRET)
    assert exc_info.value.code == "INVALID_TOKEN"
