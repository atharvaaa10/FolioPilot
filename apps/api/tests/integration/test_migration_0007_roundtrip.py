"""Test migration 0007 roundtrip with data and constraint validation."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_migration_0007_roundtrip() -> None:
    """Verify downgrade to 0006 drops import tables and import_id column,
    and upgrade restores tables, columns, indexes, and constraints.
    """
    settings = get_settings()
    test_db_url = settings.TEST_DATABASE_URL
    root_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = root_dir / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    alembic_cfg.set_main_option("script_location", str(root_dir / "alembic"))

    async def run_query(sql: str, params: dict[str, Any] | None = None) -> list[Any] | None:
        eng = create_async_engine(test_db_url, poolclass=NullPool)
        try:
            async with eng.connect() as conn:
                res = await conn.execute(text(sql), params or {})
                await conn.commit()
                try:
                    return list(res.fetchall())
                except Exception:
                    return None
        finally:
            await eng.dispose()

    # 1. Ensure DB is on head (0007)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    # 2. Insert prerequisites (user, portfolio, fund)
    from uuid import uuid4

    user_id = str(uuid4())
    port_id = str(uuid4())
    fund_id = str(uuid4())
    import_id = str(uuid4())
    row_id = str(uuid4())
    txn_id = str(uuid4())
    scheme_code = 999103

    await run_query(
        "INSERT INTO users (id, email, password_hash, is_active, created_at, updated_at) "
        f"VALUES ('{user_id}', '{user_id}@example.com', 'dummy_hash', true, now(), now()) "
        "ON CONFLICT (id) DO NOTHING"
    )
    await run_query(
        "INSERT INTO portfolios (id, user_id, name, created_at, updated_at) "
        f"VALUES ('{port_id}', '{user_id}', 'Import Migr Port', now(), now()) "
        "ON CONFLICT (id) DO NOTHING"
    )
    fund_cols = (
        "id, scheme_code, isin_growth, name, name_normalized, amc, category_raw, "
        "asset_class, classification_source, plan_type, option_type, is_active, "
        "is_tracked, first_seen_at, last_seen_at, created_at, updated_at"
    )
    fund_vals = (
        f"'{fund_id}', {scheme_code}, 'INF{scheme_code}', 'Import Migr Fund', "
        "'import migr fund', 'Migr AMC', 'Flexi Cap', 'equity', 'category', 'direct', "
        "'growth', true, false, now(), now(), now(), now()"
    )
    await run_query(
        f"INSERT INTO funds ({fund_cols}) VALUES ({fund_vals}) ON CONFLICT (scheme_code) DO NOTHING"
    )

    # 3. Insert transaction_import, transaction_import_row, and linked transaction
    await run_query(
        "INSERT INTO transaction_imports "
        "(id, portfolio_id, status, filename, file_sha256, file_size, rows_total, rows_ok, "
        "rows_warning, rows_duplicate, rows_error, will_import, plan_fingerprint, "
        "expires_at, created_at, updated_at) "
        f"VALUES ('{import_id}', '{port_id}', 'previewed', 'test.xlsx', 'dummy_sha', 1024, "
        "1, 1, 0, 0, 0, 1, 'dummy_fp', now() + interval '24 hours', now(), now())"
    )
    await run_query(
        "INSERT INTO transaction_import_rows "
        "(id, import_id, row_number, status, fund_id, txn_type, "
        "txn_date, units, nav, amount, notes, raw, messages) "
        f"VALUES ('{row_id}', '{import_id}', 2, 'ok', '{fund_id}', 'buy', '2025-01-15', "
        "100.0000, 50.00000000, 5000.00, 'Test import note', '{}', '[]')"
    )
    await run_query(
        "INSERT INTO transactions "
        "(id, portfolio_id, fund_id, txn_type, txn_date, units, nav, amount, "
        "import_id, created_at, updated_at) "
        f"VALUES ('{txn_id}', '{port_id}', '{fund_id}', 'buy', '2025-01-15', "
        f"100.0000, 50.00000000, 5000.00, '{import_id}', now(), now())"
    )

    # 4. Assert constraints exist under 0007
    constraints_0007 = await run_query(
        "SELECT conname FROM pg_constraint WHERE conname IN ("
        "'ck_transaction_imports_chk_transaction_import_status', "
        "'ck_transaction_import_rows_chk_transaction_import_row_status', "
        "'uq_transaction_import_rows_import_row', "
        "'fk_transactions_import_id'"
        ")"
    )
    assert constraints_0007 is not None
    found_connames = {r[0] for r in constraints_0007}
    assert "ck_transaction_imports_chk_transaction_import_status" in found_connames
    assert "ck_transaction_import_rows_chk_transaction_import_row_status" in found_connames
    assert "uq_transaction_import_rows_import_row" in found_connames
    assert "fk_transactions_import_id" in found_connames

    # Assert partial unique index exists
    idx_sql = (
        "SELECT indexname FROM pg_indexes "
        "WHERE indexname = 'ix_transaction_imports_portfolio_previewed'"
    )
    indexes_0007 = await run_query(idx_sql)
    assert indexes_0007 is not None and len(indexes_0007) == 1

    # 5. Downgrade to 0006
    await asyncio.to_thread(command.downgrade, alembic_cfg, "0006")

    # 6. Verify tables and columns dropped under 0006
    tables_sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' "
        "AND table_name IN ('transaction_imports', 'transaction_import_rows')"
    )
    tables_0006 = await run_query(tables_sql)
    assert tables_0006 is not None and len(tables_0006) == 0

    col_0006 = await run_query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'transactions' AND column_name = 'import_id'"
    )
    assert col_0006 is not None and len(col_0006) == 0

    # 7. Upgrade back to 0007 (head)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    # 8. Verify tables and columns restored under 0007
    tables_head = await run_query(tables_sql)
    assert tables_head is not None and len(tables_head) == 2

    col_head = await run_query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'transactions' AND column_name = 'import_id'"
    )
    assert col_head is not None and len(col_head) == 1
