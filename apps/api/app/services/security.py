"""Cryptographic security utilities for passwords and tokens.

Pure business logic adhering to CONVENTIONS.md.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.core.errors import UnauthorizedError

_ph = PasswordHasher()
# Pre-computed argon2id hash for dummy verification when email does not exist,
# preventing timing side-channel attacks on login.
DUMMY_HASH: str = _ph.hash("foliopilot-dummy-timing-password")


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return _ph.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against Argon2id hash. Returns True on success, False otherwise."""
    try:
        return _ph.verify(hashed_password, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def check_needs_rehash(hashed_password: str) -> bool:
    """Check if the password hash should be upgraded with modern parameters."""
    try:
        return _ph.check_needs_rehash(hashed_password)
    except (InvalidHashError, VerificationError):
        return False


def generate_refresh_token() -> str:
    """Generate high-entropy opaque refresh token string."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Compute SHA-256 hex digest of opaque token string."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    user_id: str | uuid.UUID,
    secret: str,
    algorithm: str = "HS256",
    expires_delta: timedelta | None = None,
    now: datetime | None = None,
) -> str:
    """Generate signed JWT access token with required claims."""
    current_time = now or datetime.now(UTC)
    delta = expires_delta or timedelta(minutes=15)
    expire_time = current_time + delta

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(current_time.timestamp()),
        "exp": int(expire_time.timestamp()),
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(
    token: str,
    *,
    secret: str,
    algorithm: str = "HS256",
) -> dict[str, Any]:
    """Decode and validate JWT access token claims.

    Raises:
        UnauthorizedError(code="TOKEN_EXPIRED"): If the token has expired.
        UnauthorizedError(code="INVALID_TOKEN"): If signature is invalid or claims are malformed.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["sub", "iat", "exp", "jti", "typ"]},
        )
    except ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token expired", code="TOKEN_EXPIRED") from exc
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token", code="INVALID_TOKEN") from exc

    if payload.get("typ") != "access":
        raise UnauthorizedError("Invalid token type", code="INVALID_TOKEN")

    return payload
