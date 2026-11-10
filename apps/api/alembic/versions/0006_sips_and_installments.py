"""sips and installments

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create sips table
    op.create_table(
        "sips",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fund_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("funds.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("day_of_month", sa.SmallInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("step_up_percent", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint("amount > 0", name="chk_sip_amount_positive"),
        sa.CheckConstraint(
            "day_of_month >= 1 AND day_of_month <= 28", name="chk_sip_day_of_month_range"
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="chk_sip_dates_order"
        ),
        sa.CheckConstraint(
            "step_up_percent >= 0 AND step_up_percent <= 100", name="chk_sip_step_up_range"
        ),
    )
    op.create_index("ix_sips_portfolio_id", "sips", ["portfolio_id"])
    op.create_index("ix_sips_fund_id", "sips", ["fund_id"])

    # 2. Create sip_pauses table
    op.create_table(
        "sip_pauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("paused_from", sa.Date(), nullable=False),
        sa.Column("resumed_on", sa.Date(), nullable=True),
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
            "resumed_on IS NULL OR resumed_on > paused_from", name="chk_sip_pause_dates"
        ),
    )
    op.create_index("ix_sip_pauses_sip_id", "sip_pauses", ["sip_id"])
    op.create_index(
        "uq_sip_pauses_open_pause",
        "sip_pauses",
        ["sip_id"],
        unique=True,
        postgresql_where=sa.text("resumed_on IS NULL"),
    )

    # 3. Create sip_installments table
    op.create_table(
        "sip_installments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("planned_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("nav_date", sa.Date(), nullable=True),
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
            "planned_amount > 0", name="chk_sip_installment_planned_amount_positive"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'executed', 'skipped')",
            name="chk_sip_installment_status",
        ),
        sa.UniqueConstraint("sip_id", "due_date", name="uq_sip_installments_sip_due_date"),
    )
    op.create_index("ix_sip_installments_sip_id", "sip_installments", ["sip_id"])
    op.create_index(
        "ix_sip_installments_status_due_date", "sip_installments", ["status", "due_date"]
    )

    # 4. Add sip_installment_id to transactions table
    op.add_column(
        "transactions",
        sa.Column("sip_installment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_transactions_sip_installment_id",
        "transactions",
        ["sip_installment_id"],
    )
    op.create_foreign_key(
        "fk_transactions_sip_installment_id",
        "transactions",
        "sip_installments",
        ["sip_installment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 1. Remove column and constraints from transactions
    op.drop_constraint("fk_transactions_sip_installment_id", "transactions", type_="foreignkey")
    op.drop_constraint("uq_transactions_sip_installment_id", "transactions", type_="unique")
    op.drop_column("transactions", "sip_installment_id")

    # 2. Drop sip_installments table
    op.drop_index("ix_sip_installments_status_due_date", table_name="sip_installments")
    op.drop_index("ix_sip_installments_sip_id", table_name="sip_installments")
    op.drop_table("sip_installments")

    # 3. Drop sip_pauses table
    op.drop_index("uq_sip_pauses_open_pause", table_name="sip_pauses")
    op.drop_index("ix_sip_pauses_sip_id", table_name="sip_pauses")
    op.drop_table("sip_pauses")

    # 4. Drop sips table
    op.drop_index("ix_sips_fund_id", table_name="sips")
    op.drop_index("ix_sips_portfolio_id", table_name="sips")
    op.drop_table("sips")
