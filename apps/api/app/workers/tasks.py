"""Celery background tasks for FolioPilot."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.logging import get_logger
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.workers.celery_app import celery_app

logger = get_logger("workers.tasks")


@celery_app.task(name="ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    """Trivial ping task to verify Celery worker connectivity."""
    return "pong"


async def _async_purge_expired_tokens(
    retention_days: int = 7,
    db_url: str | None = None,
) -> int:
    """Execute asynchronous database purge of old expired refresh tokens with dedicated engine."""
    settings = get_settings()
    target_url = db_url or (
        settings.TEST_DATABASE_URL
        if ("pytest" in sys.modules or settings.ENVIRONMENT == "test")
        else settings.DATABASE_URL
    )
    engine = create_async_engine(target_url, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    try:
        async with session_factory() as session:
            count = await RefreshTokenRepository.delete_expired_before(session, cutoff)
            await session.commit()
            return count
    finally:
        await engine.dispose()


@celery_app.task(name="purge_expired_refresh_tokens")  # type: ignore[untyped-decorator]
def purge_expired_refresh_tokens(
    retention_days: int = 7,
    db_url: str | None = None,
) -> int:
    """Purge refresh tokens that expired more than retention_days ago."""
    count = asyncio.run(_async_purge_expired_tokens(retention_days=retention_days, db_url=db_url))
    logger.info("purged_expired_refresh_tokens", deleted_count=count)
    return count
