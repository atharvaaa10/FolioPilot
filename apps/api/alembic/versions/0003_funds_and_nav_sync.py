"""Create pg_trgm extension, funds, nav_history, and nav_sync_runs tables.

Revision ID: 0003_funds_and_nav_sync
Revises: 0002_auth_tables
Create Date: 2026-11-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_funds_and_nav_sync"
down_revision: str | None = "0002_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable pg_trgm extension for GIN trigram indexing
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. Create funds table
    op.create_table(
        "funds",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("scheme_code", sa.Integer(), nullable=False),
        sa.Column("isin_growth", sa.String(length=12), nullable=True),
        sa.Column("isin_reinvest", sa.String(length=12), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_normalized", sa.String(length=255), nullable=False),
        sa.Column("amc", sa.String(length=255), nullable=False),
        sa.Column("scheme_type_raw", sa.String(length=100), nullable=True),
        sa.Column("category_raw", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=50), nullable=False),
        sa.Column("sub_category", sa.String(length=100), nullable=True),
        sa.Column("classification_source", sa.String(length=50), nullable=False),
        sa.Column("plan_type", sa.String(length=20), nullable=False),
        sa.Column("option_type", sa.String(length=20), nullable=False),
        sa.Column("latest_nav", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("latest_nav_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_tracked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme_code", name="uq_funds_scheme_code"),
    )
    op.create_index(op.f("ix_funds_scheme_code"), "funds", ["scheme_code"], unique=True)
    op.create_index(op.f("ix_funds_isin_growth"), "funds", ["isin_growth"], unique=False)
    op.create_index(op.f("ix_funds_isin_reinvest"), "funds", ["isin_reinvest"], unique=False)
    op.create_index(op.f("ix_funds_asset_class"), "funds", ["asset_class"], unique=False)
    op.create_index(op.f("ix_funds_is_active"), "funds", ["is_active"], unique=False)

    # GIN trigram index on name_normalized
    op.execute(
        "CREATE INDEX ix_funds_name_normalized_trgm "
        "ON funds USING gin (name_normalized gin_trgm_ops);"
    )

    # 3. Create nav_history table
    op.create_table(
        "nav_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nav_date", sa.Date(), nullable=False),
        sa.Column("nav", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fund_id", "nav_date", name="uq_nav_history_fund_date"),
    )
    op.create_index(op.f("ix_nav_history_fund_id"), "nav_history", ["fund_id"], unique=False)
    op.execute(
        "CREATE INDEX ix_nav_history_fund_date_desc ON nav_history (fund_id, nav_date DESC);"
    )

    # 4. Create nav_sync_runs table
    op.create_table(
        "nav_sync_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schemes_parsed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("funds_created", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("funds_updated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("nav_rows_written", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("nav_sync_runs")
    op.execute("DROP INDEX IF EXISTS ix_nav_history_fund_date_desc;")
    op.drop_table("nav_history")
    op.execute("DROP INDEX IF EXISTS ix_funds_name_normalized_trgm;")
    op.drop_table("funds")
