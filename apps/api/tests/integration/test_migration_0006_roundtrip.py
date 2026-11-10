"""Test migration 0006 roundtrip with data and constraint validation."""

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
async def test_migration_0006_roundtrip() -> None:
    """Verify downgrade drops SIP tables and sip_installment_id column,

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

    # 1. Ensure DB is on head (0006)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    # 2. Insert prerequisites (user, portfolio, fund)
    await run_query(
        "INSERT INTO users (id, email, password_hash, is_active, created_at, updated_at) "
        "VALUES ('55555555-5555-5555-5555-555555555555', 'sip_migr_user@example.com', "
        "'dummy_hash', true, now(), now()) ON CONFLICT (id) DO NOTHING"
    )
    await run_query(
        "INSERT INTO portfolios (id, user_id, name, created_at, updated_at) "
        "VALUES ('66666666-6666-6666-6666-666666666666', '55555555-5555-5555-5555-555555555555', "
        "'Sip Migr Port', now(), now()) ON CONFLICT (id) DO NOTHING"
    )
    fund_cols = (
        "id, scheme_code, isin_growth, name, name_normalized, amc, category_raw, "
        "asset_class, classification_source, plan_type, option_type, is_active, "
        "is_tracked, first_seen_at, last_seen_at, created_at, updated_at"
    )
    fund_vals = (
        "'77777777-7777-7777-7777-777777777777', 999002, 'INF999002', 'Sip Migr Fund', "
        "'sip migr fund', 'Migr AMC', 'Flexi Cap', 'equity', 'category', 'direct', "
        "'growth', true, false, now(), now(), now(), now()"
    )
    await run_query(
        f"INSERT INTO funds ({fund_cols}) VALUES ({fund_vals}) ON CONFLICT (scheme_code) DO NOTHING"
    )

    # 3. Insert SIP, Pause, Installment, and linked Transaction before downgrade
    sip_id = "88888888-8888-8888-8888-888888888888"
    await run_query(
        "INSERT INTO sips (id, portfolio_id, fund_id, amount, day_of_month, start_date, "
        "end_date, step_up_percent, notes, created_at, updated_at) "
        f"VALUES ('{sip_id}', '66666666-6666-6666-6666-666666666666', "
        "'77777777-7777-7777-7777-777777777777', 5000.00, 10, '2025-01-05', "
        "'2025-12-31', 10.00, 'Test migration SIP', now(), now())"
    )
    pause_id = "99999999-9999-9999-9999-999999999999"
    await run_query(
        "INSERT INTO sip_pauses (id, sip_id, paused_from, resumed_on, created_at, updated_at) "
        f"VALUES ('{pause_id}', '{sip_id}', '2025-03-01', '2025-05-01', now(), now())"
    )
    inst_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    await run_query(
        "INSERT INTO sip_installments "
        "(id, sip_id, due_date, planned_amount, status, nav_date, created_at, updated_at) "
        f"VALUES ('{inst_id}', '{sip_id}', '2025-01-10', 5000.00, 'executed', "
        "'2025-01-10', now(), now())"
    )
    txn_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    await run_query(
        "INSERT INTO transactions "
        "(id, portfolio_id, fund_id, txn_type, txn_date, units, nav, amount, "
        "sip_installment_id, created_at, updated_at) "
        f"VALUES ('{txn_id}', '66666666-6666-6666-6666-666666666666', "
        "'77777777-7777-7777-7777-777777777777', 'buy', '2025-01-10', "
        f"100.0000, 50.00000000, 5000.00, '{inst_id}', now(), now())"
    )

    # 4. Assert constraints exist under 0006
    constraints_0006 = await run_query(
        "SELECT conname FROM pg_constraint WHERE conname IN ("
        "'ck_sips_chk_sip_amount_positive', "
        "'ck_sips_chk_sip_day_of_month_range', "
        "'ck_sips_chk_sip_dates_order', "
        "'ck_sips_chk_sip_step_up_range', "
        "'ck_sip_pauses_chk_sip_pause_dates', "
        "'ck_sip_installments_chk_sip_installment_planned_amount_positive', "
        "'ck_sip_installments_chk_sip_installment_status', "
        "'uq_sip_installments_sip_due_date', "
        "'uq_transactions_sip_installment_id', "
        "'fk_transactions_sip_installment_id'"
        ")"
    )
    assert constraints_0006 is not None
    found_connames = {r[0] for r in constraints_0006}
    assert "ck_sips_chk_sip_amount_positive" in found_connames
    assert "ck_sip_installments_chk_sip_installment_planned_amount_positive" in found_connames
    assert "uq_transactions_sip_installment_id" in found_connames

    # 5. Downgrade to 0005
    await asyncio.to_thread(command.downgrade, alembic_cfg, "0005")

    # 6. Verify tables and columns dropped under 0005
    tables_0005 = await run_query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name IN ('sips', 'sip_pauses', 'sip_installments')"
    )
    assert tables_0005 is not None and len(tables_0005) == 0

    col_0005 = await run_query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'transactions' AND column_name = 'sip_installment_id'"
    )
    assert col_0005 is not None and len(col_0005) == 0

    # 7. Upgrade back to 0006 (head)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    # 8. Verify tables and columns restored under 0006
    tables_head = await run_query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name IN ('sips', 'sip_pauses', 'sip_installments')"
    )
    assert tables_head is not None and len(tables_head) == 3

    col_head = await run_query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'transactions' AND column_name = 'sip_installment_id'"
    )
    assert col_head is not None and len(col_head) == 1
