"""CLI entrypoints for manual operations: sync-nav and backfill-nav."""

import asyncio
import sys

from app.core.db import get_db_session
from app.repositories.funds import FundRepository
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


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m app.cli [sync-nav | backfill-nav <scheme_code>]")
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
    else:
        print(f"Unknown command '{cmd}'. Available commands: sync-nav, backfill-nav")
        sys.exit(1)


if __name__ == "__main__":
    main()
