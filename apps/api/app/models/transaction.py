"""Transaction ledger model."""

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.fund import Fund
    from app.models.portfolio import Portfolio


class Transaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable transaction entry in a portfolio's ledger."""

    __tablename__ = "transactions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fund_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    txn_type: Mapped[str] = mapped_column(String(16), nullable=False)
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sip_installment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sip_installments.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="transactions")
    fund: Mapped["Fund"] = relationship("Fund", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "txn_type IN ('buy', 'sell', 'dividend_reinvest')",
            name="chk_transaction_type",
        ),
        CheckConstraint("units > 0", name="chk_transaction_units_positive"),
        CheckConstraint("nav > 0", name="chk_transaction_nav_positive"),
        CheckConstraint("amount > 0", name="chk_transaction_amount_positive"),
        Index(
            "ix_transactions_portfolio_fund_date_created",
            "portfolio_id",
            "fund_id",
            "txn_date",
            "created_at",
            "id",
        ),
    )
