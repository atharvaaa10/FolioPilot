"""Redis distributed lock with owner-checked token release."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.core.logging import get_logger

logger = get_logger("core.redis_lock")

_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


async def acquire_lock(
    redis_client: Any,
    key: str,
    timeout_seconds: int = 600,
    owner_token: str | None = None,
) -> str | None:
    """Acquire a Redis lock with SET NX EX.

    Returns the owner token if acquired, or None if lock is already held.
    """
    token = owner_token or str(uuid.uuid4())
    acquired = await redis_client.set(key, token, nx=True, ex=timeout_seconds)
    if acquired:
        return token
    return None


async def release_lock(
    redis_client: Any,
    key: str,
    owner_token: str,
) -> bool:
    """Release a Redis lock atomically only if the owner token matches."""
    try:
        result = await redis_client.eval(_RELEASE_LOCK_LUA, 1, key, owner_token)
        return bool(result)
    except Exception as exc:
        logger.warning(
            "Failed to release Redis lock cleanly",
            lock_key=key,
            error=str(exc),
        )
        return False


@asynccontextmanager
async def distributed_lock(
    redis_client: Any,
    key: str,
    timeout_seconds: int = 600,
) -> AsyncIterator[str | None]:
    """Async context manager for acquiring and safely releasing a distributed lock.

    Yields owner_token if acquired, or None if already held.
    """
    token = await acquire_lock(redis_client, key, timeout_seconds=timeout_seconds)
    try:
        yield token
    finally:
        if token is not None:
            await release_lock(redis_client, key, token)
