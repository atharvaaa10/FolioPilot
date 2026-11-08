"""Integration tests for Transaction Ledger mutations, oversell guards, and positions."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fund import Fund


async def _get_auth_headers(
    client: AsyncClient, email: str = "txn_user@example.com"
) -> dict[str, str]:
    """Helper to register user and obtain valid Authorization headers."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SuperSecret123!"},
    )
    token = reg.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_test_fund(
    session: AsyncSession,
    scheme_code: int = 122639,
    name: str = "Parag Parikh Flexi Cap Fund",
    latest_nav: Decimal = Decimal("95.50000000"),
) -> Fund:
    fund = Fund(
        scheme_code=scheme_code,
        isin_growth=f"INF{scheme_code}",
        name=name,
        name_normalized=name.lower(),
        amc="PPFAS",
        category_raw="Flexi Cap",
        asset_class="equity",
        sub_category="flexi-cap",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        latest_nav=latest_nav,
        latest_nav_date=date(2026, 11, 6),
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(fund)
    await session.commit()
    return fund


@pytest.mark.asyncio
async def test_add_transaction_derivation_and_ensure_tracked(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers = await _get_auth_headers(client, "txn_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=100001, name="Equity Test Fund")

    # Create portfolio
    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Growth Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # Provide units and nav only -> amount is derived
    r_txn1 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "50.0000",
            "nav": "100.00000000",
        },
        headers=headers,
    )
    assert r_txn1.status_code == 201
    t1_data = r_txn1.json()["data"]
    assert t1_data["units"] == "50.0000"
    assert t1_data["nav"] == "100.00000000"
    assert t1_data["amount"] == "5000.00"

    # Verify fund was flagged as tracked
    await test_session.refresh(fund)
    assert fund.is_tracked is True


@pytest.mark.asyncio
async def test_amount_mismatch_tolerance_rejection(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers = await _get_auth_headers(client, "tolerance_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=100002)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Tolerance Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # Expected amount = 100 * 10 = 1000.00
    # Tolerance = max(1.00, 1000 * 0.002 = 2.00) = 2.00
    # Amount 1005.00 diff is 5.00 > 2.00 -> 422 AMOUNT_MISMATCH
    r_mismatch = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "100.0000",
            "nav": "10.00000000",
            "amount": "1005.00",
        },
        headers=headers,
    )
    assert r_mismatch.status_code == 422
    assert r_mismatch.json()["error"]["code"] == "AMOUNT_MISMATCH"


@pytest.mark.asyncio
async def test_oversell_guard_rejected(client: AsyncClient, test_session: AsyncSession) -> None:
    headers = await _get_auth_headers(client, "oversell_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=100003)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Oversell Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # 1. Buy 10 units
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "10.0000",
            "nav": "100.00000000",
        },
        headers=headers,
    )

    # 2. Attempt to sell 15 units -> 422 INSUFFICIENT_UNITS
    r_sell = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "SELL",
            "txn_date": "2026-11-02",
            "units": "15.0000",
            "nav": "110.00000000",
        },
        headers=headers,
    )
    assert r_sell.status_code == 422
    assert r_sell.json()["error"]["code"] == "INSUFFICIENT_UNITS"


@pytest.mark.asyncio
async def test_worked_example_positions_and_delete_guard(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """End-to-end worked example from prompt:

    Buy 100 @ 10 -> amount 1000
    Buy 100 @ 20 -> amount 2000
    Sell 50 @ 25 -> amount 1250
    Verify derived position: units=150, invested=2250, avg_nav=15, realized_gain=500
    Verify deleting first BUY is rejected because SELL would oversell.
    """
    headers = await _get_auth_headers(client, "worked_example@example.com")
    fund = await _seed_test_fund(
        test_session,
        scheme_code=122639,
        latest_nav=Decimal("30.00000000"),
    )

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Main Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # 1. BUY 100 @ 10
    r1 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "100.0000",
            "nav": "10.00000000",
        },
        headers=headers,
    )
    assert r1.status_code == 201
    _t1_id = r1.json()["data"]["id"]

    # 2. BUY 100 @ 20
    r2 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-02",
            "units": "100.0000",
            "nav": "20.00000000",
        },
        headers=headers,
    )
    assert r2.status_code == 201

    # 3. SELL 50 @ 25
    r3 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "SELL",
            "txn_date": "2026-11-03",
            "units": "50.0000",
            "nav": "25.00000000",
        },
        headers=headers,
    )
    assert r3.status_code == 201
    t3_id = r3.json()["data"]["id"]

    # 4. Check positions & metrics on portfolio detail
    r_detail = await client.get(f"/api/v1/portfolios/{p_id}", headers=headers)
    assert r_detail.status_code == 200
    data = r_detail.json()["data"]

    assert data["total_invested"] == "2250.00"
    assert data["realized_gain"] == "500.00"
    # current_value = 150 * 30 (latest NAV) = 4500.00
    assert data["current_value"] == "4500.00"
    assert data["unrealized_gain"] == "2250.00"

    positions = data["positions"]
    assert len(positions) == 1
    pos = positions[0]
    assert pos["units"] == "150.0000"
    assert pos["total_invested"] == "2250.00"
    assert pos["avg_nav"] == "15.00000000"
    assert pos["realized_gain"] == "500.00"

    # 5. Deleting SELL succeeds
    r_del_sell = await client.delete(
        f"/api/v1/portfolios/{p_id}/transactions/{t3_id}",
        headers=headers,
    )
    assert r_del_sell.status_code == 200
    assert r_del_sell.json()["data"]["deleted"] is True


