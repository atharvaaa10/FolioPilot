"""Pytest configuration and test isolation fixtures.

Strictly enforces database and Redis isolation per CONVENTIONS.md:
- Refuses to run unless TEST_DATABASE_URL ends in '_test'
- Refuses to run unless TEST_REDIS_URL points to db index 1
- Automatically creates test database if it does not exist
- Flushes ONLY Redis db 1
- Never touches development database
"""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
import redis.asyncio as redis_async
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.api.deps import get_db_session, get_redis_client
from app.core.config import get_settings
from app.main import create_app

# Module-level singletons for test harness
_test_engine = None
_test_session_factory = None
_test_redis = None


def _validate_safety_gates() -> tuple[str, str]:
    """Strictly verify test database and Redis settings before executing any tests."""
    settings = get_settings()
    db_url = make_url(settings.TEST_DATABASE_URL)
    if not db_url.database or not db_url.database.endswith("_test"):
        raise RuntimeError(
            f"SAFETY REFUSAL: TEST_DATABASE_URL db '{db_url.database}' must end in '_test'!"
        )

    redis_url = settings.TEST_REDIS_URL
    if not (redis_url.endswith("/1") or "/1?" in redis_url):
        raise RuntimeError(
            f"SAFETY REFUSAL: TEST_REDIS_URL must use Redis database 1 (got '{redis_url}')!"
        )

    return settings.TEST_DATABASE_URL, settings.TEST_REDIS_URL


def _run_alembic_upgrade(test_db_url: str) -> None:
    """Run Alembic migrations programmatically against the test database."""
    root_dir = Path(__file__).resolve().parent.parent
    ini_path = root_dir / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    alembic_cfg.set_main_option("script_location", str(root_dir / "alembic"))
    command.upgrade(alembic_cfg, "head")


async def _init_test_db(test_db_url: str) -> None:
    """Ensure test database exists, has extensions, and all tables created."""
    parsed = make_url(test_db_url)
    db_name = parsed.database

    # Connect to maintenance database to create test database if absent
    admin_url = parsed.set(database="postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            check_query = text("SELECT 1 FROM pg_database WHERE datname = :name")
            exists = (await conn.execute(check_query, {"name": db_name})).scalar()
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await admin_engine.dispose()

    # Apply Alembic migrations (creates extensions and tables via 0001 and 0002)
    await asyncio.to_thread(_run_alembic_upgrade, test_db_url)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_infra() -> AsyncGenerator[None, None]:
    """Session fixture setting up test database and Redis infrastructure."""
    test_db_url, test_redis_url = _validate_safety_gates()

    global _test_engine, _test_session_factory

    await _init_test_db(test_db_url)

    _test_engine = create_async_engine(test_db_url, poolclass=NullPool)
    _test_session_factory = async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield

    if _test_engine is not None:
        await _test_engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_infra: None) -> AsyncGenerator[AsyncSession, None]:
    """Provide clean database session for an integration test, truncating before and after."""
    assert _test_session_factory is not None
    assert _test_engine is not None

    # Truncate tables cleanly before each test to guarantee fresh state
    async with _test_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE nav_sync_runs, nav_history, funds, refresh_tokens, users CASCADE;")
        )

    async with _test_session_factory() as session:
        yield session

    # Truncate tables cleanly between tests
    async with _test_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE nav_sync_runs, nav_history, funds, refresh_tokens, users CASCADE;")
        )


@pytest_asyncio.fixture
async def test_redis(test_infra: None) -> AsyncGenerator[redis_async.Redis, None]:
    """Provide clean Redis connection to database index 1, flushing before and after each test."""
    settings = get_settings()
    client = redis_async.from_url(
        settings.TEST_REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def client(
    test_session: AsyncSession,
    test_redis: redis_async.Redis,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient wired with test database session and Redis db 1."""
    test_app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    def override_redis() -> redis_async.Redis:
        return test_redis

    test_app.dependency_overrides[get_db_session] = override_db
    test_app.dependency_overrides[get_redis_client] = override_redis

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
