"""Integration tests for import Celery tasks, schedules, and cleanup."""

import asyncio
import datetime as dt
from uuid import uuid4

import pytest
from celery.schedules import crontab
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_batch import TransactionImport, TransactionImportRow
from app.models.portfolio import Portfolio
from app.models.user import User
from app.workers.beat_schedule import (
    CELERY_BEAT_SCHEDULE,
    IMPORT_PURGE_HOUR_IST,
    IMPORT_PURGE_HOUR_UTC,
    IMPORT_PURGE_MINUTE_IST,
    IMPORT_PURGE_MINUTE_UTC,
)
from app.workers.tasks import purge_expired_import_previews


def test_import_purge_beat_schedule_times() -> None:
    """Verify IST (04:00) and UTC (22:30 previous day) constants agree."""
    # 04:00 IST = 22:30 UTC previous day (IST is UTC + 5:30)
    # (22 * 60 + 30 + 330) % 1440 = (1350 + 330) % 1440 = 1680 % 1440 = 240 = 4 * 60 + 0
    utc_minutes = IMPORT_PURGE_HOUR_UTC * 60 + IMPORT_PURGE_MINUTE_UTC
    ist_minutes = IMPORT_PURGE_HOUR_IST * 60 + IMPORT_PURGE_MINUTE_IST
    assert (utc_minutes + 330) % 1440 == ist_minutes

    assert "purge-expired-import-previews-daily" in CELERY_BEAT_SCHEDULE
    entry = CELERY_BEAT_SCHEDULE["purge-expired-import-previews-daily"]
    sched = entry["schedule"]
    assert isinstance(sched, crontab)
    assert sched.hour == {IMPORT_PURGE_HOUR_UTC}
    assert sched.minute == {IMPORT_PURGE_MINUTE_UTC}


@pytest.mark.asyncio
async def test_purge_expired_import_previews_task(test_session: AsyncSession) -> None:
    # 1. Create a user and portfolio
    user = User(
        email=f"purge_{uuid4().hex[:8]}@example.com",
        password_hash="dummy_hash",
        is_active=True,
    )
    test_session.add(user)
    await test_session.flush()

    port = Portfolio(
        user_id=user.id,
        name="Purge Test Portfolio",
    )
    test_session.add(port)
    await test_session.flush()

    now = dt.datetime.now(dt.UTC)

    # 2. Expired preview (should be purged)
    expired_imp = TransactionImport(
        portfolio_id=port.id,
        status="previewed",
        filename="expired.xlsx",
        file_sha256="sha_exp",
        file_size=1024,
        rows_total=1,
        rows_ok=1,
        rows_warning=0,
        rows_duplicate=0,
        rows_error=0,
        will_import=1,
        plan_fingerprint="fp_exp",
        expires_at=now - dt.timedelta(hours=2),
    )
    test_session.add(expired_imp)
    await test_session.flush()

    exp_row = TransactionImportRow(
        import_id=expired_imp.id,
        row_number=2,
        status="ok",
        raw={},
        messages=[],
    )
    test_session.add(exp_row)

    # 3. Valid preview (not expired, should NOT be purged)
    # (Note: we use a different portfolio to avoid partial unique index collision on previewed)
    port2 = Portfolio(
        user_id=user.id,
        name="Purge Test Portfolio 2",
    )
    test_session.add(port2)
    await test_session.flush()

    valid_imp = TransactionImport(
        portfolio_id=port2.id,
        status="previewed",
        filename="valid.xlsx",
        file_sha256="sha_valid",
        file_size=1024,
        rows_total=1,
        rows_ok=1,
        rows_warning=0,
        rows_duplicate=0,
        rows_error=0,
        will_import=1,
        plan_fingerprint="fp_valid",
        expires_at=now + dt.timedelta(hours=22),
    )
    test_session.add(valid_imp)
    await test_session.flush()

    valid_row = TransactionImportRow(
        import_id=valid_imp.id,
        row_number=2,
        status="ok",
        raw={},
        messages=[],
    )
    test_session.add(valid_row)

    # 4. Committed import with expired date (committed imports are NEVER purged)
    port3 = Portfolio(
        user_id=user.id,
        name="Purge Test Portfolio 3",
    )
    test_session.add(port3)
    await test_session.flush()

    committed_imp = TransactionImport(
        portfolio_id=port3.id,
        status="committed",
        filename="committed.xlsx",
        file_sha256="sha_comm",
        file_size=1024,
        rows_total=1,
        rows_ok=1,
        rows_warning=0,
        rows_duplicate=0,
        rows_error=0,
        will_import=1,
        plan_fingerprint="fp_comm",
        expires_at=now - dt.timedelta(hours=5),
        committed_at=now - dt.timedelta(hours=5),
        committed_count=1,
    )
    test_session.add(committed_imp)
    await test_session.commit()

    exp_id = expired_imp.id
    exp_row_id = exp_row.id
    valid_id = valid_imp.id
    comm_id = committed_imp.id

    # Run purge task in thread
    purged_count = await asyncio.to_thread(purge_expired_import_previews)
    assert purged_count >= 1

    # Verify database state using direct queries on fresh connection
    res_exp = (
        await test_session.execute(select(TransactionImport).where(TransactionImport.id == exp_id))
    ).scalar_one_or_none()
    assert res_exp is None

    res_row = (
        await test_session.execute(
            select(TransactionImportRow).where(TransactionImportRow.id == exp_row_id)
        )
    ).scalar_one_or_none()
    assert res_row is None

    res_valid = (
        await test_session.execute(
            select(TransactionImport).where(TransactionImport.id == valid_id)
        )
    ).scalar_one_or_none()
    assert res_valid is not None

    res_comm = (
        await test_session.execute(select(TransactionImport).where(TransactionImport.id == comm_id))
    ).scalar_one_or_none()
    assert res_comm is not None
