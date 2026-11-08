"""Repository for Portfolio master records and Target Allocations."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.portfolio import Portfolio, PortfolioTarget


class PortfolioRepository:
    """Repository handling Portfolio and PortfolioTarget database interactions."""

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID | None = None,
        load_targets: bool = False,
    ) -> Portfolio | None:
        """Fetch portfolio by ID, optionally enforcing user ownership."""
        stmt = select(Portfolio).where(Portfolio.id == portfolio_id)
        if user_id is not None:
            stmt = stmt.where(Portfolio.user_id == user_id)
        if load_targets:
            stmt = stmt.options(selectinload(Portfolio.targets))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_update(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID | None = None,
    ) -> Portfolio | None:
        """Pessimistically lock (SELECT ... FOR UPDATE) portfolio row for ledger mutation."""
        stmt = select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()
        if user_id is not None:
            stmt = stmt.where(Portfolio.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(
        session: AsyncSession,
        user_id: UUID,
        load_targets: bool = True,
    ) -> list[Portfolio]:
        """Fetch all portfolios belonging to a user, ordered by creation time."""
        stmt = (
            select(Portfolio)
            .where(Portfolio.user_id == user_id)
            .order_by(Portfolio.created_at.asc())
        )
        if load_targets:
            stmt = stmt.options(selectinload(Portfolio.targets))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_user(session: AsyncSession, user_id: UUID) -> int:
        """Count total portfolios owned by a user."""
        stmt = select(func.count(Portfolio.id)).where(Portfolio.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def exists_name_for_user(
        session: AsyncSession,
        user_id: UUID,
        name: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Check if lowercased portfolio name is already used by this user."""
        stmt = select(func.count(Portfolio.id)).where(
            Portfolio.user_id == user_id,
            func.lower(Portfolio.name) == name.strip().lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(Portfolio.id != exclude_id)
        result = await session.execute(stmt)
        count = result.scalar_one() or 0
        return count > 0

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: UUID,
        name: str,
        description: str | None = None,
    ) -> Portfolio:
        """Create and persist a new portfolio."""
        portfolio = Portfolio(
            user_id=user_id,
            name=name.strip(),
            description=description.strip() if description else None,
        )
        portfolio.targets = []
        session.add(portfolio)
        await session.flush()
        return portfolio

    @staticmethod
    async def update(
        session: AsyncSession,
        portfolio: Portfolio,
        name: str | None = None,
        description: str | None = None,
    ) -> Portfolio:
        """Update portfolio metadata."""
        if name is not None:
            portfolio.name = name.strip()
        if description is not None:
            portfolio.description = description.strip() if description.strip() else None
        await session.flush()
        return portfolio

    @staticmethod
    async def delete(session: AsyncSession, portfolio: Portfolio) -> None:
        """Delete portfolio (cascades to targets and transactions)."""
        await session.delete(portfolio)
        await session.flush()

    @staticmethod
    async def get_targets(session: AsyncSession, portfolio_id: UUID) -> list[PortfolioTarget]:
        """Fetch all target allocations for a portfolio."""
        stmt = (
            select(PortfolioTarget)
            .where(PortfolioTarget.portfolio_id == portfolio_id)
            .order_by(PortfolioTarget.asset_class.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def replace_targets(
        session: AsyncSession,
        portfolio_id: UUID,
        targets: list[tuple[str, Decimal]],
    ) -> list[PortfolioTarget]:
        """Atomically replace target allocations for a portfolio."""
        # Delete existing targets
        await session.execute(
            delete(PortfolioTarget).where(PortfolioTarget.portfolio_id == portfolio_id)
        )

        # Insert new targets
        new_targets: list[PortfolioTarget] = []
        for asset_class, pct in targets:
            target = PortfolioTarget(
                portfolio_id=portfolio_id,
                asset_class=asset_class,
                target_pct=pct,
            )
            session.add(target)
            new_targets.append(target)

        await session.flush()
        return new_targets
