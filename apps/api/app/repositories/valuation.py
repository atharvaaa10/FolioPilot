"""Repository for valuation, portfolio ledger aggregation, and historical NAV lookups."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.nav_history import NavHistory
from app.models.transaction import Transaction


class ValuationRepository:
    """Thin repository executing batch queries without N+1 patterns."""

    @staticmethod
    async def list_transactions_for_portfolios(
        session: AsyncSession,
        portfolio_ids: list[UUID],
    ) -> list[Transaction]:
        """Fetch all ledger transactions for a set of portfolios joined to fund metadata."""
        if not portfolio_ids:
            return []

        stmt = (
            select(Transaction)
            .where(Transaction.portfolio_id.in_(portfolio_ids))
            .options(joinedload(Transaction.fund))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_nav_points_in_range(
        session: AsyncSession,
        fund_ids: set[UUID],
        start_date: date,
        end_date: date,
    ) -> list[NavHistory]:
        """Fetch all official historical NAV points for funds within date range in one query."""
        if not fund_ids:
            return []

        stmt = (
            select(NavHistory)
            .where(
                NavHistory.fund_id.in_(fund_ids),
                NavHistory.nav_date >= start_date,
                NavHistory.nav_date <= end_date,
            )
            .order_by(NavHistory.nav_date.asc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_last_nav_before_date(
        session: AsyncSession,
        fund_ids: set[UUID],
        before_date: date,
    ) -> list[NavHistory]:
        """Fetch the most recent official NAV point prior to before_date per fund (DISTINCT ON)."""
        if not fund_ids:
            return []

        stmt = (
            select(NavHistory)
            .where(
                NavHistory.fund_id.in_(fund_ids),
                NavHistory.nav_date < before_date,
            )
            .distinct(NavHistory.fund_id)
            .order_by(NavHistory.fund_id, NavHistory.nav_date.desc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())
