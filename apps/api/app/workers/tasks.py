"""Celery background tasks for FolioPilot."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from celery import Task
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.clients.amfi import AmfiClient, AmfiFetchError
from app.clients.mfapi import MfapiClient, MfapiFetchError
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis_lock import acquire_lock, release_lock
from app.repositories.funds import FundRepository
from app.repositories.imports import ImportRepository
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.sync_runs import SyncRunRepository
from app.services.fund_sync import sync_amfi_funds_and_nav
from app.services.nav_backfill import backfill_fund_nav_history
from app.services.sip_executor import SipExecutor
from app.workers.celery_app import celery_app

logger = get_logger("workers.tasks")

LOCK_KEY_AMFI_SYNC = "lock:sync_amfi_nav"
LOCK_TIMEOUT_AMFI_SYNC = 900  # 15 minutes

LOCK_KEY_SIP_EXECUTION = "lock:execute_due_sip_installments"
LOCK_TIMEOUT_SIP_EXECUTION = 600  # 10 minutes


@celery_app.task(name="ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    """Trivial ping task to verify Celery worker connectivity."""
    return "pong"


def _get_target_db_url(db_url: str | None = None) -> str:
    settings = get_settings()
    if db_url:
        return db_url
    if "pytest" in sys.modules or settings.ENVIRONMENT == "test":
        return settings.TEST_DATABASE_URL
    return settings.DATABASE_URL


def _get_target_redis_url(redis_url: str | None = None) -> str:
    settings = get_settings()
    if redis_url:
        return redis_url
    if "pytest" in sys.modules or settings.ENVIRONMENT == "test":
        return settings.TEST_REDIS_URL
    return settings.REDIS_URL


async def _async_purge_expired_tokens(
    retention_days: int = 7,
    db_url: str | None = None,
) -> int:
    """Execute asynchronous database purge of old expired refresh tokens with dedicated engine."""
    target_url = _get_target_db_url(db_url)
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


async def _async_sync_amfi_nav(
    db_url: str | None = None,
    redis_url: str | None = None,
    amfi_client: AmfiClient | None = None,
) -> dict[str, Any]:
    """Execute AMFI NAV synchronization with distributed locking and standalone session."""
    target_db = _get_target_db_url(db_url)
    target_redis = _get_target_redis_url(redis_url)

    engine = create_async_engine(target_db, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    redis_pool = ConnectionPool.from_url(
        target_redis,
        encoding="utf-8",
        decode_responses=True,
    )
    redis_client = Redis(connection_pool=redis_pool)

    owner_token: str | None = None
    try:
        owner_token = await acquire_lock(
            redis_client,
            LOCK_KEY_AMFI_SYNC,
            timeout_seconds=LOCK_TIMEOUT_AMFI_SYNC,
        )

        if owner_token is None:
            # Another sync is actively in progress: exit as skipped and record run
            logger.info("AMFI sync skipped: lock held by another worker")
            async with session_factory() as session:
                run = await SyncRunRepository.create_run(
                    session,
                    source="amfi_navall",
                )
                await SyncRunRepository.finish_run(
                    session,
                    run=run,
                    status="skipped",
                    error_summary="Concurrent sync in progress; lock held.",
                )
                await session.commit()
            return {"status": "skipped", "reason": "lock_held"}

        async with session_factory() as session:
            run = await sync_amfi_funds_and_nav(
                session,
                amfi_client=amfi_client,
            )
            return {
                "status": run.status,
                "schemes_parsed": run.schemes_parsed,
                "funds_created": run.funds_created,
                "funds_updated": run.funds_updated,
                "nav_rows_written": run.nav_rows_written,
                "error_summary": run.error_summary,
            }
    finally:
        if owner_token is not None:
            await release_lock(redis_client, LOCK_KEY_AMFI_SYNC, owner_token)
        await redis_client.aclose()
        await redis_pool.disconnect()
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="sync_amfi_nav",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_amfi_nav(
    self: Task,
    db_url: str | None = None,
    redis_url: str | None = None,
) -> dict[str, Any]:
    """Celery task to run daily AMFI NAV sync with retries on network failures."""
    try:
        return asyncio.run(_async_sync_amfi_nav(db_url=db_url, redis_url=redis_url))
    except AmfiFetchError as exc:
        logger.warning(
            "AMFI fetch error during celery task execution; scheduling retry",
            retry_count=self.request.retries,
            error=str(exc),
        )
        raise self.retry(exc=exc) from exc


async def _async_backfill_nav_history(
    fund_id_str: str,
    db_url: str | None = None,
    mfapi_client: MfapiClient | None = None,
) -> dict[str, Any]:
    """Execute historical NAV backfill for a single fund."""
    target_db = _get_target_db_url(db_url)
    engine = create_async_engine(target_db, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        fund_id = UUID(fund_id_str)
    except ValueError:
        return {"status": "failed", "error": f"Invalid UUID: {fund_id_str}"}

    try:
        async with session_factory() as session:
            fund = await FundRepository.get_by_id(session, fund_id)
            if fund is None:
                logger.error("Fund not found for backfill", fund_id=fund_id_str)
                return {"status": "failed", "error": "Fund not found"}

            run = await backfill_fund_nav_history(
                session,
                fund=fund,
                mfapi_client=mfapi_client,
            )
            if run.status == "success":
                try:
                    execute_pending_for_fund.delay(fund_id_str)
                except Exception as exc:
                    logger.warning(
                        "Could not enqueue execute_pending_for_fund after backfill",
                        fund_id=fund_id_str,
                        error=str(exc),
                    )
            return {
                "status": run.status,
                "nav_rows_written": run.nav_rows_written,
                "error_summary": run.error_summary,
            }
    finally:
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="backfill_nav_history",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def backfill_nav_history(
    self: Task,
    fund_id_str: str,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Celery task to backfill historical NAV points for a tracked fund."""
    try:
        return asyncio.run(_async_backfill_nav_history(fund_id_str=fund_id_str, db_url=db_url))
    except MfapiFetchError as exc:
        logger.warning(
            "mfapi fetch error during backfill task; scheduling retry",
            retry_count=self.request.retries,
            error=str(exc),
        )
        raise self.retry(exc=exc) from exc


