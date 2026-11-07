"""Rate limiting service using fixed-window Redis counters.

Adheres to CONVENTIONS.md: clear separation between window calculations and Redis storage.
"""

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_async

logger = get_logger("rate_limit")


@dataclass(frozen=True)
class RateLimitResult:
    """Result of rate limit check."""

    allowed: bool
    retry_after: int


def compute_fixed_window(
    now_timestamp: int,
    window_seconds: int,
) -> tuple[int, int]:
    """Compute (window_bucket, retry_after_seconds) for a fixed time window."""
    window_bucket = now_timestamp // window_seconds
    retry_after = ((window_bucket + 1) * window_seconds) - now_timestamp
    return window_bucket, max(1, retry_after)


async def check_rate_limit(
    redis_client: "redis_async.Redis",
    *,
    prefix: str,
    identifier: str,
    limit: int,
    window_seconds: int,
    now_timestamp: int | None = None,
) -> RateLimitResult:
    """Check fixed-window rate limit using Redis INCR and EXPIRE.

    Returns RateLimitResult(allowed=True/False, retry_after=seconds).
    """
    current_time = now_timestamp if now_timestamp is not None else int(time.time())
    bucket, retry_after = compute_fixed_window(current_time, window_seconds)
    key = f"rl:{prefix}:{identifier}:{bucket}"

    try:
        # Atomic increment
        count = await redis_client.incr(key)
        if count == 1:
            # Set TTL slightly longer than window duration
            await redis_client.expire(key, window_seconds + 5)

        if count > limit:
            return RateLimitResult(allowed=False, retry_after=retry_after)

        return RateLimitResult(allowed=True, retry_after=0)
    except Exception as exc:
        logger.warning(
            "rate_limit_check_failed",
            prefix=prefix,
            identifier=identifier,
            error=str(exc),
        )
        # Fail-open in event of Redis connection failure so users are not locked out
        return RateLimitResult(allowed=True, retry_after=0)
