"""Integration tests for historical NAV backfill via mfapi.in."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.mfapi import MfapiClient, MfapiFetchError
from app.models.fund import Fund
from app.models.nav_history import NavHistory
from app.services.nav_backfill import backfill_fund_nav_history

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mfapi_122639_sample.json"


def _read_mfapi_fixture() -> dict[str, Any]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


@pytest.mark.asyncio
async def test_backfill_idempotent_and_records_run(test_session: AsyncSession) -> None:
    fund = Fund(
        scheme_code=122639,
        isin_growth="INF879O01027",
        name="Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
        name_normalized="parag parikh flexi cap fund direct plan growth",
        amc="PPFAS Mutual Fund",
        category_raw="Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
        asset_class="equity",
        sub_category="flexi-cap",
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

    payload = _read_mfapi_fixture()
    mock_client = AsyncMock(spec=MfapiClient)
    mock_client.fetch_scheme_history.return_value = payload

    # Run 1: initial backfill
    run1 = await backfill_fund_nav_history(test_session, fund, mfapi_client=mock_client)
    assert run1.status == "success"
    assert run1.nav_rows_written == 30

    history_rows = (
        (await test_session.execute(select(NavHistory).where(NavHistory.fund_id == fund.id)))
        .scalars()
        .all()
    )
    assert len(history_rows) == 30

    # Verify fund latest NAV updated
    await test_session.refresh(fund)
    assert fund.latest_nav == Decimal("92.70550000")
    assert fund.latest_nav_date == date(2026, 11, 5)

    # Run 2: second backfill is idempotent (does not duplicate rows)
    run2 = await backfill_fund_nav_history(test_session, fund, mfapi_client=mock_client)
    assert run2.status == "success"

    history_rows_after = (
        (await test_session.execute(select(NavHistory).where(NavHistory.fund_id == fund.id)))
        .scalars()
        .all()
    )
    assert len(history_rows_after) == 30


@pytest.mark.asyncio
async def test_backfill_failure_records_failed_run_without_corrupting_history(
    test_session: AsyncSession,
) -> None:
    fund = Fund(
        scheme_code=122639,
        isin_growth="INF879O01027",
        name="Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
        name_normalized="parag parikh flexi cap fund direct plan growth",
        amc="PPFAS Mutual Fund",
        category_raw="Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
        asset_class="equity",
        sub_category="flexi-cap",
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

    # Pre-existing history point
    h0 = NavHistory(
        fund_id=fund.id,
        nav_date=date(2026, 11, 1),
        nav=Decimal("90.00"),
    )
    test_session.add(h0)
    await test_session.commit()

    # Client fails with MfapiFetchError
    mock_client = AsyncMock(spec=MfapiClient)
    mock_client.fetch_scheme_history.side_effect = MfapiFetchError("Connection timeout")

    run = await backfill_fund_nav_history(test_session, fund, mfapi_client=mock_client)
    assert run.status == "failed"
    assert "Connection timeout" in str(run.error_summary)

    # Existing history row remains untouched
    history_rows = (
        (await test_session.execute(select(NavHistory).where(NavHistory.fund_id == fund.id)))
        .scalars()
        .all()
    )
    assert len(history_rows) == 1
    assert history_rows[0].nav == Decimal("90.00000000")


@pytest.mark.asyncio
async def test_backfill_writes_through_newer_amfi_nav_when_mfapi_lags(
    test_session: AsyncSession,
) -> None:
    # Fund has AMFI latest NAV at date T+1 (2026-11-06)
    fund = Fund(
        scheme_code=999101,
        isin_growth="INF999W02",
        name="Lax Fund - Direct Plan - Growth",
        name_normalized="lax fund direct plan growth",
        amc="Test AMC",
        category_raw="Open Ended Schemes(Equity Scheme - Large Cap Fund)",
        asset_class="equity",
        sub_category="large-cap",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        latest_nav=Decimal("150.00"),
        latest_nav_date=date(2026, 11, 6),
        is_active=True,
        is_tracked=True,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add(fund)
    await test_session.commit()

    # mfapi response only has points up to date T (2026-11-05)
    mock_client = AsyncMock(spec=MfapiClient)
    mock_client.fetch_scheme_history.return_value = {
        "meta": {"scheme_code": 999101, "scheme_name": "Lax Fund"},
        "data": [
            {"date": "05-11-2026", "nav": "148.00"},
            {"date": "04-11-2026", "nav": "147.00"},
        ],
    }

    run = await backfill_fund_nav_history(test_session, fund, mfapi_client=mock_client)
    assert run.status == "success"

    # Verify nav_history contains mfapi points AND the write-through point for 2026-11-06
    rows = (
        (
            await test_session.execute(
                select(NavHistory)
                .where(NavHistory.fund_id == fund.id)
                .order_by(NavHistory.nav_date.desc())
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert rows[0].nav_date == date(2026, 11, 6)
    assert rows[0].nav == Decimal("150.00000000")
    assert rows[1].nav_date == date(2026, 11, 5)
