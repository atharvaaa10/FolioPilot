"""Integration tests for SIP Celery tasks, schedules, and triggers."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fund import Fund
from app.workers.beat_schedule import (
    CELERY_BEAT_SCHEDULE,
    SIP_EVENING_HOUR_IST,
    SIP_EVENING_HOUR_UTC,
    SIP_EVENING_MINUTE_IST,
    SIP_EVENING_MINUTE_UTC,
    SIP_MORNING_HOUR_IST,
    SIP_MORNING_HOUR_UTC,
    SIP_MORNING_MINUTE_IST,
    SIP_MORNING_MINUTE_UTC,
)


def test_sip_beat_schedule_times() -> None:
    """Verify that IST and UTC constants agree for morning and evening beat schedule."""
    # 22:15 IST = 16:45 UTC (IST is UTC + 5:30)
    # Morning: 06:30 IST = 01:00 UTC
    evening_ist_minutes = SIP_EVENING_HOUR_IST * 60 + SIP_EVENING_MINUTE_IST
    evening_utc_minutes = SIP_EVENING_HOUR_UTC * 60 + SIP_EVENING_MINUTE_UTC
    assert evening_ist_minutes - evening_utc_minutes == 330  # 5 hours 30 mins

    morning_ist_minutes = SIP_MORNING_HOUR_IST * 60 + SIP_MORNING_MINUTE_IST
    morning_utc_minutes = SIP_MORNING_HOUR_UTC * 60 + SIP_MORNING_MINUTE_UTC
    assert morning_ist_minutes - morning_utc_minutes == 330

    assert "execute-due-sip-installments-evening" in CELERY_BEAT_SCHEDULE
    assert "execute-due-sip-installments-morning" in CELERY_BEAT_SCHEDULE

    from celery.schedules import crontab

    evening_entry = CELERY_BEAT_SCHEDULE["execute-due-sip-installments-evening"]
    evening_sched = evening_entry["schedule"]
    assert isinstance(evening_sched, crontab)
    assert evening_sched.hour == {SIP_EVENING_HOUR_UTC}
    assert evening_sched.minute == {SIP_EVENING_MINUTE_UTC}

    morning_entry = CELERY_BEAT_SCHEDULE["execute-due-sip-installments-morning"]
    morning_sched = morning_entry["schedule"]
    assert isinstance(morning_sched, crontab)
    assert morning_sched.hour == {SIP_MORNING_HOUR_UTC}
    assert morning_sched.minute == {SIP_MORNING_MINUTE_UTC}


async def _get_auth_headers(client: AsyncClient, email: str) -> dict[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    token = res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_test_fund(
    session: AsyncSession,
    scheme_code: int = 150001,
    name: str = "SIP Trigger Test Fund",
) -> Fund:
    fund = Fund(
        scheme_code=scheme_code,
        isin_growth=f"INF{scheme_code}",
        name=name,
        name_normalized=name.lower(),
        amc="Test AMC",
        category_raw="Flexi Cap",
        asset_class="equity",
        sub_category="flexi-cap",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        latest_nav=Decimal("100.00"),
        latest_nav_date=date(2026, 11, 1),
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(fund)
    await session.commit()
    return fund


@pytest.mark.asyncio
async def test_sip_create_enqueues_execution(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify that creating a SIP enqueues execute_pending_for_fund."""
    headers = await _get_auth_headers(client, "sip_enqueue_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=150002)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "SIP Enqueue Portfolio"},
        headers=headers,
    )
    portfolio_id = r_port.json()["data"]["id"]

    with patch("app.workers.tasks.execute_pending_for_fund.delay") as mock_delay:
        r_sip = await client.post(
            f"/api/v1/portfolios/{portfolio_id}/sips",
            json={
                "fund_id": str(fund.id),
                "amount": "5000.00",
                "day_of_month": 10,
                "start_date": "2026-05-01",
            },
            headers=headers,
        )
        assert r_sip.status_code == 201
        mock_delay.assert_called_once_with(str(fund.id))


@pytest.mark.asyncio
async def test_sip_create_enqueue_failure_does_not_fail_request(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify that Celery enqueue failure on SIP create is logged and request still succeeds."""
    headers = await _get_auth_headers(client, "sip_enqueue_fail_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=150003)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "SIP Enqueue Fail Portfolio"},
        headers=headers,
    )
    portfolio_id = r_port.json()["data"]["id"]

    with patch(
        "app.workers.tasks.execute_pending_for_fund.delay",
        side_effect=Exception("Redis connection error"),
    ):
        r_sip = await client.post(
            f"/api/v1/portfolios/{portfolio_id}/sips",
            json={
                "fund_id": str(fund.id),
                "amount": "5000.00",
                "day_of_month": 10,
                "start_date": "2026-05-01",
            },
            headers=headers,
        )
        assert r_sip.status_code == 201
        assert "id" in r_sip.json()["data"]


@pytest.mark.asyncio
async def test_nav_backfill_enqueues_execution(test_session: AsyncSession) -> None:
    """Verify that successful backfill enqueues execute_pending_for_fund."""
    from unittest.mock import AsyncMock

    from app.clients.mfapi import MfapiClient
    from app.services.nav_backfill import backfill_fund_nav_history

    fund = await _seed_test_fund(test_session, scheme_code=150004)

    mock_client = AsyncMock(spec=MfapiClient)
    mock_client.fetch_scheme_history.return_value = {
        "status": "SUCCESS",
        "data": [
            {"date": "05-11-2026", "nav": "105.50"},
            {"date": "04-11-2026", "nav": "104.20"},
        ],
    }

    with patch("app.workers.tasks.execute_pending_for_fund.delay") as mock_delay:
        run = await backfill_fund_nav_history(test_session, fund, mfapi_client=mock_client)
        assert run.status == "success"
        mock_delay.assert_called_once_with(str(fund.id))
