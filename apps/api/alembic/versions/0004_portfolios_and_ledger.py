"""portfolios and ledger

Revision ID: 0004_portfolios_and_ledger
Revises: 0003_funds_and_nav_sync
Create Date: 2026-11-08 12:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_portfolios_and_ledger"
down_revision: str | None = "0003_funds_and_nav_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create portfolios table
    op.create_table(
        "portfolios",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_portfolios_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolios")),
    )
    op.create_index(op.f("ix_portfolios_user_id"), "portfolios", ["user_id"], unique=False)
    op.create_index(
        "uq_portfolios_user_name_lower",
        "portfolios",
        ["user_id", sa.literal_column("lower(name)")],
        unique=True,
    )

    # 2. Create portfolio_targets table
    op.create_table(
        "portfolio_targets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("target_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "asset_class IN ('equity', 'debt', 'hybrid', 'gold', 'other')",
            name=op.f("ck_portfolio_targets_chk_target_asset_class"),
        ),
        sa.CheckConstraint(
            "target_pct > 0 AND target_pct <= 100",
            name=op.f("ck_portfolio_targets_chk_target_pct_range"),
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_portfolio_targets_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_targets")),
        sa.UniqueConstraint(
            "portfolio_id", "asset_class", name="uq_portfolio_targets_portfolio_asset_class"
        ),
    )
    op.create_index(
        op.f("ix_portfolio_targets_portfolio_id"),
        "portfolio_targets",
        ["portfolio_id"],
        unique=False,
    )

    # 3. Create transactions table (the append-only ledger)
    op.create_table(
        "transactions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("fund_id", sa.UUID(), nullable=False),
        sa.Column("txn_type", sa.String(length=16), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("units", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("nav", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "txn_type IN ('BUY', 'SELL')", name=op.f("ck_transactions_chk_transaction_type")
        ),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_transactions_chk_transaction_amount_positive")
        ),
        sa.CheckConstraint("nav > 0", name=op.f("ck_transactions_chk_transaction_nav_positive")),
        sa.CheckConstraint(
            "units > 0", name=op.f("ck_transactions_chk_transaction_units_positive")
        ),
        sa.ForeignKeyConstraint(
            ["fund_id"],
            ["funds.id"],
            name=op.f("fk_transactions_fund_id_funds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_transactions_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
    )
    op.create_index(op.f("ix_transactions_fund_id"), "transactions", ["fund_id"], unique=False)
    op.create_index(
        op.f("ix_transactions_portfolio_id"), "transactions", ["portfolio_id"], unique=False
    )
    op.create_index(
        "ix_transactions_portfolio_fund_date_created",
        "transactions",
        ["portfolio_id", "fund_id", "txn_date", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_portfolio_fund_date_created", table_name="transactions")
    op.drop_index(op.f("ix_transactions_portfolio_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_fund_id"), table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(op.f("ix_portfolio_targets_portfolio_id"), table_name="portfolio_targets")
    op.drop_table("portfolio_targets")
    op.drop_index("uq_portfolios_user_name_lower", table_name="portfolios")
    op.drop_index(op.f("ix_portfolios_user_id"), table_name="portfolios")
    op.drop_table("portfolios")
