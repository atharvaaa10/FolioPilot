"""SQLAlchemy models for Excel transaction imports and import preview rows."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.fund import Fund
    from app.models.portfolio import Portfolio
    from app.models.transaction import Transaction


class TransactionImport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Excel transaction import batch record."""

    __tablename__ = "transaction_imports"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)

    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_warning: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    will_import: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    extra_columns: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    committed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    undone_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
    rows: Mapped[list["TransactionImportRow"]] = relationship(
        "TransactionImportRow",
        back_populates="import_batch",
        cascade="all, delete-orphan",
        order_by="TransactionImportRow.row_number",
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="import_batch",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('previewed', 'committed', 'undone')",
            name="chk_transaction_import_status",
        ),
        Index(
            "ix_transaction_imports_portfolio_previewed",
            "portfolio_id",
            unique=True,
            postgresql_where=(mapped_column("status") == "previewed"),
        ),
    )


class TransactionImportRow(Base, UUIDPrimaryKeyMixin):
    """Normalized prospective row of an Excel transaction import preview."""

    __tablename__ = "transaction_import_rows"

    import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transaction_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    fund_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("funds.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    txn_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    txn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    units: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fund_name_in_file: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # Relationships
    import_batch: Mapped["TransactionImport"] = relationship(
        "TransactionImport", back_populates="rows"
    )
    fund: Mapped["Fund | None"] = relationship("Fund", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "status IN ('ok', 'warning', 'duplicate', 'error')",
            name="chk_transaction_import_row_status",
        ),
        Index(
            "uq_transaction_import_rows_import_row",
            "import_id",
            "row_number",
            unique=True,
        ),
        Index(
            "ix_transaction_import_rows_import_status_row",
            "import_id",
            "status",
            "row_number",
        ),
    )
