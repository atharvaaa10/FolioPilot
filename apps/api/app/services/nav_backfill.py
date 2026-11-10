"""Orchestrator for backfilling NAV history from mfapi.in."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.mfapi import MfapiClient
from app.core.logging import get_logger
from app.models.fund import Fund
from app.models.sync_run import NavSyncRun
from app.repositories.nav_history import NavHistoryRepository
from app.repositories.sync_runs import SyncRunRepository
from app.services.mfapi_parser import parse_mfapi_history
from app.services.nav_rules import should_update_latest

logger = get_logger("services.nav_backfill")


async def backfill_fund_nav_history(
    session: AsyncSession,
    fund: Fund,
    mfapi_client: MfapiClient | None = None,
    clock: Callable[[], datetime] | None = None,
) -> NavSyncRun:
    """Fetch and persist complete historical NAV series for a tracked fund."""
    now_fn = clock or (lambda: datetime.now(UTC))
    start_time = now_fn()
    client = mfapi_client or MfapiClient()

    run = await SyncRunRepository.create_run(
        session,
        source="mfapi_backfill",
        fund_id=fund.id,
        started_at=start_time,
    )
    await session.commit()

    try:
        payload = await client.fetch_scheme_history(fund.scheme_code)
    except Exception as exc:
        logger.error(
            "Failed to fetch mfapi history",
            scheme_code=fund.scheme_code,
            error=str(exc),
        )
        await SyncRunRepository.finish_run(
            session,
            run=run,
            status="failed",
            error_summary=str(exc),
            finished_at=now_fn(),
        )
        await session.commit()
        return run

    parsed_result = parse_mfapi_history(payload)
    if not parsed_result.points:
        logger.warning(
            "mfapi history returned no valid points",
            scheme_code=fund.scheme_code,
            total_points=parsed_result.total_points,
            skipped_points=parsed_result.skipped_points,
        )
        await SyncRunRepository.finish_run(
            session,
            run=run,
            status="failed",
            schemes_parsed=1,
            nav_rows_written=0,
            error_summary="No valid historical NAV points found in response",
            finished_at=now_fn(),
        )
        await session.commit()
        return run

    # Prepare historical records
    history_records = [
        {
            "fund_id": fund.id,
            "nav_date": pt.nav_date,
            "nav": pt.nav,
        }
        for pt in parsed_result.points
    ]

    nav_rows_written = await NavHistoryRepository.upsert_nav_batch(session, history_records)

    # Check if latest historical point should update the fund's latest NAV
    # mfapi data is typically ordered descending (newest first)
    sorted_points = sorted(parsed_result.points, key=lambda p: p.nav_date, reverse=True)
    newest_point = sorted_points[0]

    if should_update_latest(fund.latest_nav_date, newest_point.nav_date):
        fund.latest_nav = newest_point.nav
        fund.latest_nav_date = newest_point.nav_date
        await session.flush()
    elif fund.latest_nav is not None and fund.latest_nav_date is not None:
        if fund.latest_nav_date > newest_point.nav_date:
            extra_record = [
                {
                    "fund_id": fund.id,
                    "nav_date": fund.latest_nav_date,
                    "nav": fund.latest_nav,
                }
            ]
            extra_written = await NavHistoryRepository.upsert_nav_batch(session, extra_record)
            nav_rows_written += extra_written

    await SyncRunRepository.finish_run(
        session,
        run=run,
        status="success",
        schemes_parsed=1,
        nav_rows_written=nav_rows_written,
        finished_at=now_fn(),
    )
    await session.commit()
    logger.info(
        "mfapi backfill completed successfully",
        scheme_code=fund.scheme_code,
        nav_rows_written=nav_rows_written,
    )

    try:
        from app.workers.tasks import execute_pending_for_fund

        execute_pending_for_fund.delay(str(fund.id))
    except Exception as exc:
        logger.warning(
            "Could not enqueue execute_pending_for_fund after backfill",
            fund_id=str(fund.id),
            error=str(exc),
        )

    return run


async def ensure_tracked(
    session: AsyncSession,
    fund: Fund,
    enqueue_task: bool = True,
) -> tuple[bool, bool]:
    """Ensure fund is flagged as tracked and enqueue backfill if no history exists.

    Returns (is_tracked, backfill_enqueued).
    """
    fund.is_tracked = True
    await session.flush()

    has_history = await NavHistoryRepository.has_history(session, fund.id)
    backfill_enqueued = False

    if not has_history and enqueue_task:
        try:
            from app.workers.tasks import backfill_nav_history

            backfill_nav_history.delay(str(fund.id))
            backfill_enqueued = True
        except Exception as exc:
            logger.warning(
                "Could not enqueue backfill task directly",
                fund_id=str(fund.id),
                error=str(exc),
            )

    return True, backfill_enqueued
