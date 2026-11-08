"""Portfolio application service."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PORTFOLIOS_PER_USER
from app.core.errors import (
    PortfolioLimitReachedError,
    PortfolioNameTakenError,
    PortfolioNotFoundError,
)
from app.models.portfolio import Portfolio, PortfolioTarget
from app.repositories.portfolios import PortfolioRepository
from app.services.target_allocation import validate_targets


class PortfolioService:
    """Service orchestrating portfolio lifecycle and target allocations."""

    @staticmethod
    async def create_portfolio(
        session: AsyncSession,
        user_id: UUID,
        name: str,
        description: str | None = None,
    ) -> Portfolio:
        """Create a new portfolio with limit and name uniqueness enforcement."""
        count = await PortfolioRepository.count_by_user(session, user_id)
        if count >= MAX_PORTFOLIOS_PER_USER:
            raise PortfolioLimitReachedError(
                f"Cannot create more than {MAX_PORTFOLIOS_PER_USER} portfolios"
            )

        if await PortfolioRepository.exists_name_for_user(session, user_id, name):
            raise PortfolioNameTakenError(f"You already have a portfolio named '{name.strip()}'")

        return await PortfolioRepository.create(
            session,
            user_id=user_id,
            name=name,
            description=description,
        )

    @staticmethod
    async def get_portfolio(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        load_targets: bool = True,
    ) -> Portfolio:
        """Fetch portfolio by ID with strict ownership validation (404 if not found)."""
        portfolio = await PortfolioRepository.get_by_id(
            session, portfolio_id, user_id=user_id, load_targets=load_targets
        )
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")
        return portfolio

    @staticmethod
    async def list_portfolios(
        session: AsyncSession,
        user_id: UUID,
    ) -> list[Portfolio]:
        """List all portfolios belonging to user with targets eagerly loaded."""
        return await PortfolioRepository.list_by_user(session, user_id, load_targets=True)

    @staticmethod
    async def update_portfolio(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Portfolio:
        """Update portfolio metadata with ownership and uniqueness checks."""
        portfolio = await PortfolioService.get_portfolio(
            session, portfolio_id, user_id=user_id, load_targets=False
        )

        if name is not None and name.strip():
            if await PortfolioRepository.exists_name_for_user(
                session, user_id, name, exclude_id=portfolio.id
            ):
                raise PortfolioNameTakenError(
                    f"You already have a portfolio named '{name.strip()}'"
                )

        return await PortfolioRepository.update(
            session, portfolio, name=name, description=description
        )

    @staticmethod
    async def delete_portfolio(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
    ) -> None:
        """Delete portfolio with ownership validation."""
        portfolio = await PortfolioService.get_portfolio(
            session, portfolio_id, user_id=user_id, load_targets=False
        )
        await PortfolioRepository.delete(session, portfolio)

    @staticmethod
    async def set_targets(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        targets: list[tuple[str, Decimal]],
    ) -> list[PortfolioTarget]:
        """Validate and atomically replace target allocations for portfolio."""
        # Validate ownership (raises PortfolioNotFoundError if unowned)
        await PortfolioService.get_portfolio(
            session, portfolio_id, user_id=user_id, load_targets=False
        )

        # Validate pure allocation rules
        validate_targets(targets)

        return await PortfolioRepository.replace_targets(session, portfolio_id, targets)
