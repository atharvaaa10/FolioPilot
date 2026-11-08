"""Transaction ledger application service."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    LEDGER_DATE_FLOOR,
    MAX_TRANSACTIONS_PER_PORTFOLIO,
)
from app.core.errors import (
    FundNotFoundError,
    PortfolioNotFoundError,
    TransactionLimitReachedError,
    TransactionNotFoundError,
    ValidationError,
)
from app.models.transaction import Transaction
from app.repositories.funds import FundRepository
from app.repositories.portfolios import PortfolioRepository
from app.repositories.transactions import TransactionRepository
from app.services.ledger import DerivedPosition, compute_positions, validate_ledger
from app.services.nav_backfill import ensure_tracked
from app.services.transaction_math import resolve_transaction_amounts

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class PositionWithFund:
    """Enriched derived position containing Fund master metadata."""

    position: DerivedPosition
    scheme_code: int
    name: str
    asset_class: str
    sub_category: str | None
    latest_nav: Decimal | None
    latest_nav_date: date | None


class TransactionService:
    """Service orchestrating ledger mutations under pessimistic portfolio row locks."""

    @staticmethod
    async def add_transaction(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        fund_id: UUID,
        txn_type: str,
        txn_date: date,
        units: Decimal | None = None,
        nav: Decimal | None = None,
        amount: Decimal | None = None,
        notes: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> Transaction:
        """Add transaction to portfolio ledger with concurrency lock and validation."""
        # 1. Acquire pessimistic lock on portfolio row and verify ownership (404 rule)
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # 2. Check portfolio transaction limit
        txn_count = await TransactionRepository.count_by_portfolio(session, portfolio_id)
        if txn_count >= MAX_TRANSACTIONS_PER_PORTFOLIO:
            raise TransactionLimitReachedError(
                f"Cannot add more than {MAX_TRANSACTIONS_PER_PORTFOLIO} transactions to a portfolio"
            )

        # 3. Verify fund exists
        fund = await FundRepository.get_by_id(session, fund_id)
        if fund is None:
            raise FundNotFoundError("Fund not found")

        # 4. Validate transaction type
        normalized_type = txn_type.strip().upper()
        if normalized_type not in ("BUY", "SELL"):
            raise ValidationError("Transaction type must be 'BUY' or 'SELL'")

        # 5. Validate date bounds
        if txn_date < LEDGER_DATE_FLOOR:
            raise ValidationError(
                f"Transaction date cannot be earlier than {LEDGER_DATE_FLOOR.isoformat()}"
            )

        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()
        if txn_date > today_kolkata:
            raise ValidationError("Transaction date cannot be in the future")

        # 6. Resolve math, scale, and tolerance for units/nav/amount
        res_units, res_nav, res_amount = resolve_transaction_amounts(
            units=units, nav=nav, amount=amount
        )

        # 7. Check full ledger consistency with prospective transaction
        existing_txns = await TransactionRepository.list_by_portfolio(
            session, portfolio_id, load_fund=False
        )

        # Candidate object simulating candidate transaction in the ledger
        candidate = Transaction(
            portfolio_id=portfolio_id,
            fund_id=fund_id,
            txn_type=normalized_type,
            txn_date=txn_date,
            units=res_units,
            nav=res_nav,
            amount=res_amount,
            notes=notes.strip() if notes else None,
            created_at=now_utc,
        )
        validate_ledger(existing_txns + [candidate])

        # 8. Persist transaction
        txn = await TransactionRepository.create(
            session,
            portfolio_id=portfolio_id,
            fund_id=fund_id,
            txn_type=normalized_type,
            txn_date=txn_date,
            units=res_units,
            nav=res_nav,
            amount=res_amount,
            notes=notes,
        )

        # 9. Ensure fund is flagged tracked and backfill enqueued
        await ensure_tracked(session, fund, enqueue_task=True)

        return txn

    @staticmethod
    async def delete_transaction(
        session: AsyncSession,
        portfolio_id: UUID,
        transaction_id: UUID,
        user_id: UUID,
    ) -> None:
        """Delete transaction from ledger with concurrency lock and historical consistency check."""
        # 1. Acquire pessimistic lock on portfolio row and verify ownership
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # 2. Verify transaction exists within this portfolio
        txn = await TransactionRepository.get_by_id(
            session, transaction_id, portfolio_id=portfolio_id
        )
        if txn is None:
            raise TransactionNotFoundError("Transaction not found")

        # 3. Verify ledger consistency if this transaction is removed
        all_txns = await TransactionRepository.list_by_portfolio(
            session, portfolio_id, load_fund=False
        )
        remaining_txns = [t for t in all_txns if t.id != transaction_id]
        validate_ledger(remaining_txns)

        # 4. Delete transaction
        await TransactionRepository.delete(session, txn)

    @staticmethod
    async def list_transactions(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        fund_id: UUID | None = None,
    ) -> list[Transaction]:
        """List transactions for a portfolio in deterministic ledger order."""
        # Ownership check
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        return await TransactionRepository.list_by_portfolio(
            session, portfolio_id, fund_id=fund_id, load_fund=True
        )

    @staticmethod
    async def get_portfolio_positions(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
    ) -> list[PositionWithFund]:
        """Compute average-cost derived positions for portfolio and enrich with fund details."""
        # Ownership check
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        txns = await TransactionRepository.list_by_portfolio(session, portfolio_id, load_fund=True)
        derived_map = compute_positions(txns)

        # Collect unique funds from transactions
        funds_by_id = {t.fund_id: t.fund for t in txns if t.fund is not None}

        result: list[PositionWithFund] = []
        for fund_id, pos in derived_map.items():
            fund = funds_by_id.get(fund_id)
            if fund is not None:
                result.append(
                    PositionWithFund(
                        position=pos,
                        scheme_code=fund.scheme_code,
                        name=fund.name,
                        asset_class=fund.asset_class,
                        sub_category=fund.sub_category,
                        latest_nav=fund.latest_nav,
                        latest_nav_date=fund.latest_nav_date,
                    )
                )

        # Sort positions by name ascending
        result.sort(key=lambda p: p.name)
        return result
