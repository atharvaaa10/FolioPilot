"""Repository for tracking NAV synchronization and backfill runs."""

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_run import NavSyncRun


def sanitize_error_summary(error: str | None) -> str | None:
    """Sanitize error message to prevent URL credentials or stack traces from being stored."""
    if not error:
        return None
    # Strip URL passwords/tokens: http://user:pass@host -> http://user:***@host
    sanitized = re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", error)
    # Strip Authorization/Bearer tokens
    sanitized = re.sub(
        r"(Bearer\s+)[A-Za-z0-9._~+/-]+",
        r"\1***",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Truncate to first 500 chars to avoid storing raw multiline tracebacks
    lines = sanitized.splitlines()
    first_few = " ".join(line.strip() for line in lines[:3] if line.strip())
    return first_few[:500]


class SyncRunRepository:
    """Thin repository handling nav_sync_runs CRUD operations."""

    @staticmethod
    async def create_run(
        session: AsyncSession,
        source: str,
        fund_id: UUID | None = None,
        started_at: datetime | None = None,
    ) -> NavSyncRun:
        """Create a new pending sync run record."""
        now = started_at or datetime.now(UTC)
        run = NavSyncRun(
            source=source,
            fund_id=fund_id,
            status="running",
            started_at=now,
            schemes_parsed=0,
            funds_created=0,
            funds_updated=0,
            nav_rows_written=0,
        )
        session.add(run)
        await session.flush()
        return run

    @staticmethod
    async def finish_run(
        session: AsyncSession,
        run: NavSyncRun,
        status: str,
        schemes_parsed: int = 0,
        funds_created: int = 0,
        funds_updated: int = 0,
        nav_rows_written: int = 0,
        error_summary: str | None = None,
        finished_at: datetime | None = None,
    ) -> NavSyncRun:
        """Finalize a sync run record with completion metrics."""
        finish_time = finished_at or datetime.now(UTC)
        duration_ms = int((finish_time - run.started_at).total_seconds() * 1000)

        run.status = status
        run.finished_at = finish_time
        run.schemes_parsed = schemes_parsed
        run.funds_created = funds_created
        run.funds_updated = funds_updated
        run.nav_rows_written = nav_rows_written
        run.error_summary = sanitize_error_summary(error_summary)
        run.duration_ms = max(0, duration_ms)

        await session.flush()
        return run

    @staticmethod
    async def get_last_amfi_run_status(
        session: AsyncSession,
    ) -> tuple[NavSyncRun | None, NavSyncRun | None]:
        """Fetch the most recent AMFI sync run and the most recent successful AMFI sync run."""
        latest_stmt = (
            select(NavSyncRun)
            .where(NavSyncRun.source == "amfi_navall")
            .order_by(NavSyncRun.started_at.desc())
            .limit(1)
        )
        latest_res = await session.execute(latest_stmt)
        latest_run = latest_res.scalar_one_or_none()

        latest_success_stmt = (
            select(NavSyncRun)
            .where(
                NavSyncRun.source == "amfi_navall",
                NavSyncRun.status == "success",
            )
            .order_by(NavSyncRun.started_at.desc())
            .limit(1)
        )
        latest_success_res = await session.execute(latest_success_stmt)
        latest_success_run = latest_success_res.scalar_one_or_none()

        return latest_run, latest_success_run
