from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings

_pool: ConnectionPool | None = None
_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return shared async Redis client."""
    global _pool, _client
    if _client is None:
        settings = get_settings()
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        _client = Redis(connection_pool=_pool)
    return _client


async def close_redis_client() -> None:
    """Gracefully close Redis connections."""
    global _client, _pool
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


async def check_redis_health(client: Redis | None = None) -> bool:
    """Verify Redis connectivity by issuing a PING command."""
    redis_instance = client or get_redis_client()
    pong = await redis_instance.ping()
    return bool(pong)
