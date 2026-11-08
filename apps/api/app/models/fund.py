"""Fund domain model for Indian Mutual Funds."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.nav_history import NavHistory


class Fund(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Mutual Fund master entity."""

    __tablename__ = "funds"

    scheme_code: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    isin_growth: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    isin_reinvest: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    amc: Mapped[str] = mapped_column(String(255), nullable=False)
    scheme_type_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    classification_source: Mapped[str] = mapped_column(String(50), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    option_type: Mapped[str] = mapped_column(String(20), nullable=False)
    latest_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    latest_nav_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), index=True, nullable=False
    )
    is_tracked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    nav_history: Mapped[list["NavHistory"]] = relationship(
        "NavHistory",
        back_populates="fund",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "ix_funds_name_normalized_trgm",
            "name_normalized",
            postgresql_using="gin",
            postgresql_ops={"name_normalized": "gin_trgm_ops"},
        ),
    )
