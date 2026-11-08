"""Integration tests for AMFI NAV synchronization, sanity guards, and locking."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.amfi import AmfiClient
from app.core.redis_lock import acquire_lock
from app.models.fund import Fund
from app.models.nav_history import NavHistory
from app.models.sync_run import NavSyncRun
from app.services.fund_sync import sync_amfi_funds_and_nav
from app.workers.tasks import LOCK_KEY_AMFI_SYNC, _async_sync_amfi_nav

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "NAVAll_sample.txt"


def _read_fixture() -> str:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return f.read()


@pytest.mark.asyncio
async def test_sync_fixture_idempotent(test_session: AsyncSession) -> None:
    fixture_text = _read_fixture()
    mock_client = AsyncMock(spec=AmfiClient)
    mock_client.fetch_navall.return_value = fixture_text

    # Run 1: initial sync with min_schemes=10 to allow sample fixture
    run1 = await sync_amfi_funds_and_nav(
        test_session,
        amfi_client=mock_client,
        min_schemes=10,
    )
    assert run1.status == "success"
    assert run1.funds_created > 0

    # Run 2: identical fixture should create 0 new funds and 0 updated funds
    run2 = await sync_amfi_funds_and_nav(
        test_session,
        amfi_client=mock_client,
        min_schemes=10,
    )
    assert run2.status == "success"
    assert run2.funds_created == 0
    assert run2.funds_updated == 0


@pytest.mark.asyncio
async def test_latest_nav_never_moves_backwards(test_session: AsyncSession) -> None:
    # Initial sync with date 2026-11-06, NAV 100.00
    row_v1 = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999001;INF999A01;INF999A02;Test NAV Guard Fund;Direct;Growth;100.00;06-Nov-2026\n"
    )
    mock_client = AsyncMock(spec=AmfiClient)
    mock_client.fetch_navall.return_value = row_v1

    await sync_amfi_funds_and_nav(test_session, amfi_client=mock_client, min_schemes=1)

    fund_stmt = select(Fund).where(Fund.scheme_code == 999001)
    fund = (await test_session.execute(fund_stmt)).scalar_one()
    assert fund.latest_nav == Decimal("100.00000000")
    assert fund.latest_nav_date == date(2026, 11, 6)

    # Attempt to sync older NAV (2026-11-05, NAV 90.00)
    row_v0 = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999001;INF999A01;INF999A02;Test NAV Guard Fund;Direct;Growth;90.00;05-Nov-2026\n"
    )
    mock_client.fetch_navall.return_value = row_v0
    await sync_amfi_funds_and_nav(test_session, amfi_client=mock_client, min_schemes=1)

    await test_session.refresh(fund)
    assert fund.latest_nav == Decimal("100.00000000")  # Did not move backwards
    assert fund.latest_nav_date == date(2026, 11, 6)

    # Newer NAV (2026-11-07, NAV 105.50)
    row_v2 = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999001;INF999A01;INF999A02;Test NAV Guard Fund;Direct;Growth;105.50;07-Nov-2026\n"
    )
    mock_client.fetch_navall.return_value = row_v2
    await sync_amfi_funds_and_nav(test_session, amfi_client=mock_client, min_schemes=1)

    await test_session.refresh(fund)
    assert fund.latest_nav == Decimal("105.50000000")  # Updated to newer date
    assert fund.latest_nav_date == date(2026, 11, 7)


@pytest.mark.asyncio
async def test_tracked_fund_gets_nav_history_untracked_does_not(
    test_session: AsyncSession,
) -> None:
    data = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999002;INF999B01;-;Tracked Fund;Direct;Growth;50.00;06-Nov-2026\n"
        "999003;INF999C01;-;Untracked Fund;Direct;Growth;60.00;06-Nov-2026\n"
    )
    mock_client = AsyncMock(spec=AmfiClient)
    mock_client.fetch_navall.return_value = data

    # First sync creates the funds
    await sync_amfi_funds_and_nav(test_session, amfi_client=mock_client, min_schemes=1)

    fund_stmt2 = select(Fund).where(Fund.scheme_code == 999002)
    fund2 = (await test_session.execute(fund_stmt2)).scalar_one()
    fund2.is_tracked = True
    await test_session.commit()

    # Second sync should write history row ONLY for 999002 (tracked)
    data_newer = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999002;INF999B01;-;Tracked Fund;Direct;Growth;51.00;07-Nov-2026\n"
        "999003;INF999C01;-;Untracked Fund;Direct;Growth;61.00;07-Nov-2026\n"
    )
    mock_client.fetch_navall.return_value = data_newer
    run = await sync_amfi_funds_and_nav(test_session, amfi_client=mock_client, min_schemes=1)
    assert run.nav_rows_written == 1

    fund_stmt3 = select(Fund).where(Fund.scheme_code == 999003)
    fund3 = (await test_session.execute(fund_stmt3)).scalar_one()

    hist2 = (
        (await test_session.execute(select(NavHistory).where(NavHistory.fund_id == fund2.id)))
        .scalars()
        .all()
    )
    hist3 = (
        (await test_session.execute(select(NavHistory).where(NavHistory.fund_id == fund3.id)))
        .scalars()
        .all()
    )

    assert len(hist2) == 1
    assert hist2[0].nav == Decimal("51.00000000")
    assert hist2[0].nav_date == date(2026, 11, 7)
    assert len(hist3) == 0


@pytest.mark.asyncio
async def test_stale_deactivation_and_reactivation(
    test_session: AsyncSession,
) -> None:
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    data_t0 = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999004;INF999D01;-;Disappearing Fund;Direct;Growth;10.00;01-Jan-2026\n"
    )
    mock_client = AsyncMock(spec=AmfiClient)
    mock_client.fetch_navall.return_value = data_t0

    await sync_amfi_funds_and_nav(
        test_session,
        amfi_client=mock_client,
        clock=lambda: t0,
        min_schemes=1,
    )

    fund_stmt = select(Fund).where(Fund.scheme_code == 999004)
    fund = (await test_session.execute(fund_stmt)).scalar_one()
    assert fund.is_active is True

    # 31 days later, fund is missing from file
    t1 = t0 + timedelta(days=31)
    data_t1 = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999005;INF999E01;-;Other Fund;Direct;Growth;20.00;01-Feb-2026\n"
    )
    mock_client.fetch_navall.return_value = data_t1
    await sync_amfi_funds_and_nav(
        test_session,
        amfi_client=mock_client,
        clock=lambda: t1,
        min_schemes=1,
        inactive_after_days=30,
    )

    await test_session.refresh(fund)
    assert fund.is_active is False  # Marked inactive

    # Fund reappears 5 days later
    t2 = t1 + timedelta(days=5)
    data_t2 = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999004;INF999D01;-;Disappearing Fund;Direct;Growth;11.00;06-Feb-2026\n"
    )
    mock_client.fetch_navall.return_value = data_t2
    await sync_amfi_funds_and_nav(
        test_session,
        amfi_client=mock_client,
        clock=lambda: t2,
        min_schemes=1,
    )

    await test_session.refresh(fund)
    assert fund.is_active is True  # Reactivated


@pytest.mark.asyncio
async def test_sanity_guard_aborts_on_truncation_or_html(
    test_session: AsyncSession,
) -> None:
    # Pre-seed active fund
    f = Fund(
        scheme_code=999006,
        name="Existing Sane Fund",
        name_normalized="existing sane fund",
        amc="Test AMC",
        category_raw="Open Ended Schemes(Equity Scheme - Large Cap Fund)",
        asset_class="equity",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        is_active=True,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add(f)
    await test_session.commit()

    # Truncated payload with min_schemes=5000 default
    truncated = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999007;INF007;-;Truncated;Direct;Growth;10.0;06-Nov-2026\n"
    )
    mock_client = AsyncMock(spec=AmfiClient)
    mock_client.fetch_navall.return_value = truncated

    run = await sync_amfi_funds_and_nav(
        test_session,
        amfi_client=mock_client,
        min_schemes=5000,
    )
    assert run.status == "aborted"
    assert "below minimum threshold" in str(run.error_summary)

    # Verify no funds were added or deactivated
    count = (await test_session.execute(select(Fund))).scalars().all()
    assert len(count) == 1
    assert count[0].scheme_code == 999006


@pytest.mark.asyncio
async def test_concurrent_sync_lock_skips_second(test_session: AsyncSession) -> None:
    # Use real test Redis (db 1)
    from redis.asyncio import Redis

    from app.core.config import get_settings

    settings = get_settings()
    test_redis = Redis.from_url(settings.TEST_REDIS_URL, decode_responses=True)

    # Pre-acquire the lock
    owner = await acquire_lock(test_redis, LOCK_KEY_AMFI_SYNC, timeout_seconds=30)
    assert owner is not None

    try:
        # Run Celery task async worker while lock is held
        res = await _async_sync_amfi_nav(
            db_url=settings.TEST_DATABASE_URL,
            redis_url=settings.TEST_REDIS_URL,
        )
        assert res["status"] == "skipped"
        assert res["reason"] == "lock_held"

        # Verify a run record was saved with status="skipped"
        latest_run = (
            await test_session.execute(
                select(NavSyncRun).order_by(NavSyncRun.started_at.desc()).limit(1)
            )
        ).scalar_one()
        assert latest_run.status == "skipped"
        assert "Concurrent sync in progress" in str(latest_run.error_summary)
    finally:
        await test_redis.delete(LOCK_KEY_AMFI_SYNC)
        await test_redis.aclose()


@pytest.mark.asyncio
async def test_nav_write_through_mfapi_ending_t_and_amfi_sync_t_plus_1(
    test_session: AsyncSession,
) -> None:
    """Verify when a tracked fund's latest NAV is updated by AMFI sync,

    that NAV point is also written into nav_history (ending on T+1).
    """
    from sqlalchemy import func

    from app.clients.mfapi import MfapiClient
    from app.services.nav_backfill import backfill_fund_nav_history

    # 1. Create a tracked fund
    fund = Fund(
        scheme_code=999100,
        isin_growth="INF999W01",
        name="Write Through Fund - Direct Plan - Growth",
        name_normalized="write through fund direct plan growth",
        amc="Test AMC",
        category_raw="Open Ended Schemes(Equity Scheme - Large Cap Fund)",
        asset_class="equity",
        sub_category="large-cap",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        is_active=True,
        is_tracked=True,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add(fund)
    await test_session.commit()

    # 2. Mock mfapi ending on date T = 2026-11-05
    mock_mfapi = AsyncMock(spec=MfapiClient)
    mock_mfapi.fetch_scheme_history.return_value = {
        "meta": {"scheme_code": 999100, "scheme_name": "Write Through Fund"},
        "data": [
            {"date": "05-11-2026", "nav": "100.00"},
            {"date": "04-11-2026", "nav": "99.50"},
        ],
    }
    backfill_run = await backfill_fund_nav_history(test_session, fund, mfapi_client=mock_mfapi)
    assert backfill_run.status == "success"

    # Verify nav_history currently ends on date T (2026-11-05)
    max_d1 = (
        await test_session.execute(
            select(func.max(NavHistory.nav_date)).where(NavHistory.fund_id == fund.id)
        )
    ).scalar_one()
    assert max_d1 == date(2026, 11, 5)

    # 3. AMFI sync runs giving a point on date T+1 (2026-11-06)
    row_t_plus_1 = (
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Test AMC\n"
        "999100;INF999W01;-;Write Through Fund - Direct Plan - Growth;"
        "Direct;Growth;102.50;06-Nov-2026\n"
    )
    mock_amfi = AsyncMock(spec=AmfiClient)
    mock_amfi.fetch_navall.return_value = row_t_plus_1

    sync_run = await sync_amfi_funds_and_nav(test_session, amfi_client=mock_amfi, min_schemes=1)
    assert sync_run.status == "success"
    assert sync_run.nav_rows_written == 1

    # 4. Verify nav_history now ends on T+1 (2026-11-06) with NAV 102.50
    max_d2 = (
        await test_session.execute(
            select(func.max(NavHistory.nav_date)).where(NavHistory.fund_id == fund.id)
        )
    ).scalar_one()
    assert max_d2 == date(2026, 11, 6)

    latest_point = (
        await test_session.execute(
            select(NavHistory).where(
                NavHistory.fund_id == fund.id,
                NavHistory.nav_date == date(2026, 11, 6),
            )
        )
    ).scalar_one()
    assert latest_point.nav == Decimal("102.50000000")
