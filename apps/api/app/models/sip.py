"""SIP (Systematic Investment Plan) and installment database models."""

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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.fund import Fund
    from app.models.portfolio import Portfolio
    from app.models.transaction import Transaction


class Sip(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Recurring investment rule belonging to a portfolio."""

    __tablename__ = "sips"

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
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    day_of_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    step_up_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
    fund: Mapped["Fund"] = relationship("Fund", lazy="selectin")
    pauses: Mapped[list["SipPause"]] = relationship(
        "SipPause",
        back_populates="sip",
        cascade="all, delete-orphan",
        order_by="SipPause.paused_from",
        lazy="selectin",
    )
    installments: Mapped[list["SipInstallment"]] = relationship(
        "SipInstallment",
        back_populates="sip",
        cascade="all, delete-orphan",
        order_by="SipInstallment.due_date.desc()",
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_sip_amount_positive"),
        CheckConstraint(
            "day_of_month >= 1 AND day_of_month <= 28", name="chk_sip_day_of_month_range"
        ),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="chk_sip_dates_order"),
        CheckConstraint(
            "step_up_percent >= 0 AND step_up_percent <= 100", name="chk_sip_step_up_range"
        ),
    )


class SipPause(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Pause interval for a SIP."""

    __tablename__ = "sip_pauses"

    sip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paused_from: Mapped[date] = mapped_column(Date, nullable=False)
    resumed_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationship
    sip: Mapped["Sip"] = relationship("Sip", back_populates="pauses")

    __table_args__ = (
        CheckConstraint(
            "resumed_on IS NULL OR resumed_on > paused_from", name="chk_sip_pause_dates"
        ),
        Index(
            "uq_sip_pauses_open_pause",
            "sip_id",
            unique=True,
            postgresql_where=text("resumed_on IS NULL"),
        ),
    )


class SipInstallment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Individual scheduled or executed installment of a SIP."""

    __tablename__ = "sip_installments"

    sip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    nav_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationships
    sip: Mapped["Sip"] = relationship("Sip", back_populates="installments")
    transaction: Mapped["Transaction | None"] = relationship(
        "Transaction",
        primaryjoin="SipInstallment.id == foreign(Transaction.sip_installment_id)",
        uselist=False,
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("planned_amount > 0", name="chk_sip_installment_planned_amount_positive"),
        CheckConstraint(
            "status IN ('pending', 'executed', 'skipped')",
            name="chk_sip_installment_status",
        ),
        UniqueConstraint("sip_id", "due_date", name="uq_sip_installments_sip_due_date"),
        Index("ix_sip_installments_status_due_date", "status", "due_date"),
    )
