"""Unit tests for Redis distributed lock with owner-token release."""

import asyncio

from app.core.redis_lock import acquire_lock, distributed_lock, release_lock


class FakeAsyncRedis:
    """In-memory Redis fake implementing SET NX EX and Lua owner-checked release."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    async def eval(
        self,
        script: str,
        numkeys: int,
        key: str,
        owner_token: str,
    ) -> int:
        current = self.store.get(key)
        if current == owner_token:
            del self.store[key]
            return 1
        return 0


def test_redis_lock_lifecycle() -> None:
    async def _run() -> None:
        fake_redis = FakeAsyncRedis()
        lock_key = "test:lock:1"

        # Acquire lock
        token1 = await acquire_lock(fake_redis, lock_key, timeout_seconds=10)
        assert token1 is not None

        # Concurrent attempt fails
        token2 = await acquire_lock(fake_redis, lock_key, timeout_seconds=10)
        assert token2 is None

        # Release with wrong token fails and keeps lock
        released_bad = await release_lock(fake_redis, lock_key, "wrong-token")
        assert released_bad is False
        assert lock_key in fake_redis.store

        # Release with correct token succeeds
        released_good = await release_lock(fake_redis, lock_key, token1)
        assert released_good is True
        assert lock_key not in fake_redis.store

        # Can acquire again after release
        token3 = await acquire_lock(fake_redis, lock_key, timeout_seconds=10)
        assert token3 is not None

    asyncio.run(_run())


def test_distributed_lock_context_manager() -> None:
    async def _run() -> None:
        fake_redis = FakeAsyncRedis()
        lock_key = "test:lock:ctx"

        async with distributed_lock(fake_redis, lock_key) as token:
            assert token is not None
            assert lock_key in fake_redis.store

            # Sub-attempt while in context fails
            token_inner = await acquire_lock(fake_redis, lock_key)
            assert token_inner is None

        # Released upon exiting context
        assert lock_key not in fake_redis.store

    asyncio.run(_run())
