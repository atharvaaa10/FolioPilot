"""Initial database extensions (vector and pgcrypto)

Revision ID: 0001_initial_extensions
Revises: None
Create Date: 2026-11-04 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_extensions"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pgvector for factsheet embeddings / RAG
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # Enable pgcrypto for cryptographic functions and gen_random_uuid
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto;")
    op.execute("DROP EXTENSION IF EXISTS vector;")
