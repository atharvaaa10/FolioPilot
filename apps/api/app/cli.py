"""CLI entrypoints for manual operations: sync-nav, backfill-nav, and reclassify."""

import asyncio
import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models.fund import Fund
from app.repositories.funds import FundRepository
from app.services.fund_classification import classify_fund
from app.services.nav_backfill import backfill_fund_nav_history
from app.workers.tasks import sync_amfi_nav


def run_sync_nav() -> None:
    """Trigger manual AMFI NAV sync and print summary results."""
    print("Initiating manual AMFI NAV sync...")
    result = sync_amfi_nav()
    print("AMFI NAV sync completed with summary:")
    for k, v in result.items():
        print(f"  {k}: {v}")


async def _async_backfill(scheme_code: int) -> None:
    print(f"Initiating historical NAV backfill for scheme_code={scheme_code}...")
    async for session in get_db_session():
        fund = await FundRepository.get_by_scheme_code(session, scheme_code)
        if fund is None:
            print(f"Error: Fund with scheme code {scheme_code} not found in database.")
            sys.exit(1)
        fund.is_tracked = True
        await session.flush()
        run = await backfill_fund_nav_history(session, fund)
        print("Backfill completed with summary:")
        print(f"  status: {run.status}")
        print(f"  schemes_parsed: {run.schemes_parsed}")
        print(f"  nav_rows_written: {run.nav_rows_written}")
        print(f"  duration_ms: {run.duration_ms}")
        if run.error_summary:
            print(f"  error_summary: {run.error_summary}")
        break


def run_backfill_nav(scheme_code_str: str) -> None:
    try:
        code = int(scheme_code_str)
    except ValueError:
        print(f"Error: Invalid scheme code '{scheme_code_str}', must be an integer.")
        sys.exit(1)
    asyncio.run(_async_backfill(code))


async def _get_distribution(session: AsyncSession) -> list[tuple[str, str, int]]:
    stmt = (
        select(Fund.asset_class, Fund.classification_source, func.count(Fund.id))
        .group_by(Fund.asset_class, Fund.classification_source)
        .order_by(func.count(Fund.id).desc())
    )
    res = await session.execute(stmt)
    return [(str(r[0]), str(r[1]), int(r[2])) for r in res.all()]


async def _async_reclassify() -> None:
    print("Starting database fund reclassification from stored name and category_raw...")
    async for session in get_db_session():
        # Before distribution
        dist_before = await _get_distribution(session)

        # Process in batches
        batch_size = 1000
        offset = 0
        total_reclassified = 0

        while True:
            stmt = select(Fund).order_by(Fund.scheme_code).limit(batch_size).offset(offset)
            res = await session.execute(stmt)
            funds_batch = res.scalars().all()
            if not funds_batch:
                break

            for fund in funds_batch:
                cls = classify_fund(
                    name=fund.name,
                    category_raw=fund.category_raw,
                    plan_raw=fund.plan_type,
                    option_raw=fund.option_type,
                )
                fund.asset_class = cls.asset_class
                fund.sub_category = cls.sub_category
                fund.classification_source = cls.classification_source
                fund.plan_type = cls.plan_type
                fund.option_type = cls.option_type

            await session.flush()
            total_reclassified += len(funds_batch)
            offset += batch_size

        await session.commit()

        # After distribution
        dist_after = await _get_distribution(session)

        print("\n=== CLASSIFICATION DISTRIBUTION BEFORE ===")
        for ac, src, cnt in dist_before:
            print(f"  {ac:<12} | {src:<15} | {cnt:>6}")

        print("\n=== CLASSIFICATION DISTRIBUTION AFTER ===")
        for ac, src, cnt in dist_after:
            print(f"  {ac:<12} | {src:<15} | {cnt:>6}")

        # Count still other/unknown
        stmt_unknown = (
            select(Fund.scheme_code, Fund.name, Fund.category_raw)
            .where(Fund.asset_class == "other", Fund.classification_source == "unknown")
            .order_by(func.random())
            .limit(30)
        )
        res_unknown = await session.execute(stmt_unknown)
        unknown_sample = res_unknown.all()

        stmt_unknown_count = select(func.count(Fund.id)).where(
            Fund.asset_class == "other", Fund.classification_source == "unknown"
        )
        cnt_unknown = (await session.execute(stmt_unknown_count)).scalar_one() or 0

        print(f"\nTotal funds still other/unknown: {cnt_unknown}")
        print("\n=== 30 RANDOM REMAINING OTHER/UNKNOWN EXAMPLES ===")
        for r in unknown_sample:
            print(f"  [{r[0]}] {r[1]}  (Category: {r[2]})")

        break


def run_reclassify() -> None:
    asyncio.run(_async_reclassify())


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m app.cli [sync-nav | backfill-nav <scheme_code> | reclassify]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "sync-nav":
        run_sync_nav()
    elif cmd == "backfill-nav":
        if len(sys.argv) < 3:
            print(
                "Error: Missing scheme_code argument. "
                "Usage: python -m app.cli backfill-nav <scheme_code>"
            )
            sys.exit(1)
        run_backfill_nav(sys.argv[2])
    elif cmd == "reclassify":
        run_reclassify()
    else:
        print(f"Unknown command '{cmd}'. Available commands: sync-nav, backfill-nav, reclassify")
        sys.exit(1)


if __name__ == "__main__":
    main()
