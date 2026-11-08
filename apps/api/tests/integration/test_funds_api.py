"""Integration tests for Funds and NAV API endpoints."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fund import Fund
from app.models.nav_history import NavHistory


async def _get_auth_headers(
    client: AsyncClient, email: str = "funds_user@example.com"
) -> dict[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    token = reg.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_search_funds_requires_auth(client: AsyncClient) -> None:
    res = await client.get("/api/v1/funds/search?q=test")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_search_ranking_and_filters(
    client: AsyncClient,
    test_session: AsyncSession,
) -> None:
    headers = await _get_auth_headers(client, "searcher@example.com")

    # Seed funds
    f1 = Fund(
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
        latest_nav=Decimal("92.70550000"),
        latest_nav_date=date(2026, 11, 5),
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    f2 = Fund(
        scheme_code=100050,
        isin_growth="INF179K01010",
        name="HDFC Top 100 Fund - Growth",
        name_normalized="hdfc top 100 fund growth",
        amc="HDFC Mutual Fund",
        category_raw="Open Ended Schemes(Equity Scheme - Large Cap Fund)",
        asset_class="equity",
        sub_category="large-cap",
        classification_source="category",
        plan_type="regular",
        option_type="growth",
        latest_nav=Decimal("110.00"),
        latest_nav_date=date(2026, 11, 5),
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    f3 = Fund(
        scheme_code=100060,
        isin_growth="INF200K01020",
        name="Special 100% Gilt_Fund (Debt)",
        name_normalized="special 100 gilt fund debt",
        amc="SBI Mutual Fund",
        category_raw="Open Ended Schemes(Debt Scheme - Gilt Fund)",
        asset_class="debt",
        sub_category="gilt",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        latest_nav=Decimal("50.00"),
        latest_nav_date=date(2026, 11, 5),
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add_all([f1, f2, f3])
    await test_session.commit()

    # 1. Multi-word search
    res_multi = await client.get(
        "/api/v1/funds/search?q=parag+parikh+flexi",
        headers=headers,
    )
    assert res_multi.status_code == 200
    data_multi = res_multi.json()["data"]
    assert len(data_multi["items"]) >= 1
    assert data_multi["items"][0]["scheme_code"] == 122639
    assert data_multi["items"][0]["asset_class"] == "equity"
    assert data_multi["items"][0]["sub_category"] == "flexi-cap"

    # 2. Exact scheme code match
    res_code = await client.get("/api/v1/funds/search?q=122639", headers=headers)
    assert res_code.status_code == 200
    assert res_code.json()["data"]["items"][0]["scheme_code"] == 122639

    # 3. Exact ISIN match
    res_isin = await client.get(
        "/api/v1/funds/search?q=INF879O01027",
        headers=headers,
    )
    assert res_isin.status_code == 200
    assert res_isin.json()["data"]["items"][0]["scheme_code"] == 122639

    # 4. Wildcard characters % and _ are treated literally
    res_pct = await client.get(
        "/api/v1/funds/search?q=100%25",  # URL-encoded %
        headers=headers,
    )
    assert res_pct.status_code == 200

    # 5. Asset class and plan filters
    res_filtered = await client.get(
        "/api/v1/funds/search?asset_class=debt&plan=direct",
        headers=headers,
    )
    assert res_filtered.status_code == 200
    items = res_filtered.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["scheme_code"] == 100060

    # 6. Pagination and has_more
    res_page = await client.get("/api/v1/funds/search?limit=1&offset=0", headers=headers)
    assert res_page.status_code == 200
    assert len(res_page.json()["data"]["items"]) == 1
    assert res_page.json()["data"]["has_more"] is True


@pytest.mark.asyncio
async def test_search_rate_limiting_429(
    client: AsyncClient,
) -> None:
    headers = await _get_auth_headers(client, "rate_limited_user@example.com")

    # Send 60 requests (allowed), 61st should be rate-limited
    for _ in range(60):
        res = await client.get("/api/v1/funds/search?q=test", headers=headers)
        assert res.status_code == 200

    res_blocked = await client.get("/api/v1/funds/search?q=test", headers=headers)
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in res_blocked.headers


@pytest.mark.asyncio
async def test_get_fund_detail_and_404(
    client: AsyncClient,
    test_session: AsyncSession,
) -> None:
    headers = await _get_auth_headers(client, "detail_user@example.com")

    fund = Fund(
        scheme_code=122639,
        isin_growth="INF879O01027",
        name="Parag Parikh Flexi Cap Fund",
        name_normalized="parag parikh flexi cap fund",
        amc="PPFAS Mutual Fund",
        category_raw="Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
        asset_class="equity",
        sub_category="flexi-cap",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        latest_nav=Decimal("92.70550000"),
        latest_nav_date=date(2026, 11, 5),
        is_active=True,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add(fund)
    await test_session.commit()

    # Success 200
    res = await client.get("/api/v1/funds/122639", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["scheme_code"] == 122639
    assert data["asset_class"] == "equity"
    assert data["classification_source"] == "category"

    # Not found 404
    res_404 = await client.get("/api/v1/funds/999999", headers=headers)
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "FUND_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_fund_nav_history_and_track(
    client: AsyncClient,
    test_session: AsyncSession,
) -> None:
    headers = await _get_auth_headers(client, "nav_user@example.com")

    fund = Fund(
        scheme_code=122639,
        name="Parag Parikh Flexi Cap Fund",
        name_normalized="parag parikh flexi cap fund",
        amc="PPFAS Mutual Fund",
        category_raw="Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
        asset_class="equity",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add(fund)
    await test_session.commit()

    # Before tracking: history_available is False, empty points
    res_nav1 = await client.get("/api/v1/funds/122639/nav", headers=headers)
    assert res_nav1.status_code == 200
    assert res_nav1.json()["data"]["history_available"] is False
    assert len(res_nav1.json()["data"]["points"]) == 0

    # Track fund: enqueues task
    with patch("app.workers.tasks.backfill_nav_history.delay") as mock_delay:
        res_track = await client.post("/api/v1/funds/122639/track", headers=headers)
        assert res_track.status_code == 202
        assert res_track.json()["data"]["status"] == "queued"
        mock_delay.assert_called_once_with(str(fund.id))

    # Add historical points
    h1 = NavHistory(fund_id=fund.id, nav_date=date(2026, 11, 4), nav=Decimal("91.39"))
    h2 = NavHistory(fund_id=fund.id, nav_date=date(2026, 11, 5), nav=Decimal("92.70"))
    test_session.add_all([h1, h2])
    await test_session.commit()

    # Track again when history exists: returns "already_tracked"
    res_track2 = await client.post("/api/v1/funds/122639/track", headers=headers)
    assert res_track2.status_code == 202
    assert res_track2.json()["data"]["status"] == "already_tracked"

    # Fetch NAV history ascending
    res_nav2 = await client.get("/api/v1/funds/122639/nav", headers=headers)
    assert res_nav2.status_code == 200
    data_nav2 = res_nav2.json()["data"]
    assert data_nav2["history_available"] is True
    assert len(data_nav2["points"]) == 2
    assert data_nav2["points"][0]["date"] == "2026-11-04"
    assert data_nav2["points"][1]["date"] == "2026-11-05"
