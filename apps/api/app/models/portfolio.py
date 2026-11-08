"""Portfolio and Target Allocation domain models."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.transaction import Transaction
    from app.models.user import User


class Portfolio(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-created investment portfolio."""

    __tablename__ = "portfolios"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="portfolios")
    targets: Mapped[list["PortfolioTarget"]] = relationship(
        "PortfolioTarget",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PortfolioTarget.asset_class",
        lazy="selectin",
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "uq_portfolios_user_name_lower",
            "user_id",
            text("lower(name)"),
            unique=True,
        ),
    )


class PortfolioTarget(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Asset class allocation target for a portfolio."""

    __tablename__ = "portfolio_targets"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    target_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="targets")

    __table_args__ = (
        CheckConstraint(
            "target_pct > 0 AND target_pct <= 100",
            name="chk_target_pct_range",
        ),
        CheckConstraint(
            "asset_class IN ('equity', 'debt', 'hybrid', 'gold', 'other')",
            name="chk_target_asset_class",
        ),
        UniqueConstraint(
            "portfolio_id",
            "asset_class",
            name="uq_portfolio_targets_portfolio_asset_class",
        ),
    )
