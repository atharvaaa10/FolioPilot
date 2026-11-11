"""Repository for Transaction ledger records."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.transaction import Transaction


class TransactionRepository:
    """Repository handling Transaction ledger queries and mutations."""

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        transaction_id: UUID,
        portfolio_id: UUID | None = None,
        load_fund: bool = False,
    ) -> Transaction | None:
        """Fetch transaction by ID, optionally validating portfolio ownership."""
        stmt = select(Transaction).where(Transaction.id == transaction_id)
        if portfolio_id is not None:
            stmt = stmt.where(Transaction.portfolio_id == portfolio_id)
        if load_fund:
            stmt = stmt.options(joinedload(Transaction.fund))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_portfolio(
        session: AsyncSession,
        portfolio_id: UUID,
        fund_id: UUID | None = None,
        load_fund: bool = True,
    ) -> list[Transaction]:
        """Fetch all transactions in deterministic ledger order:

        (txn_date ASC, BUY before SELL, created_at ASC, id ASC).
        """
        type_rank = case(
            (Transaction.txn_type.in_(("BUY", "buy", "dividend_reinvest")), 0),
            else_=1,
        )
        stmt = (
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(
                Transaction.txn_date.asc(),
                type_rank.asc(),
                Transaction.created_at.asc(),
                Transaction.id.asc(),
            )
        )
        if fund_id is not None:
            stmt = stmt.where(Transaction.fund_id == fund_id)
        if load_fund:
            stmt = stmt.options(joinedload(Transaction.fund))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_portfolio(session: AsyncSession, portfolio_id: UUID) -> int:
        """Count total transactions in a portfolio."""
        stmt = select(func.count(Transaction.id)).where(Transaction.portfolio_id == portfolio_id)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def get_by_installment_id(
        session: AsyncSession,
        installment_id: UUID,
        load_fund: bool = False,
    ) -> Transaction | None:
        """Fetch transaction linked to a specific SIP installment."""
        stmt = select(Transaction).where(Transaction.sip_installment_id == installment_id)
        if load_fund:
            stmt = stmt.options(joinedload(Transaction.fund))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        portfolio_id: UUID,
        fund_id: UUID,
        txn_type: str,
        txn_date: date,
        units: Decimal,
        nav: Decimal,
        amount: Decimal,
        notes: str | None = None,
        sip_installment_id: UUID | None = None,
        import_id: UUID | None = None,
    ) -> Transaction:
        """Append a transaction to the portfolio ledger."""
        txn = Transaction(
            portfolio_id=portfolio_id,
            fund_id=fund_id,
            txn_type=txn_type.lower(),
            txn_date=txn_date,
            units=units,
            nav=nav,
            amount=amount,
            notes=notes.strip() if notes else None,
            sip_installment_id=sip_installment_id,
            import_id=import_id,
        )
        session.add(txn)
        await session.flush()
        return txn

    @staticmethod
    async def create_batch(
        session: AsyncSession,
        transactions: list[Transaction],
    ) -> list[Transaction]:
        """Bulk append transactions to the portfolio ledger."""
        session.add_all(transactions)
        await session.flush()
        return transactions

    @staticmethod
    async def delete(session: AsyncSession, transaction: Transaction) -> None:
        """Delete a transaction from the ledger."""
        await session.delete(transaction)
        await session.flush()
