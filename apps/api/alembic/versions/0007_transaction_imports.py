"""transaction imports and preview rows

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create transaction_imports table
    op.create_table(
        "transaction_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_warning", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_error", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("will_import", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("extra_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("committed_count", sa.Integer(), nullable=True),
        sa.Column("undone_count", sa.Integer(), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('previewed', 'committed', 'undone')",
            name="chk_transaction_import_status",
        ),
    )
    op.create_index(
        "ix_transaction_imports_portfolio_id",
        "transaction_imports",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_transaction_imports_portfolio_previewed",
        "transaction_imports",
        ["portfolio_id"],
        unique=True,
        postgresql_where=sa.text("status = 'previewed'"),
    )

    # 2. Create transaction_import_rows table
    op.create_table(
        "transaction_import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "import_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transaction_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "fund_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("funds.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("txn_type", sa.String(16), nullable=True),
        sa.Column("txn_date", sa.Date(), nullable=True),
        sa.Column("units", sa.Numeric(18, 4), nullable=True),
        sa.Column("nav", sa.Numeric(20, 8), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("fund_name_in_file", sa.Text(), nullable=True),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'warning', 'duplicate', 'error')",
            name="chk_transaction_import_row_status",
        ),
        sa.UniqueConstraint(
            "import_id",
            "row_number",
            name="uq_transaction_import_rows_import_row",
        ),
    )
    op.create_index(
        "ix_transaction_import_rows_import_id",
        "transaction_import_rows",
        ["import_id"],
    )
    op.create_index(
        "ix_transaction_import_rows_import_status_row",
        "transaction_import_rows",
        ["import_id", "status", "row_number"],
    )

    # 3. Add import_id to transactions table
    op.add_column(
        "transactions",
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_import_id",
        "transactions",
        "transaction_imports",
        ["import_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_import_id", "transactions", ["import_id"])


def downgrade() -> None:
    # 1. Drop foreign key, index, and column from transactions
    op.drop_index("ix_transactions_import_id", table_name="transactions")
    op.drop_constraint("fk_transactions_import_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "import_id")

    # 2. Drop transaction_import_rows table
    op.drop_index(
        "ix_transaction_import_rows_import_status_row",
        table_name="transaction_import_rows",
    )
    op.drop_index("ix_transaction_import_rows_import_id", table_name="transaction_import_rows")
    op.drop_table("transaction_import_rows")

    # 3. Drop transaction_imports table
    op.drop_index(
        "ix_transaction_imports_portfolio_previewed",
        table_name="transaction_imports",
    )
    op.drop_index("ix_transaction_imports_portfolio_id", table_name="transaction_imports")
    op.drop_table("transaction_imports")
