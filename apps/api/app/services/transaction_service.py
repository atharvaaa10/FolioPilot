"""Transaction ledger application service."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
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
from app.schemas.transaction import (
    FundSummary,
    HoldingResponse,
    HoldingsListResponse,
    HoldingsTotals,
)
from app.services.ledger import (
    DerivedHolding,
    compute_holdings,
    validate_ledger,
)
from app.services.nav_backfill import ensure_tracked
from app.services.transaction_math import resolve_transaction_amounts

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class HoldingWithFund:
    """Enriched derived holding containing fund master metadata."""

    holding: DerivedHolding
    fund: Any


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

        # Candidate object simulating new transaction in the ledger
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
        validate_ledger(existing_txns + [candidate], mutation_type="add", target_txn_id=None)

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
    async def get_transaction(
        session: AsyncSession,
        portfolio_id: UUID,
        transaction_id: UUID,
        user_id: UUID,
    ) -> Transaction:
        """Fetch single transaction by ID, enforcing portfolio ownership."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        txn = await TransactionRepository.get_by_id(
            session, transaction_id, portfolio_id=portfolio_id, load_fund=True
        )
        if txn is None:
            raise TransactionNotFoundError("Transaction not found")

        return txn

    @staticmethod
    async def update_transaction(
        session: AsyncSession,
        portfolio_id: UUID,
        transaction_id: UUID,
        user_id: UUID,
        txn_date: date | None = None,
        units: Decimal | None = None,
        nav: Decimal | None = None,
        amount: Decimal | None = None,
        notes: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> Transaction:
        """Update existing transaction under pessimistic row lock with ledger re-validation."""
        # 1. Acquire pessimistic lock on portfolio row and verify ownership
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # 2. Verify transaction exists within this portfolio
        txn = await TransactionRepository.get_by_id(
            session, transaction_id, portfolio_id=portfolio_id, load_fund=True
        )
        if txn is None:
            raise TransactionNotFoundError("Transaction not found")

        # 3. Determine new values (type and fund are strictly immutable)
        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        new_date = txn_date if txn_date is not None else txn.txn_date
        if new_date < LEDGER_DATE_FLOOR:
            raise ValidationError(
                f"Transaction date cannot be earlier than {LEDGER_DATE_FLOOR.isoformat()}"
            )
        if new_date > today_kolkata:
            raise ValidationError("Transaction date cannot be in the future")

        has_math_change = (
            (units is not None and units != txn.units)
            or (nav is not None and nav != txn.nav)
            or (amount is not None and amount != txn.amount)
        )

        if has_math_change:
            input_units = units if units is not None else txn.units
            input_nav = nav if nav is not None else txn.nav
            # If amount wasn't explicitly supplied but units or nav changed,
            # derive amount rather than forcing old amount
            if amount is None and (units is not None or nav is not None):
                input_amount = None
            else:
                input_amount = amount if amount is not None else txn.amount

            res_units, res_nav, res_amount = resolve_transaction_amounts(
                units=input_units, nav=input_nav, amount=input_amount
            )
        else:
            res_units, res_nav, res_amount = txn.units, txn.nav, txn.amount

        # 4. Check ledger consistency across all transactions with the updated candidate
        all_txns = await TransactionRepository.list_by_portfolio(
            session, portfolio_id, load_fund=False
        )

        candidate = Transaction(
            portfolio_id=portfolio_id,
            fund_id=txn.fund_id,
            txn_type=txn.txn_type,
            txn_date=new_date,
            units=res_units,
            nav=res_nav,
            amount=res_amount,
            notes=notes.strip() if notes is not None else txn.notes,
            created_at=txn.created_at,
        )
        candidate.id = txn.id

        simulated_txns = [candidate if t.id == txn.id else t for t in all_txns]
        validate_ledger(simulated_txns, mutation_type="edit", target_txn_id=str(txn.id))

        # 5. Persist updates
        txn.txn_date = new_date
        txn.units = res_units
        txn.nav = res_nav
        txn.amount = res_amount
        if notes is not None:
            txn.notes = notes.strip() if notes else None

        await session.flush()
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
        validate_ledger(remaining_txns, mutation_type="delete", target_txn_id=str(transaction_id))

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
    async def get_holdings(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
    ) -> HoldingsListResponse:
        """Derive holdings from the ledger and enrich with fund metadata in a single query."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # Load transactions with joined fund relation (single SQL query)
        txns = await TransactionRepository.list_by_portfolio(session, portfolio_id, load_fund=True)
        holdings_map = compute_holdings(txns)

        # Collect unique funds from pre-loaded relation (no N+1 queries)
        funds_by_id = {t.fund_id: t.fund for t in txns if t.fund is not None}

        items: list[HoldingResponse] = []
        total_cost_basis = Decimal("0.00")
        open_positions = 0

        for fund_id, holding in holdings_map.items():
            fund = funds_by_id.get(fund_id)
            if fund is not None:
                if not holding.is_closed:
                    open_positions += 1
                    total_cost_basis += holding.cost_basis

                items.append(
                    HoldingResponse(
                        scheme_code=fund.scheme_code,
                        fund=FundSummary(
                            name=fund.name,
                            amc=fund.amc,
                            asset_class=fund.asset_class,
                            sub_category=fund.sub_category,
                            plan_type=fund.plan_type,
                            option_type=fund.option_type,
                            latest_nav=fund.latest_nav,
                            latest_nav_date=fund.latest_nav_date,
                        ),
                        units=holding.units,
                        avg_cost=holding.avg_cost,
                        cost_basis=holding.cost_basis,
                        total_bought=holding.total_bought,
                        total_sold=holding.total_sold,
                        first_txn_date=holding.first_txn_date,
                        last_txn_date=holding.last_txn_date,
                        txn_count=holding.txn_count,
                        is_closed=holding.is_closed,
                    )
                )

        # Sort items by fund name ascending
        items.sort(key=lambda h: h.fund.name)

        return HoldingsListResponse(
            items=items,
            totals=HoldingsTotals(
                cost_basis=total_cost_basis,
                open_positions=open_positions,
            ),
        )

    @staticmethod
    async def count_open_positions_sql(session: AsyncSession, portfolio_id: UUID) -> int:
        """Calculate open positions using a pure SQL aggregate for cross-verification."""
        signed_units = case(
            (Transaction.txn_type == "BUY", Transaction.units),
            else_=-Transaction.units,
        )
        subq = (
            select(Transaction.fund_id)
            .where(Transaction.portfolio_id == portfolio_id)
            .group_by(Transaction.fund_id)
            .having(func.sum(signed_units) > 0)
            .subquery()
        )
        stmt = select(func.count()).select_from(subq)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)
