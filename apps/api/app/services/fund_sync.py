"""Orchestrator for syncing AMFI fund master and daily NAVs."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.amfi import AmfiClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.sync_run import NavSyncRun
from app.repositories.funds import FundRepository
from app.repositories.nav_history import NavHistoryRepository
from app.repositories.sync_runs import SyncRunRepository
from app.services.amfi_parser import ParsedScheme, parse_navall
from app.services.fund_classification import classify_fund, normalize_name
from app.services.nav_rules import evaluate_sanity_guard

logger = get_logger("services.fund_sync")


async def sync_amfi_funds_and_nav(
    session: AsyncSession,
    amfi_client: AmfiClient | None = None,
    clock: Callable[[], datetime] | None = None,
    min_schemes: int | None = None,
    inactive_after_days: int | None = None,
) -> NavSyncRun:
    """Orchestrate downloading, parsing, guarding, upserting, and deactivating funds."""
    settings = get_settings()
    now_fn = clock or (lambda: datetime.now(UTC))
    start_time = now_fn()
    client = amfi_client or AmfiClient()
    min_schemes_val = min_schemes if min_schemes is not None else settings.FUND_SYNC_MIN_SCHEMES
    inactive_days_val = (
        inactive_after_days
        if inactive_after_days is not None
        else settings.FUND_INACTIVE_AFTER_DAYS
    )

    run = await SyncRunRepository.create_run(
        session,
        source="amfi_navall",
        started_at=start_time,
    )
    await session.commit()

    # Step 1: Download AMFI NAVAll.txt
    try:
        raw_text = await client.fetch_navall()
    except Exception as exc:
        logger.error("Failed to fetch AMFI NAVAll", error=str(exc))
        await SyncRunRepository.finish_run(
            session,
            run=run,
            status="failed",
            error_summary=str(exc),
            finished_at=now_fn(),
        )
        await session.commit()
        return run

    # Step 2: Parse raw text
    parse_result = parse_navall(raw_text)
    schemes_count = len(parse_result.schemes)

    # Step 3: Run sanity guard
    active_count = await FundRepository.count_active(session)
    is_sane, abort_reason = evaluate_sanity_guard(
        parsed_count=schemes_count,
        active_count=active_count,
        min_schemes=min_schemes_val,
        is_valid_format=True,
    )

    if not is_sane:
        logger.error(
            "AMFI sync aborted by sanity guard",
            parsed_count=schemes_count,
            active_count=active_count,
            reason=abort_reason,
        )
        await SyncRunRepository.finish_run(
            session,
            run=run,
            status="aborted",
            schemes_parsed=schemes_count,
            error_summary=abort_reason,
            finished_at=now_fn(),
        )
        await session.commit()
        return run

    # Step 4: Map parsed schemes to Fund records
    fund_records: list[dict[str, Any]] = []
    parsed_by_code: dict[int, ParsedScheme] = {}
    for p in parse_result.schemes:
        parsed_by_code[p.scheme_code] = p
        classification = classify_fund(
            name=p.name,
            category_raw=p.category_raw,
            plan_raw=p.plan_raw,
            option_raw=p.option_raw,
        )
        norm_name = normalize_name(p.name)

        record: dict[str, Any] = {
            "scheme_code": p.scheme_code,
            "isin_growth": p.isin_growth,
            "isin_reinvest": p.isin_reinvest,
            "name": p.name,
            "name_normalized": norm_name,
            "amc": p.amc,
            "scheme_type_raw": p.scheme_type_raw,
            "category_raw": p.category_raw,
            "asset_class": classification.asset_class,
            "sub_category": classification.sub_category,
            "classification_source": classification.classification_source,
            "plan_type": classification.plan_type,
            "option_type": classification.option_type,
            "latest_nav": p.nav,
            "latest_nav_date": p.nav_date,
            "is_active": True,
            "first_seen_at": start_time,
            "last_seen_at": start_time,
        }
        fund_records.append(record)

    # Step 5: Upsert funds in batches
    created, updated = await FundRepository.upsert_funds_batch(session, fund_records)

    # Keep last_seen_at fresh without row churn: touch funds that weren't updated in >=12h
    seen_scheme_codes = [p.scheme_code for p in parse_result.schemes]
    await FundRepository.touch_last_seen(
        session,
        scheme_codes=seen_scheme_codes,
        seen_at=start_time,
        cutoff=start_time - timedelta(hours=12),
    )

    # Step 6: Write NAV history row for currently tracked funds only
    tracked_funds = await FundRepository.get_tracked_funds(session)
    history_records: list[dict[str, Any]] = []
    for tf in tracked_funds:
        scheme_item = parsed_by_code.get(tf.scheme_code)
        if (
            scheme_item is not None
            and scheme_item.nav is not None
            and scheme_item.nav_date is not None
        ):
            history_records.append(
                {
                    "fund_id": tf.id,
                    "nav_date": scheme_item.nav_date,
                    "nav": scheme_item.nav,
                }
            )

    nav_rows_written = 0
    if history_records:
        nav_rows_written = await NavHistoryRepository.upsert_nav_batch(session, history_records)

    # Step 7: Deactivate stale funds
    cutoff = start_time - timedelta(days=inactive_days_val)
    deactivated = await FundRepository.deactivate_stale(session, cutoff)
    logger.info(
        "AMFI sync completed successfully",
        schemes_parsed=schemes_count,
        funds_created=created,
        funds_updated=updated,
        nav_rows_written=nav_rows_written,
        funds_deactivated=deactivated,
    )

    # Step 8: Finalize run record
    await SyncRunRepository.finish_run(
        session,
        run=run,
        status="success",
        schemes_parsed=schemes_count,
        funds_created=created,
        funds_updated=updated,
        nav_rows_written=nav_rows_written,
        finished_at=now_fn(),
    )
    await session.commit()
    return run
