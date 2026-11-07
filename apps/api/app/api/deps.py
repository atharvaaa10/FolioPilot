"""Common API dependencies for authentication, database, clock, and request context."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated

import redis.asyncio as redis_async
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session as _get_db_session
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.redis import get_redis_client as _get_redis_client
from app.models.user import User
from app.repositories.users import UserRepository
from app.services.security import decode_access_token


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding an active database session."""
    async for session in _get_db_session():
        yield session


def get_redis_client() -> redis_async.Redis:
    """Dependency providing the async Redis client."""
    return _get_redis_client()


def get_clock() -> datetime:
    """Dependency providing the current UTC time. Can be overridden in tests."""
    return datetime.now(UTC)


def get_client_ip(request: Request) -> str:
    """Extract client IP respecting TRUST_PROXY_HEADERS configuration."""
    settings = get_settings()
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def verify_csrf_origin(request: Request) -> None:
    """Reject state-changing or cookie-authenticated requests with unapproved Origin."""
    origin = request.headers.get("origin")
    if origin is not None:
        settings = get_settings()
        if origin not in settings.CORS_ORIGINS:
            raise ForbiddenError(
                "Cross-origin request rejected for security",
                code="FORBIDDEN",
            )


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Extract, decode, and validate the JWT Bearer access token."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError(
            "Missing or malformed Authorization header",
            code="INVALID_TOKEN",
        )

    token = auth_header[7:].strip()
    settings = get_settings()
    payload = decode_access_token(
        token,
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise UnauthorizedError("Token missing subject claim", code="INVALID_TOKEN")

    try:
        user_id = uuid.UUID(str(user_id_raw))
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("Malformed user ID in token", code="INVALID_TOKEN") from exc

    user = await UserRepository.get_by_id(session, user_id)
    if user is None:
        raise UnauthorizedError("User does not exist", code="INVALID_TOKEN")

    if not user.is_active:
        raise ForbiddenError("User account is inactive", code="FORBIDDEN")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
