"""Integration tests for Transaction Ledger mutations and derived holdings."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fund import Fund
from app.services.ledger import compute_holdings
from app.services.transaction_service import TransactionService


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
    err_body = r_mismatch.json()["error"]
    assert err_body["code"] == "AMOUNT_MISMATCH"
    assert err_body["details"]["expected"] == "1000.00"
    assert err_body["details"]["given"] == "1005.00"


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

    # 2. Attempt to sell 15 units -> 409 INSUFFICIENT_UNITS with details.available_units
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
    assert r_sell.status_code == 409
    err = r_sell.json()["error"]
    assert err["code"] == "INSUFFICIENT_UNITS"
    assert err["details"]["available_units"] == "10.0000"


@pytest.mark.asyncio
async def test_worked_example_holdings_and_delete_guard(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """End-to-end worked example from spec:

    Buy 100 @ 50 (5000.00) on 2025-01-10
    Buy 50 @ 60 (3000.00) on 2025-02-10
    Sell 30 @ 70 (2100.00) on 2025-03-10

    Derived holding:
    units = 120.0000
    cost_basis = 6400.00
    avg_cost = 53.3333
    total_bought = 8000.00
    total_sold = 2100.00
    first_txn_date = 2025-01-10
    last_txn_date = 2025-03-10
    txn_count = 3
    is_closed = False
    """
    headers = await _get_auth_headers(client, "worked_example@example.com")
    fund = await _seed_test_fund(
        test_session,
        scheme_code=122639,
        latest_nav=Decimal("95.50000000"),
    )

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Main Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # 1. BUY 100 @ 50
    r1 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2025-01-10",
            "units": "100.0000",
            "nav": "50.00000000",
            "amount": "5000.00",
        },
        headers=headers,
    )
    assert r1.status_code == 201
    t1_id = r1.json()["data"]["id"]

    # 2. BUY 50 @ 60
    r2 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2025-02-10",
            "units": "50.0000",
            "nav": "60.00000000",
            "amount": "3000.00",
        },
        headers=headers,
    )
    assert r2.status_code == 201

    # 3. SELL 30 @ 70
    r3 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "SELL",
            "txn_date": "2025-03-10",
            "units": "30.0000",
            "nav": "70.00000000",
            "amount": "2100.00",
        },
        headers=headers,
    )
    assert r3.status_code == 201

    # 4. Check GET /holdings
    r_holdings = await client.get(f"/api/v1/portfolios/{p_id}/holdings", headers=headers)
    assert r_holdings.status_code == 200
    h_data = r_holdings.json()["data"]
    assert len(h_data["items"]) == 1
    h = h_data["items"][0]

    assert h["scheme_code"] == 122639
    assert h["units"] == "120.0000"
    assert h["avg_cost"] == "53.3333"
    assert h["cost_basis"] == "6400.00"
    assert h["total_bought"] == "8000.00"
    assert h["total_sold"] == "2100.00"
    assert h["first_txn_date"] == "2025-01-10"
    assert h["last_txn_date"] == "2025-03-10"
    assert h["txn_count"] == 3
    assert h["is_closed"] is False

    # Check embedded fund master metadata
    f = h["fund"]
    assert f["name"] == "Parag Parikh Flexi Cap Fund"
    assert f["amc"] == "PPFAS"
    assert f["asset_class"] == "equity"
    assert f["sub_category"] == "flexi-cap"
    assert f["plan_type"] == "direct"
    assert f["option_type"] == "growth"
    assert f["latest_nav"] == "95.50000000"
    assert f["latest_nav_date"] == "2026-11-06"

    assert h_data["totals"]["cost_basis"] == "6400.00"
    assert h_data["totals"]["open_positions"] == 1

    # 5. Check GET portfolio detail metrics
    r_detail = await client.get(f"/api/v1/portfolios/{p_id}", headers=headers)
    assert r_detail.status_code == 200
    detail = r_detail.json()["data"]
    assert detail["total_cost_basis"] == "6400.00"
    assert detail["open_positions"] == 1
    assert detail["total_transactions"] == 3

    # Add another SELL of 100 units on 2025-04-10 (leaving 20 units)
    r4 = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "SELL",
            "txn_date": "2025-04-10",
            "units": "100.0000",
            "nav": "72.00000000",
            "amount": "7200.00",
        },
        headers=headers,
    )
    assert r4.status_code == 201
    t4_id = r4.json()["data"]["id"]

    # 6. Deleting BUY 1 (100 units) leaves only 50 units bought, but 130 units sold!
    # Rejected with 409 LEDGER_INCONSISTENT because SELL would oversell
    r_del_buy1 = await client.delete(
        f"/api/v1/portfolios/{p_id}/transactions/{t1_id}",
        headers=headers,
    )
    assert r_del_buy1.status_code == 409
    assert r_del_buy1.json()["error"]["code"] == "LEDGER_INCONSISTENT"

    # 7. Deleting SELL succeeds
    r_del_sell = await client.delete(
        f"/api/v1/portfolios/{p_id}/transactions/{t4_id}",
        headers=headers,
    )
    assert r_del_sell.status_code == 200
    assert r_del_sell.json()["data"]["deleted"] is True


@pytest.mark.asyncio
async def test_get_and_patch_transaction(client: AsyncClient, test_session: AsyncSession) -> None:
    headers_a = await _get_auth_headers(client, "patch_user_a@example.com")
    headers_b = await _get_auth_headers(client, "patch_user_b@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=100007)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Patch Portfolio"},
        headers=headers_a,
    )
    p_id = r_port.json()["data"]["id"]

    # Add BUY 50 units
    r_add = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "50.0000",
            "nav": "100.00000000",
            "notes": "Initial purchase",
        },
        headers=headers_a,
    )
    t_id = r_add.json()["data"]["id"]

    # Add SELL 30 units
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "SELL",
            "txn_date": "2026-11-02",
            "units": "30.0000",
            "nav": "110.00000000",
        },
        headers=headers_a,
    )

    # 1. GET single transaction
    r_get = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions/{t_id}",
        headers=headers_a,
    )
    assert r_get.status_code == 200
    assert r_get.json()["data"]["notes"] == "Initial purchase"

    # 2. User B cannot GET single transaction -> 404
    r_get_b = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions/{t_id}",
        headers=headers_b,
    )
    assert r_get_b.status_code == 404

    # 3. PATCH notes only -> 200
    r_patch_notes = await client.patch(
        f"/api/v1/portfolios/{p_id}/transactions/{t_id}",
        json={"notes": "Updated notes"},
        headers=headers_a,
    )
    assert r_patch_notes.status_code == 200
    assert r_patch_notes.json()["data"]["notes"] == "Updated notes"

    # 4. PATCH units to 20 when 30 units are sold downstream -> 409 LEDGER_INCONSISTENT
    r_break = await client.patch(
        f"/api/v1/portfolios/{p_id}/transactions/{t_id}",
        json={"units": "20.0000", "nav": "100.00000000"},
        headers=headers_a,
    )
    assert r_break.status_code == 409
    assert r_break.json()["error"]["code"] == "LEDGER_INCONSISTENT"


@pytest.mark.asyncio
async def test_concurrent_transactions_acquire_lock_safely(
    test_session: AsyncSession,
    test_redis: Any,
) -> None:
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport

    from app.api.deps import get_db_session, get_redis_client
    from app.main import create_app
    from tests.conftest import _test_session_factory

    assert _test_session_factory is not None
    test_app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with _test_session_factory() as s:
            yield s

    test_app.dependency_overrides[get_db_session] = override_db
    test_app.dependency_overrides[get_redis_client] = lambda: test_redis
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

        # Buy 10 units first
        r_init = await concurrent_client.post(
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
        assert r_init.status_code == 201

        # Fire two concurrent SELL requests of 10 units each
        async def _attempt_sell(tag: str) -> int:
            res = await concurrent_client.post(
                f"/api/v1/portfolios/{p_id}/transactions",
                json={
                    "fund_id": str(fund.id),
                    "txn_type": "SELL",
                    "txn_date": "2026-11-02",
                    "units": "10.0000",
                    "nav": "105.00000000",
                    "notes": tag,
                },
                headers=headers,
            )
            return res.status_code

        statuses = await asyncio.gather(_attempt_sell("sell1"), _attempt_sell("sell2"))

        # Exactly one must succeed (201) and one must be rejected (409 INSUFFICIENT_UNITS)
        assert sorted(statuses) == [201, 409]

        # Final holdings must have units == 0.0000 and cost_basis == 0.00
        r_holdings = await concurrent_client.get(
            f"/api/v1/portfolios/{p_id}/holdings",
            headers=headers,
        )
        assert r_holdings.status_code == 200
        h_data = r_holdings.json()["data"]
        assert h_data["items"][0]["units"] == "0.0000"
        assert h_data["items"][0]["cost_basis"] == "0.00"
        assert h_data["items"][0]["is_closed"] is True


@pytest.mark.asyncio
async def test_count_open_positions_sql_matches_pure_function(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers = await _get_auth_headers(client, "sql_agg_user@example.com")
    f1 = await _seed_test_fund(test_session, scheme_code=100010, name="Fund 1")
    f2 = await _seed_test_fund(test_session, scheme_code=100011, name="Fund 2")

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "SQL Agg Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # F1: Buy 20, sell 10 -> open (10 remaining)
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(f1.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "20.0000",
            "nav": "10.00000000",
        },
        headers=headers,
    )
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(f1.id),
            "txn_type": "SELL",
            "txn_date": "2026-11-02",
            "units": "10.0000",
            "nav": "12.00000000",
        },
        headers=headers,
    )

    # F2: Buy 30, sell 30 -> closed (0 remaining)
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(f2.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "30.0000",
            "nav": "20.00000000",
        },
        headers=headers,
    )
    await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(f2.id),
            "txn_type": "SELL",
            "txn_date": "2026-11-02",
            "units": "30.0000",
            "nav": "25.00000000",
        },
        headers=headers,
    )

    from uuid import UUID

    sql_count = await TransactionService.count_open_positions_sql(test_session, UUID(p_id))
    assert sql_count == 1

    r_txns = await client.get(f"/api/v1/portfolios/{p_id}/transactions", headers=headers)
    txns = r_txns.json()["data"]["items"]

    from app.models.transaction import Transaction

    txns_models = [
        Transaction(
            fund_id=UUID(t["fund_id"]),
            txn_type=t["txn_type"],
            txn_date=date.fromisoformat(t["txn_date"]),
            units=Decimal(t["units"]),
            nav=Decimal(t["nav"]),
            amount=Decimal(t["amount"]),
            created_at=datetime.fromisoformat(t["created_at"]),
        )
        for t in txns
    ]
    pure_holdings = compute_holdings(txns_models)
    pure_open_count = sum(1 for h in pure_holdings.values() if not h.is_closed)
    assert sql_count == pure_open_count == 1


@pytest.mark.asyncio
async def test_holdings_query_count_no_n_plus_one(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """GET /portfolios/{id}/holdings must execute in a constant number of queries regardless of

    how many distinct funds are present in the portfolio (no N+1 SQL queries).
    """
    from sqlalchemy import event

    from app.core.db import get_engine

    headers = await _get_auth_headers(client, email="nplus1_user@example.com")

    # 1. Create a portfolio
    r_create = await client.post(
        "/api/v1/portfolios",
        json={"name": "N+1 Test Portfolio"},
        headers=headers,
    )
    assert r_create.status_code == 201
    p_id = r_create.json()["data"]["id"]

    # 2. Seed 4 distinct funds and add transactions for each
    funds = []
    for code in [70001, 70002, 70003, 70004]:
        f = await _seed_test_fund(
            test_session,
            scheme_code=code,
            name=f"Test Growth Fund {code}",
            latest_nav=Decimal("100.00000000"),
        )
        funds.append(f)
        r_txn = await client.post(
            f"/api/v1/portfolios/{p_id}/transactions",
            json={
                "fund_id": str(f.id),
                "txn_type": "buy",
                "txn_date": "2026-11-01",
                "units": "50.0000",
                "nav": "100.00000000",
                "amount": "5000.00",
            },
            headers=headers,
        )
        assert r_txn.status_code == 201

    # 3. Intercept and count executed SQL statements during GET /holdings
    statements: list[str] = []

    def before_cursor_execute(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        statements.append(statement)

    sync_engine = get_engine().sync_engine
    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        r_holdings = await client.get(f"/api/v1/portfolios/{p_id}/holdings", headers=headers)
        assert r_holdings.status_code == 200
        data = r_holdings.json()["data"]
        assert len(data["items"]) == 4

        # For 4 funds, N+1 would execute 1 (txns) + 4 (funds) = 5+ queries.
        # With joinedload(Transaction.fund), total SELECT queries is exactly 2:
        # 1: SELECT portfolio to check ownership
        # 2: SELECT transactions JOIN funds (single query for all transactions and funds)
        # Even counting auth user lookup if applicable, statements must remain strictly <= 3.
        select_statements = [s for s in statements if s.strip().upper().startswith("SELECT")]
        err_msg = (
            f"Expected <= 3 SELECT queries for 4 funds, but got "
            f"{len(select_statements)}: {select_statements}"
        )
        assert len(select_statements) <= 3, err_msg
    finally:
        event.remove(sync_engine, "before_cursor_execute", before_cursor_execute)