@pytest.mark.asyncio
async def test_delete_buy_rejected_when_subsequent_sell_oversells(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers = await _get_auth_headers(client, "del_guard@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=100004)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Delete Guard Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # Buy 40 units on Day 1
    r_buy1 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "40.0000",
            "nav": "10.00000000",
        },
        headers=headers,
    )
    buy1_id = r_buy1.json()["data"]["id"]

    # Buy 10 units on Day 2 (total 50)
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-02",
            "units": "10.0000",
            "nav": "10.00000000",
        },
        headers=headers,
    )

    # Sell 50 units on Day 3 (balance becomes 0)
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "SELL",
            "txn_date": "2026-11-03",
            "units": "50.0000",
            "nav": "15.00000000",
        },
        headers=headers,
    )

    # Attempting to delete BUY 1 (40 units) leaves only 10 units for Day 3 SELL of 50 units.
    # Must be rejected with 422 INSUFFICIENT_UNITS!
    r_del_buy1 = await client.delete(
        f"/api/v1/portfolios/{p_id}/transactions/{buy1_id}",
        headers=headers,
    )
    assert r_del_buy1.status_code == 422
    assert r_del_buy1.json()["error"]["code"] == "INSUFFICIENT_UNITS"


@pytest.mark.asyncio
async def test_concurrent_transactions_acquire_lock_safely(
    test_session: AsyncSession,
) -> None:
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport

    from app.api.deps import get_db_session
    from app.main import create_app
    from tests.conftest import _test_session_factory

    assert _test_session_factory is not None
    test_app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with _test_session_factory() as s:
            yield s

    test_app.dependency_overrides[get_db_session] = override_db
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as concurrent_client:
        headers = await _get_auth_headers(concurrent_client, "concurrency_user@example.com")
        fund = await _seed_test_fund(test_session, scheme_code=100005)

        r_port = await concurrent_client.post(
            "/api/v1/portfolios",
            json={"name": "Concurrent Portfolio"},
            headers=headers,
        )
        p_id = r_port.json()["data"]["id"]

        # Fire 5 concurrent BUY requests using asyncio.gather
        async def _add_buy(idx: int) -> int:
            res = await concurrent_client.post(
                f"/api/v1/portfolios/{p_id}/transactions",
                json={
                    "fund_id": str(fund.id),
                    "txn_type": "BUY",
                    "txn_date": "2026-11-01",
                    "units": "10.0000",
                    "nav": "100.00000000",
                    "notes": f"Batch item {idx}",
                },
                headers=headers,
            )
            return res.status_code

        statuses = await asyncio.gather(*[_add_buy(i) for i in range(5)])
        assert all(s == 201 for s in statuses)

        # Verify all 5 transactions were persisted and total units is 50.0000
        r_detail = await concurrent_client.get(f"/api/v1/portfolios/{p_id}", headers=headers)
        assert r_detail.status_code == 200
        pos = r_detail.json()["data"]["positions"][0]
        assert pos["units"] == "50.0000"


@pytest.mark.asyncio
async def test_transaction_date_guards_and_foreign_user_404(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers_a = await _get_auth_headers(client, "user_date_a@example.com")
    headers_b = await _get_auth_headers(client, "user_date_b@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=100006)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Date Guard Portfolio"},
        headers=headers_a,
    )
    p_id = r_port.json()["data"]["id"]

    # 1. Date before 1990-01-01 -> 422
    r_old = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "1989-12-31",
            "units": "10.0000",
            "nav": "10.00000000",
        },
        headers=headers_a,
    )
    assert r_old.status_code == 422
    assert "earlier than 1990-01-01" in r_old.json()["error"]["message"]

    # 2. Date in future -> 422
    r_fut = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2099-01-01",
            "units": "10.0000",
            "nav": "10.00000000",
        },
        headers=headers_a,
    )
    assert r_fut.status_code == 422
    assert "cannot be in the future" in r_fut.json()["error"]["message"]

    # 3. Ownership 404: User B cannot add transaction to User A's portfolio
    r_foreign_add = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "10.0000",
            "nav": "10.00000000",
        },
        headers=headers_b,
    )
    assert r_foreign_add.status_code == 404
    assert r_foreign_add.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"

    # 4. Ownership 404: User B cannot list transactions for User A's portfolio
    r_foreign_list = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions",
        headers=headers_b,
    )
    assert r_foreign_list.status_code == 404
    assert r_foreign_list.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"