async def _async_execute_due_sip_installments(
    db_url: str | None = None,
    redis_url: str | None = None,
) -> dict[str, Any]:
    """Generate due installments and execute pending ones across all active SIPs."""
    target_db = _get_target_db_url(db_url)
    target_redis = _get_target_redis_url(redis_url)

    engine = create_async_engine(target_db, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    redis_pool = ConnectionPool.from_url(
        target_redis,
        encoding="utf-8",
        decode_responses=True,
    )
    redis_client = Redis(connection_pool=redis_pool)

    owner_token: str | None = None
    try:
        owner_token = await acquire_lock(
            redis_client,
            LOCK_KEY_SIP_EXECUTION,
            timeout_seconds=LOCK_TIMEOUT_SIP_EXECUTION,
        )

        if owner_token is None:
            logger.info("SIP installment execution skipped: lock held by another worker")
            return {"status": "skipped", "reason": "lock_held"}

        # 1. Generate due installments
        async with session_factory() as session:
            gen_count = await SipExecutor.generate_due_installments(session)

        # 2. Execute pending installments
        exec_stats = await SipExecutor.execute_pending(session_factory)
        return {
            "status": "success",
            "installments_generated": gen_count,
            **exec_stats,
        }
    finally:
        if owner_token is not None:
            await release_lock(redis_client, LOCK_KEY_SIP_EXECUTION, owner_token)
        await redis_client.aclose()
        await redis_pool.disconnect()
        await engine.dispose()


@celery_app.task(name="execute_due_sip_installments")  # type: ignore[untyped-decorator]
def execute_due_sip_installments(
    db_url: str | None = None,
    redis_url: str | None = None,
) -> dict[str, Any]:
    """Execute all pending SIP installments and generate due ones."""
    res = asyncio.run(_async_execute_due_sip_installments(db_url=db_url, redis_url=redis_url))
    logger.info("executed_due_sip_installments", result=res)
    return res


async def _async_execute_pending_for_fund(
    fund_id_str: str,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Execute pending installments specifically for one fund."""
    target_db = _get_target_db_url(db_url)
    engine = create_async_engine(target_db, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        fund_id = UUID(fund_id_str)
        return await SipExecutor.execute_pending(session_factory, fund_id=fund_id)
    finally:
        await engine.dispose()


@celery_app.task(name="execute_pending_for_fund")  # type: ignore[untyped-decorator]
def execute_pending_for_fund(
    fund_id_str: str,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Execute pending installments specifically for one fund."""
    return asyncio.run(_async_execute_pending_for_fund(fund_id_str=fund_id_str, db_url=db_url))


async def _async_purge_expired_import_previews(db_url: str | None = None) -> int:
    """Execute asynchronous database purge of expired previewed imports with dedicated engine."""
    target_url = _get_target_db_url(db_url)
    engine = create_async_engine(target_url, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    now_utc = datetime.now(UTC)
    try:
        async with session_factory() as session:
            count = await ImportRepository.purge_expired_previews(session, now_utc)
            await session.commit()
            logger.info("purged_expired_import_previews", count=count)
            return count
    finally:
        await engine.dispose()


@celery_app.task(name="purge_expired_import_previews")  # type: ignore[untyped-decorator]
def purge_expired_import_previews(db_url: str | None = None) -> int:
    """Daily Celery Beat task to purge expired transaction import previews."""
    return asyncio.run(_async_purge_expired_import_previews(db_url=db_url))
