"""NAV historical time-series model for tracked mutual funds."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.fund import Fund


class NavHistory(Base, UUIDPrimaryKeyMixin):
    """Historical NAV point for a tracked fund."""

    __tablename__ = "nav_history"

    fund_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nav_date: Mapped[date] = mapped_column(Date, nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    fund: Mapped["Fund"] = relationship("Fund", back_populates="nav_history")

    __table_args__ = (
        UniqueConstraint("fund_id", "nav_date", name="uq_nav_history_fund_date"),
        Index("ix_nav_history_fund_date_desc", "fund_id", text("nav_date DESC")),
    )
