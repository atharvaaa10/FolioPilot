"""Repository for querying and upserting historical NAV records."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nav_history import NavHistory


class NavHistoryRepository:
    """Thin repository handling historical NAV queries and batch upserts."""

    @staticmethod
    async def get_history(
        session: AsyncSession,
        fund_id: UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int | None = None,
    ) -> list[NavHistory]:
        """Fetch NAV history for a fund ordered chronologically ascending."""
        stmt = select(NavHistory).where(NavHistory.fund_id == fund_id)

        if from_date is not None:
            stmt = stmt.where(NavHistory.nav_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(NavHistory.nav_date <= to_date)

        stmt = stmt.order_by(NavHistory.nav_date.asc())

        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def has_history(session: AsyncSession, fund_id: UUID) -> bool:
        """Check whether any NAV history rows exist for a fund."""
        stmt = select(func.count(NavHistory.id)).where(NavHistory.fund_id == fund_id)
        result = await session.execute(stmt)
        count = result.scalar_one() or 0
        return count > 0

    @staticmethod
    async def upsert_nav_batch(
        session: AsyncSession,
        records: list[dict[str, Any]],
        batch_size: int = 1000,
    ) -> int:
        """Batch upsert NAV history records using ON CONFLICT (fund_id, nav_date) DO UPDATE.

        Returns total rows written.
        """
        if not records:
            return 0

        rows_written = 0

        for i in range(0, len(records), batch_size):
            chunk = records[i : i + batch_size]
            insert_stmt = insert(NavHistory).values(chunk)

            stmt = insert_stmt.on_conflict_do_update(
                index_elements=["fund_id", "nav_date"],
                set_={"nav": insert_stmt.excluded.nav},
            )

            res = await session.execute(stmt)
            count = res.rowcount if isinstance(res, CursorResult) else len(chunk)
            rows_written += count or len(chunk)

        return rows_written
