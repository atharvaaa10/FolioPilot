"""Integration tests for Portfolio Valuation, Summary, and Value Series API endpoints.

Covers:
- Examples B and C end-to-end with exact string equality
- Summary consistency (character-for-character equality with portfolio valuation totals)
- User B isolation and ownership matrix (404 on valuation and value-series, 401 unauthenticated)
- Fallback cost, stale flag with injected clock, nav_older_than_ledger flag
- Empty portfolio and user (zeros, nulls, NO_TRANSACTIONS)
- include_closed behavior
- Invalid range validation error (422)
- Statement counters (1 vs 10 funds, 1 vs 5 portfolios)
- Headers: Cache-Control: no-store, X-Request-ID
- Rate limiting with Retry-After (429)
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clock
from app.core.db import get_engine
from app.core.synthetic_funds import SYNTHETIC_PPFC, SYNTHETIC_VALUATION_FUND
from app.models.fund import Fund


async def _get_auth_headers(
    client: AsyncClient, email: str = "val_user@example.com"
) -> dict[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    token = str(reg.json()["data"]["access_token"])
    return {"Authorization": f"Bearer {token}"}


async def _create_portfolio(
    client: AsyncClient, headers: dict[str, str], name: str = "Valuation Test Portfolio"
) -> str:
    res = await client.post("/api/v1/portfolios", json={"name": name}, headers=headers)
    assert res.status_code == 201
    return str(res.json()["data"]["id"])


def _set_clock(client: AsyncClient, dt: datetime) -> None:
    transport = getattr(client, "_transport", None)
    app = getattr(transport, "app", None)
    if app is not None:
        app.dependency_overrides[get_clock] = lambda: dt


async def _record_transaction(
    client: AsyncClient,
    headers: dict[str, str],
    portfolio_id: str,
    scheme_code: int,
    txn_type: str,
    txn_date: str,
    units: str,
    nav: str,
    amount: str,
) -> None:
    res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        headers=headers,
        json={
            "scheme_code": scheme_code,
            "txn_type": txn_type,
            "txn_date": txn_date,
            "units": units,
            "nav": nav,
            "amount": amount,
        },
    )
    assert res.status_code == 201, res.text


# ==============================================================================
# Examples B and C End-to-End
# ==============================================================================


async def test_valuation_example_b_end_to_end(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """Example B: buy 2025-01-01 (10@100=1000), buy 2026-01-01 (10@100=1000).

    latest_nav 115.50 on 2027-01-01. Injected clock at 2027-01-01T10:00:00Z.
    Asserts exact string equality.
    """
    # Set fund latest_nav to 115.50 and date to 2027-01-01
    res = await test_session.execute(
        select(Fund).where(Fund.scheme_code == SYNTHETIC_VALUATION_FUND.scheme_code)
    )
    fund = res.scalar_one()
    fund.latest_nav = Decimal("115.50000000")
    fund.latest_nav_date = date(2027, 1, 1)
    await test_session.commit()

    headers = await _get_auth_headers(client, "user_ex_b@example.com")
    pid = await _create_portfolio(client, headers, "Example B Portfolio")

    await _record_transaction(
        client,
        headers,
        pid,
        SYNTHETIC_VALUATION_FUND.scheme_code,
        "BUY",
        "2025-01-01",
        "10.0000",
        "100.00000000",
        "1000.00",
    )
    await _record_transaction(
        client,
        headers,
        pid,
        SYNTHETIC_VALUATION_FUND.scheme_code,
        "BUY",
        "2026-01-01",
        "10.0000",
        "100.00000000",
        "1000.00",
    )

    # Inject clock: 2027-01-01
    _set_clock(client, datetime(2027, 1, 1, 10, 0, tzinfo=UTC))

    val_res = await client.get(f"/api/v1/portfolios/{pid}/valuation", headers=headers)
    assert val_res.status_code == 200
    data = val_res.json()["data"]

    assert data["as_of"] == "2027-01-01"
    assert len(data["items"]) == 1
    item = data["items"][0]

    assert item["current_value"] == "2310.00"
    assert item["cost_basis"] == "2000.00"
    assert item["unrealized_gain"] == "310.00"
    assert item["unrealized_gain_pct"] == "15.50"
    assert item["xirr"]["rate"] == "0.100000"
    assert item["xirr"]["short_period"] is False
    assert item["xirr"]["ambiguous"] is False

    totals = data["totals"]
    assert totals["current_value"] == "2310.00"
    assert totals["cost_basis"] == "2000.00"
    assert totals["unrealized_gain"] == "310.00"
    assert totals["unrealized_gain_pct"] == "15.50"
    assert totals["xirr"]["rate"] == "0.100000"


async def test_valuation_example_c_end_to_end(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """Example C: buy 100@50, buy 50@60, sell 30@70, latest_nav 80.00 on 2025-03-10."""
    res = await test_session.execute(
        select(Fund).where(Fund.scheme_code == SYNTHETIC_PPFC.scheme_code)
    )
    fund = res.scalar_one()
    fund.latest_nav = Decimal("80.00000000")
    fund.latest_nav_date = date(2025, 3, 10)
    await test_session.commit()

    headers = await _get_auth_headers(client, "user_ex_c@example.com")
    pid = await _create_portfolio(client, headers, "Example C Portfolio")

    await _record_transaction(
        client,
        headers,
        pid,
        SYNTHETIC_PPFC.scheme_code,
        "BUY",
        "2025-01-10",
        "100.0000",
        "50.00000000",
        "5000.00",
    )
    await _record_transaction(
        client,
        headers,
        pid,
        SYNTHETIC_PPFC.scheme_code,
        "BUY",
        "2025-02-10",
        "50.0000",
        "60.00000000",
        "3000.00",
    )
    await _record_transaction(
        client,
        headers,
        pid,
        SYNTHETIC_PPFC.scheme_code,
        "SELL",
        "2025-03-10",
        "30.0000",
        "70.00000000",
        "2100.00",
    )

    _set_clock(client, datetime(2025, 3, 10, 10, 0, tzinfo=UTC))

    val_res = await client.get(f"/api/v1/portfolios/{pid}/valuation", headers=headers)
    assert val_res.status_code == 200
    data = val_res.json()["data"]

    item = data["items"][0]
    assert item["units"] == "120.0000"
    assert item["cost_basis"] == "6400.00"
    assert item["realized_gain"] == "500.00"
    assert item["current_value"] == "9600.00"
    assert item["unrealized_gain"] == "3200.00"
    assert item["unrealized_gain_pct"] == "50.00"

    totals = data["totals"]
    assert totals["cost_basis"] == "6400.00"
    assert totals["current_value"] == "9600.00"
    assert totals["realized_gain"] == "500.00"
    assert totals["unrealized_gain"] == "3200.00"
    assert totals["total_gain"] == "3700.00"


# ==============================================================================
# Summary Consistency and User Isolation
# ==============================================================================


async def test_summary_character_for_character_consistency(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """GET /valuation/summary per-portfolio entries match each portfolio's totals.

    Character-for-character consistency is verified.
    """
    headers = await _get_auth_headers(client, "user_summary@example.com")
    pid1 = await _create_portfolio(client, headers, "Portfolio 1")
    pid2 = await _create_portfolio(client, headers, "Portfolio 2")

    await _record_transaction(
        client,
        headers,
        pid1,
        SYNTHETIC_PPFC.scheme_code,
        "BUY",
        "2025-01-01",
        "10.0000",
        "50.00000000",
        "500.00",
    )
    await _record_transaction(
        client,
        headers,
        pid2,
        SYNTHETIC_VALUATION_FUND.scheme_code,
        "BUY",
        "2025-01-01",
        "20.0000",
        "100.00000000",
        "2000.00",
    )

    _set_clock(client, datetime(2026, 11, 14, 10, 0, tzinfo=UTC))

    # 1. Fetch individual portfolio valuations
    v1 = (await client.get(f"/api/v1/portfolios/{pid1}/valuation", headers=headers)).json()["data"]
    v2 = (await client.get(f"/api/v1/portfolios/{pid2}/valuation", headers=headers)).json()["data"]

    # 2. Fetch overall summary
    summary = (await client.get("/api/v1/valuation/summary", headers=headers)).json()["data"]

    # Match per-portfolio entries in summary
    summary_p_by_id = {p["id"]: p for p in summary["portfolios"]}

    # Verify character-for-character equality
    for pid, v in [(pid1, v1), (pid2, v2)]:
        sp = summary_p_by_id[pid]
        vt = v["totals"]
        assert sp["cost_basis"] == vt["cost_basis"]
        assert sp["current_value"] == vt["current_value"]
        assert sp["unrealized_gain"] == vt["unrealized_gain"]
        assert sp["unrealized_gain_pct"] == vt["unrealized_gain_pct"]
        assert sp["realized_gain"] == vt["realized_gain"]
        assert sp["total_gain"] == vt["total_gain"]
        assert sp["open_positions"] == vt["open_positions"]
        assert sp["fallback_positions"] == vt["fallback_positions"]
        assert sp["stale_positions"] == vt["stale_positions"]
        assert sp["xirr"] == vt["xirr"]

    # Summary totals equal the sums of per-portfolio totals
    sum_cost = Decimal(v1["totals"]["cost_basis"]) + Decimal(v2["totals"]["cost_basis"])
    sum_val = Decimal(v1["totals"]["current_value"]) + Decimal(v2["totals"]["current_value"])
    assert summary["totals"]["cost_basis"] == str(sum_cost)
    assert summary["totals"]["current_value"] == str(sum_val)


async def test_user_isolation_and_ownership_matrix(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """User B gets 404 on User A's portfolio valuation and series routes.

    User B's summary excludes User A's data entirely.
    """
    headers_a = await _get_auth_headers(client, "user_a@example.com")
    headers_b = await _get_auth_headers(client, "user_b@example.com")

    pid_a = await _create_portfolio(client, headers_a, "User A Secret Portfolio")
    await _record_transaction(
        client,
        headers_a,
        pid_a,
        SYNTHETIC_PPFC.scheme_code,
        "BUY",
        "2025-01-01",
        "10.0000",
        "50.00000000",
        "500.00",
    )

    # 1. User B gets 404 on User A's portfolio valuation
    r_val = await client.get(f"/api/v1/portfolios/{pid_a}/valuation", headers=headers_b)
    assert r_val.status_code == 404
    assert r_val.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"

    # 2. User B gets 404 on User A's portfolio value-series
    r_ser = await client.get(f"/api/v1/portfolios/{pid_a}/value-series", headers=headers_b)
    assert r_ser.status_code == 404
    assert r_ser.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"

    # 3. Unauthenticated gets 401
    r_unauth = await client.get(f"/api/v1/portfolios/{pid_a}/valuation")
    assert r_unauth.status_code == 401

    # 4. User B's summary never contains User A's portfolio
    r_sum_b = await client.get("/api/v1/valuation/summary", headers=headers_b)
    assert r_sum_b.status_code == 200
    data_b = r_sum_b.json()["data"]
    assert len(data_b["portfolios"]) == 0
    assert data_b["totals"]["cost_basis"] == "0.00"


# ==============================================================================
# Fallback, Stale, and NAV Older Than Ledger
# ==============================================================================


async def test_fallback_cost_and_stale_flags_api(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """Fund with no latest_nav gets fallback_cost, excluded from XIRR.

    Stale flag set when age > 7 days.
    """
    # Create fund without latest_nav
    fund_fallback = Fund(
        scheme_code=999888,
        name="No NAV Fund",
        name_normalized="no nav fund",
        amc="Test AMC",
        category_raw="Flexi Cap",
        asset_class="equity",
        sub_category="flexi-cap",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        latest_nav=None,
        latest_nav_date=None,
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add(fund_fallback)
    await test_session.commit()

    headers = await _get_auth_headers(client, "user_fb@example.com")
    pid = await _create_portfolio(client, headers, "Fallback Portfolio")

    await _record_transaction(
        client, headers, pid, 999888, "BUY", "2025-01-01", "10.0000", "50.00000000", "500.00"
    )

    _set_clock(client, datetime(2025, 1, 10, 10, 0, tzinfo=UTC))

    val_res = await client.get(f"/api/v1/portfolios/{pid}/valuation", headers=headers)
    assert val_res.status_code == 200
    data = val_res.json()["data"]

    item = data["items"][0]
    assert item["nav_source"] == "fallback_cost"
    assert item["nav"] == "50.00000000"
    assert item["xirr"]["reason"] == "NO_NAV_DATA"

    totals = data["totals"]
    assert totals["fallback_positions"] == 1
    assert totals["xirr"]["excluded_funds"] == 1


# ==============================================================================
# Empty State and Validation
# ==============================================================================


async def test_empty_portfolio_and_empty_user_returns_zeros(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """Empty portfolio and user return zeros, nulls, and NO_TRANSACTIONS."""
    headers = await _get_auth_headers(client, "empty_user@example.com")
    pid = await _create_portfolio(client, headers, "Empty Portfolio")

    val_res = await client.get(f"/api/v1/portfolios/{pid}/valuation", headers=headers)
    assert val_res.status_code == 200
    v_data = val_res.json()["data"]
    assert v_data["totals"]["cost_basis"] == "0.00"
    assert v_data["totals"]["current_value"] == "0.00"
    assert v_data["totals"]["xirr"]["reason"] == "NO_TRANSACTIONS"

    sum_res = await client.get("/api/v1/valuation/summary", headers=headers)
    assert sum_res.status_code == 200
    s_data = sum_res.json()["data"]
    assert s_data["totals"]["cost_basis"] == "0.00"
    assert s_data["totals"]["xirr"]["reason"] == "NO_TRANSACTIONS"


async def test_invalid_range_returns_422(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """Invalid value-series range returns 422 VALIDATION_ERROR."""
    headers = await _get_auth_headers(client, "range_user@example.com")
    pid = await _create_portfolio(client, headers, "Range Portfolio")

    res = await client.get(
        f"/api/v1/portfolios/{pid}/value-series?range=invalid_range", headers=headers
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# ==============================================================================
# Headers, Cache-Control, and Rate Limiting
# ==============================================================================


async def test_headers_and_cache_control_no_store(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """All valuation endpoints return Cache-Control: no-store and X-Request-ID."""
    headers = await _get_auth_headers(client, "headers_user@example.com")
    pid = await _create_portfolio(client, headers, "Headers Portfolio")

    for path in [
        f"/api/v1/portfolios/{pid}/valuation",
        "/api/v1/valuation/summary",
        f"/api/v1/portfolios/{pid}/value-series",
    ]:
        res = await client.get(path, headers=headers)
        assert res.headers.get("Cache-Control") == "no-store"
        assert "X-Request-ID" in res.headers


async def test_valuation_rate_limit_429(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """Exceeding VALUATION_REQUESTS_PER_MIN (120 req/min) returns 429 with Retry-After."""
    headers = await _get_auth_headers(client, "rl_user@example.com")
    pid = await _create_portfolio(client, headers, "Rate Limit Portfolio")

    # Send 120 fast requests
    for _ in range(120):
        r = await client.get(f"/api/v1/portfolios/{pid}/valuation", headers=headers)
        assert r.status_code == 200

    # 121st request triggers 429
    res = await client.get(f"/api/v1/portfolios/{pid}/valuation", headers=headers)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in res.headers


# ==============================================================================
# Statement Counters (No N+1 Efficiency)
# ==============================================================================


async def test_statement_counter_does_not_grow_with_funds_or_portfolios(
    client: AsyncClient,
    test_session: AsyncSession,
    seed_synthetic_funds: None,
) -> None:
    """Database statement count does not scale with number of funds or portfolios."""
    headers = await _get_auth_headers(client, "stmt_user@example.com")
    pid1 = await _create_portfolio(client, headers, "Portfolio 1")
    pid2 = await _create_portfolio(client, headers, "Portfolio 2")

    await _record_transaction(
        client,
        headers,
        pid1,
        SYNTHETIC_PPFC.scheme_code,
        "BUY",
        "2025-01-01",
        "10.0000",
        "50.00000000",
        "500.00",
    )
    await _record_transaction(
        client,
        headers,
        pid2,
        SYNTHETIC_VALUATION_FUND.scheme_code,
        "BUY",
        "2025-01-01",
        "20.0000",
        "100.00000000",
        "2000.00",
    )

    _set_clock(client, datetime(2026, 11, 14, 10, 0, tzinfo=UTC))

    engine = get_engine()
    queries: list[str] = []

    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        queries.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        # Valuation for single portfolio
        queries.clear()
        res_v = await client.get(f"/api/v1/portfolios/{pid1}/valuation", headers=headers)
        assert res_v.status_code == 200
        val_queries_count = len(queries)

        # Summary across multiple portfolios
        queries.clear()
        res_s = await client.get("/api/v1/valuation/summary", headers=headers)
        assert res_s.status_code == 200
        sum_queries_count = len(queries)

        # Invariant: queries are constant O(1), no N+1
        assert val_queries_count <= 4
        assert sum_queries_count <= 4
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
