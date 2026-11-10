"""constraints and lowercase txn type

Revision ID: 0005_constraints_and_lowercase_txn_type
Revises: 0004_portfolios_and_ledger
Create Date: 2026-11-08 17:05:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004_portfolios_and_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop existing constraint allowing only uppercase
    op.execute(
        "ALTER TABLE transactions DROP CONSTRAINT IF EXISTS ck_transactions_chk_transaction_type"
    )

    # 2. Update existing transactions to lowercase
    op.execute("UPDATE transactions SET txn_type = lower(txn_type)")

    # 3. Add new check constraint allowing ('buy', 'sell', 'dividend_reinvest')
    op.execute(
        "ALTER TABLE transactions ADD CONSTRAINT ck_transactions_chk_transaction_type "
        "CHECK (txn_type IN ('buy', 'sell', 'dividend_reinvest'))"
    )


def downgrade() -> None:
    # 1. Drop the lowercase constraint
    op.execute(
        "ALTER TABLE transactions DROP CONSTRAINT IF EXISTS ck_transactions_chk_transaction_type"
    )

    # 2. Convert existing rows back to uppercase
    op.execute(
        "UPDATE transactions SET txn_type = CASE "
        "WHEN lower(txn_type) = 'sell' THEN 'SELL' "
        "ELSE 'BUY' END"
    )

    # 3. Restore previous check constraint allowing only ('BUY', 'SELL')
    op.execute(
        "ALTER TABLE transactions ADD CONSTRAINT ck_transactions_chk_transaction_type "
        "CHECK (txn_type IN ('BUY', 'SELL'))"
    )
