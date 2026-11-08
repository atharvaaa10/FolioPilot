"""Test migration 0005 roundtrip."""

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
async def test_migration_0005_roundtrip() -> None:
    """Verify downgrade converts txn_type to uppercase and restores constraint,

    and upgrade converts back to lowercase and restores new constraint.
    """
    settings = get_settings()
    test_db_url = settings.TEST_DATABASE_URL
    root_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = root_dir / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    alembic_cfg.set_main_option("script_location", str(root_dir / "alembic"))

    # Helper to execute SQL cleanly and close connection immediately
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

    # 1. Check initial state under 0005 and insert a lowercase 'buy' row
    rows = await run_query(
        "SELECT conname, pg_get_constraintdef(oid) "
        "FROM pg_constraint "
        "WHERE conname = 'ck_transactions_chk_transaction_type'"
    )
    assert rows is not None and len(rows) > 0
    assert "buy" in rows[0][1]

    user_insert = (
        "INSERT INTO users (id, email, password_hash, is_active, created_at, updated_at) "
        "VALUES ('11111111-1111-1111-1111-111111111111', 'migr_user@example.com', "
        "'dummy_hash', true, now(), now()) ON CONFLICT (id) DO NOTHING"
    )
    await run_query(user_insert)
    port_insert = (
        "INSERT INTO portfolios (id, user_id, name, created_at, updated_at) "
        "VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', "
        "'Migr Port', now(), now()) ON CONFLICT (id) DO NOTHING"
    )
    await run_query(port_insert)
    fund_cols = (
        "id, scheme_code, isin_growth, name, name_normalized, amc, category_raw, "
        "asset_class, classification_source, plan_type, option_type, is_active, "
        "is_tracked, first_seen_at, last_seen_at, created_at, updated_at"
    )
    fund_vals = (
        "'33333333-3333-3333-3333-333333333333', 999001, 'INF999001', 'Migr Fund', "
        "'migr fund', 'Migr AMC', 'Flexi Cap', 'equity', 'category', 'direct', "
        "'growth', true, false, now(), now(), now(), now()"
    )
    await run_query(
        f"INSERT INTO funds ({fund_cols}) VALUES ({fund_vals}) ON CONFLICT (scheme_code) DO NOTHING"
    )
    txn_cols = (
        "id, portfolio_id, fund_id, txn_type, txn_date, units, nav, amount, created_at, updated_at"
    )
    txn_vals = (
        "'44444444-4444-4444-4444-444444444444', '22222222-2222-2222-2222-222222222222', "
        "'33333333-3333-3333-3333-333333333333', 'buy', '2026-11-01', 10.0000, "
        "100.00000000, 1000.00, now(), now()"
    )
    await run_query(
        f"INSERT INTO transactions ({txn_cols}) VALUES ({txn_vals}) "
        "ON CONFLICT (id) DO UPDATE SET txn_type = 'buy'"
    )

    txn_sel = "SELECT txn_type FROM transactions WHERE id = '44444444-4444-4444-4444-444444444444'"
    r_val = await run_query(txn_sel)
    assert r_val is not None and r_val[0][0] == "buy"

    # 2. Downgrade to 0004
    await asyncio.to_thread(command.downgrade, alembic_cfg, "0004_portfolios_and_ledger")

    # 3. Verify state converted under 0004
    r_val_0004 = await run_query(txn_sel)
    assert r_val_0004 is not None and r_val_0004[0][0] == "BUY"

    rows_0004 = await run_query(
        "SELECT conname, pg_get_constraintdef(oid) "
        "FROM pg_constraint "
        "WHERE conname = 'ck_transactions_chk_transaction_type'"
    )
    assert rows_0004 is not None and len(rows_0004) > 0
    assert "BUY" in rows_0004[0][1]

    # 4. Upgrade back to 0005
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    # 5. Verify state converted under 0005
    r_val_head = await run_query(txn_sel)
    assert r_val_head is not None and r_val_head[0][0] == "buy"

    rows_head = await run_query(
        "SELECT conname, pg_get_constraintdef(oid) "
        "FROM pg_constraint "
        "WHERE conname = 'ck_transactions_chk_transaction_type'"
    )
    assert rows_head is not None and len(rows_head) > 0
    assert "buy" in rows_head[0][1]
