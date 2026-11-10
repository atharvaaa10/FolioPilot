"""Integration tests for SIP endpoints, executor, transactions guard, and holdings."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_engine
from app.models.fund import Fund
from app.models.nav_history import NavHistory
from app.services.sip_executor import SipExecutor


async def _get_auth_headers(
    client: AsyncClient, email: str = "sip_user@example.com"
) -> dict[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SuperSecret123!"},
    )
    token = reg.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_test_fund(
    session: AsyncSession,
    scheme_code: int = 160001,
    name: str = "SIP Test Fund",
    latest_nav: Decimal = Decimal("100.00"),
    is_active: bool = True,
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
        latest_nav=latest_nav,
        latest_nav_date=date(2026, 11, 1),
        is_active=is_active,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(fund)
    await session.commit()
    return fund


async def _seed_nav(session: AsyncSession, fund_id: UUID, nav_date: date, nav: Decimal) -> None:
    history = NavHistory(
        fund_id=fund_id,
        nav_date=nav_date,
        nav=nav,
    )
    session.add(history)
    await session.commit()


@pytest.mark.asyncio
async def test_ownership_404_matrix(client: AsyncClient, test_session: AsyncSession) -> None:
    """User B gets 404 on all SIP and installment endpoints for User A's portfolio."""
    headers_a = await _get_auth_headers(client, "user_a@example.com")
    headers_b = await _get_auth_headers(client, "user_b@example.com")

    fund = await _seed_test_fund(test_session, scheme_code=160002)

    # User A creates portfolio and SIP
    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "User A Portfolio"},
        headers=headers_a,
    )
    p_a = r_port.json()["data"]["id"]

    r_sip = await client.post(
        f"/api/v1/portfolios/{p_a}/sips",
        json={
            "fund_id": str(fund.id),
            "amount": "5000.00",
            "day_of_month": 15,
            "start_date": "2026-06-01",
        },
        headers=headers_a,
    )
    assert r_sip.status_code == 201
    sip_id = r_sip.json()["data"]["id"]

    # Generate an installment for user A's SIP
    await SipExecutor.generate_due_installments(test_session, as_of=date(2026, 6, 20))
    inst_res = await client.get(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}/installments",
        headers=headers_a,
    )
    assert inst_res.status_code == 200
    inst_items = inst_res.json()["data"]["items"]
    assert len(inst_items) >= 1
    inst_id = inst_items[0]["id"]

    # User B tries every endpoint on User A's portfolio/SIP
    # 1. GET sips list
    r = await client.get(f"/api/v1/portfolios/{p_a}/sips", headers=headers_b)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"

    # 2. POST create sip
    r = await client.post(
        f"/api/v1/portfolios/{p_a}/sips",
        json={
            "fund_id": str(fund.id),
            "amount": "5000.00",
            "day_of_month": 15,
            "start_date": "2026-06-01",
        },
        headers=headers_b,
    )
    assert r.status_code == 404

    # 3. GET sip detail
    r = await client.get(f"/api/v1/portfolios/{p_a}/sips/{sip_id}", headers=headers_b)
    assert r.status_code == 404

    # 4. PATCH sip
    r = await client.patch(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}",
        json={"amount": "6000.00"},
        headers=headers_b,
    )
    assert r.status_code == 404

    # 5. POST pause sip
    r = await client.post(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}/pause",
        headers=headers_b,
    )
    assert r.status_code == 404

    # 6. POST resume sip
    r = await client.post(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}/resume",
        headers=headers_b,
    )
    assert r.status_code == 404

    # 7. POST end sip
    r = await client.post(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}/end",
        headers=headers_b,
    )
    assert r.status_code == 404

    # 8. GET installments
    r = await client.get(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}/installments",
        headers=headers_b,
    )
    assert r.status_code == 404

    # 9. POST skip installment
    r = await client.post(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}/installments/{inst_id}/skip",
        headers=headers_b,
    )
    assert r.status_code == 404

    # 10. DELETE sip
    r = await client.delete(
        f"/api/v1/portfolios/{p_a}/sips/{sip_id}",
        headers=headers_b,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_sip_create_validation_and_inactive_fund(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers = await _get_auth_headers(client, "validation_user@example.com")
    active_fund = await _seed_test_fund(test_session, scheme_code=160003, is_active=True)
    inactive_fund = await _seed_test_fund(test_session, scheme_code=160004, is_active=False)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Validation Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # 1. Day of month > 28 -> 422
    r = await client.post(
        f"/api/v1/portfolios/{p_id}/sips",
        json={
            "fund_id": str(active_fund.id),
            "amount": "1000.00",
            "day_of_month": 29,
            "start_date": "2026-06-01",
        },
        headers=headers,
    )
    assert r.status_code == 422

    # 2. Amount < 100 -> 422
    r = await client.post(
        f"/api/v1/portfolios/{p_id}/sips",
        json={
            "fund_id": str(active_fund.id),
            "amount": "50.00",
            "day_of_month": 15,
            "start_date": "2026-06-01",
        },
        headers=headers,
    )
    assert r.status_code == 422

    # 3. End date < start date -> 422
    r = await client.post(
        f"/api/v1/portfolios/{p_id}/sips",
        json={
            "fund_id": str(active_fund.id),
            "amount": "1000.00",
            "day_of_month": 15,
            "start_date": "2026-06-01",
            "end_date": "2026-05-01",
        },
        headers=headers,
    )
    assert r.status_code == 422

    # 4. Inactive fund -> FUND_INACTIVE 409
    r = await client.post(
        f"/api/v1/portfolios/{p_id}/sips",
        json={
            "fund_id": str(inactive_fund.id),
            "amount": "1000.00",
            "day_of_month": 15,
            "start_date": "2026-06-01",
        },
        headers=headers,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "FUND_INACTIVE"


@pytest.mark.asyncio
async def test_sip_worked_example_end_to_end(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """End-to-end worked example matching prompt values exactly:
    - 6 installments: 2026-05-10 to 2026-10-10
    - NAVs on trading days: 55.40, 58.10, 57.80, 61.20, 62.50, 64.04
    - Executed units: 502.5941
    - Total cost: 30000.00
    - Avg cost: 59.6903
    """
    headers = await _get_auth_headers(client, "worked_example_user@example.com")
    fund = await _seed_test_fund(
        test_session,
        scheme_code=160005,
        name="Worked Example Fund",
        latest_nav=Decimal("70.00"),
    )

    # Seed NAV history per spec worked example:
    # 2025-01-10 50.0000; 2025-02-10 55.0000; 2025-03-10 60.0000;
    # 2025-04-10 62.5000; 2025-05-12 65.0000; 2025-06-10 70.0000
    nav_points = [
        (date(2025, 1, 10), Decimal("50.0000")),
        (date(2025, 2, 10), Decimal("55.0000")),
        (date(2025, 3, 10), Decimal("60.0000")),
        (date(2025, 4, 10), Decimal("62.5000")),
        (date(2025, 5, 12), Decimal("65.0000")),
        (date(2025, 6, 10), Decimal("70.0000")),
    ]
    for d, n in nav_points:
        await _seed_nav(test_session, fund.id, d, n)

    # Create portfolio
    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Worked Example Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # Preview schedule first
    r_preview = await client.post(
        f"/api/v1/portfolios/{p_id}/sips/preview",
        json={
            "fund_id": str(fund.id),
            "amount": "5000.00",
            "day_of_month": 10,
            "start_date": "2025-01-05",
            "end_date": "2025-06-20",
        },
        headers=headers,
    )
    assert r_preview.status_code == 200
    preview_items = r_preview.json()["data"]["items"]
    assert len(preview_items) == 6
    assert [item["due_date"] for item in preview_items] == [
        "2025-01-10",
        "2025-02-10",
        "2025-03-10",
        "2025-04-10",
        "2025-05-10",
        "2025-06-10",
    ]

    # Set clock to 2025-06-20 per spec worked example
    from app.api.deps import get_clock

    app_instance = getattr(client._transport, "app", None)
    if app_instance is not None:
        app_instance.dependency_overrides[get_clock] = lambda: datetime(
            2025, 6, 20, 12, 0, tzinfo=UTC
        )

    try:
        # Create SIP
        r_sip = await client.post(
            f"/api/v1/portfolios/{p_id}/sips",
            json={
                "fund_id": str(fund.id),
                "amount": "5000.00",
                "day_of_month": 10,
                "start_date": "2025-01-05",
                "step_up_percent": "10.00",
            },
            headers=headers,
        )
        assert r_sip.status_code == 201
        sip_id = r_sip.json()["data"]["id"]

        # Execute installments via executor as of 2025-06-20
        from tests.conftest import get_test_session_factory

        sf = get_test_session_factory()
        await SipExecutor.generate_due_installments(sf, as_of=date(2025, 6, 20))
        executed_stats = await SipExecutor.execute_pending(sf, as_of=date(2025, 6, 20))
        assert executed_stats["executed"] == 6

        # Verify installments state via API
        r_inst = await client.get(
            f"/api/v1/portfolios/{p_id}/sips/{sip_id}/installments",
            headers=headers,
        )
        assert r_inst.status_code == 200
        insts = r_inst.json()["data"]["items"]
        assert len(insts) == 6
        for inst in insts:
            assert inst["status"] == "executed"
            assert inst.get("transaction") is not None
            assert inst["transaction"]["nav"] is not None
            assert inst["transaction"]["units"] is not None

        # Check holdings endpoint
        r_holdings = await client.get(
            f"/api/v1/portfolios/{p_id}/holdings",
            headers=headers,
        )
        assert r_holdings.status_code == 200
        holdings_data = r_holdings.json()["data"]["items"]
        assert len(holdings_data) == 1
        h = holdings_data[0]

        assert Decimal(h["units"]) == Decimal("502.5941")
        assert Decimal(h["cost_basis"]) == Decimal("30000.00")
        assert Decimal(h["avg_cost"]) == Decimal("59.6903")
        assert h["txn_count"] == 6
    finally:
        if app_instance is not None:
            app_instance.dependency_overrides.pop(get_clock, None)

    # Verify transactions list has sip_installment_id populated
    r_txns = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions",
        headers=headers,
    )
    assert r_txns.status_code == 200
    txns = r_txns.json()["data"]["items"]
    assert len(txns) == 6
    for txn in txns:
        assert txn["sip_installment_id"] is not None
        assert txn["txn_type"].lower() == "buy"


@pytest.mark.asyncio
async def test_managed_transaction_protection_and_skip(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Managed transactions cannot be modified or deleted directly.
    Skipping an executed installment deletes the transaction.
    Skipping fails with LEDGER_INCONSISTENT if downstream sell exists.
    """
    headers = await _get_auth_headers(client, "managed_txn_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=160006)
    await _seed_nav(test_session, fund.id, date(2026, 5, 10), Decimal("100.00"))

    # Create portfolio and SIP
    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Managed Txn Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    r_sip = await client.post(
        f"/api/v1/portfolios/{p_id}/sips",
        json={
            "fund_id": str(fund.id),
            "amount": "5000.00",
            "day_of_month": 10,
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
        },
        headers=headers,
    )
    sip_id = r_sip.json()["data"]["id"]

    await SipExecutor.generate_due_installments(test_session, as_of=date(2026, 5, 10))
    await SipExecutor.execute_pending(test_session, as_of=date(2026, 5, 10))

    # Fetch transaction
    r_txns = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions",
        headers=headers,
    )
    txn = r_txns.json()["data"]["items"][0]
    txn_id = txn["id"]
    assert txn["sip_installment_id"] is not None

    # 1. Try to PATCH managed transaction -> 409 TRANSACTION_MANAGED_BY_SIP
    r_patch = await client.patch(
        f"/api/v1/portfolios/{p_id}/transactions/{txn_id}",
        json={"units": "100.0000"},
        headers=headers,
    )
    assert r_patch.status_code == 409
    assert r_patch.json()["error"]["code"] == "TRANSACTION_MANAGED_BY_SIP"

    # 2. Try to DELETE managed transaction -> 409 TRANSACTION_MANAGED_BY_SIP
    r_del = await client.delete(
        f"/api/v1/portfolios/{p_id}/transactions/{txn_id}",
        headers=headers,
    )
    assert r_del.status_code == 409
    assert r_del.json()["error"]["code"] == "TRANSACTION_MANAGED_BY_SIP"

    # 3. Add a manual SELL transaction that sells all units (50 units)
    r_sell = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "SELL",
            "txn_date": "2026-05-15",
            "units": "50.0000",
            "nav": "110.00000000",
        },
        headers=headers,
    )
    assert r_sell.status_code == 201

    # Fetch installment id
    r_inst = await client.get(
        f"/api/v1/portfolios/{p_id}/sips/{sip_id}/installments",
        headers=headers,
    )
    inst_id = r_inst.json()["data"]["items"][0]["id"]

    # 4. Try to skip the executed installment -> fails because SELL relies on it
    r_skip_fail = await client.post(
        f"/api/v1/portfolios/{p_id}/sips/{sip_id}/installments/{inst_id}/skip",
        headers=headers,
    )
    assert r_skip_fail.status_code == 409
    assert r_skip_fail.json()["error"]["code"] == "LEDGER_INCONSISTENT"

    # 5. Delete the SELL transaction
    sell_id = r_sell.json()["data"]["id"]
    r_del_sell = await client.delete(
        f"/api/v1/portfolios/{p_id}/transactions/{sell_id}",
        headers=headers,
    )
    assert r_del_sell.status_code == 200

    # 6. Now skip the installment -> succeeds, removes BUY transaction
    r_skip_ok = await client.post(
        f"/api/v1/portfolios/{p_id}/sips/{sip_id}/installments/{inst_id}/skip",
        headers=headers,
    )
    assert r_skip_ok.status_code == 200
    assert r_skip_ok.json()["data"]["status"] == "skipped"

    # Verify transaction is gone
    r_txns_after = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions",
        headers=headers,
    )
    assert len(r_txns_after.json()["data"]["items"]) == 0


@pytest.mark.asyncio
async def test_idempotent_execution_and_concurrent_skip(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers = await _get_auth_headers(client, "concurrency_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=160007)
    await _seed_nav(test_session, fund.id, date(2026, 5, 10), Decimal("50.00"))

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Concurrency Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    r_sip = await client.post(
        f"/api/v1/portfolios/{p_id}/sips",
        json={
            "fund_id": str(fund.id),
            "amount": "2000.00",
            "day_of_month": 10,
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
        },
        headers=headers,
    )
    sip_id = r_sip.json()["data"]["id"]

    await SipExecutor.generate_due_installments(test_session, as_of=date(2026, 5, 10))

    # 1. Concurrent executor runs: run execute_pending twice
    # Both running should produce exactly 1 transaction
    from tests.conftest import get_test_session_factory

    sf = get_test_session_factory()
    res1, res2 = await asyncio.gather(
        SipExecutor.execute_pending(sf, as_of=date(2026, 5, 10)),
        SipExecutor.execute_pending(sf, as_of=date(2026, 5, 10)),
    )
    assert res1["executed"] + res2["executed"] == 1  # Exactly one executed

    # Check transactions count is 1
    r_txns = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions",
        headers=headers,
    )
    assert len(r_txns.json()["data"]["items"]) == 1

    # Fetch installment
    r_inst = await client.get(
        f"/api/v1/portfolios/{p_id}/sips/{sip_id}/installments",
        headers=headers,
    )
    inst_id = r_inst.json()["data"]["items"][0]["id"]

    # 2. Concurrent skips: Two concurrent requests to skip same installment
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport
    from httpx import AsyncClient as HttpxAsyncClient

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

    async with HttpxAsyncClient(transport=transport, base_url="http://test") as concurrent_client:
        r1, r2 = await asyncio.gather(
            concurrent_client.post(
                f"/api/v1/portfolios/{p_id}/sips/{sip_id}/installments/{inst_id}/skip",
                headers=headers,
            ),
            concurrent_client.post(
                f"/api/v1/portfolios/{p_id}/sips/{sip_id}/installments/{inst_id}/skip",
                headers=headers,
            ),
        )
    statuses = {r1.status_code, r2.status_code}
    assert 200 in statuses
    assert 409 in statuses  # The other got INSTALLMENT_NOT_SKIPPABLE


@pytest.mark.asyncio
async def test_delete_sip_keeps_transactions_with_null_installment_id(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    headers = await _get_auth_headers(client, "del_sip_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=160008)
    await _seed_nav(test_session, fund.id, date(2026, 5, 10), Decimal("100.00"))

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "Del Sip Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    r_sip = await client.post(
        f"/api/v1/portfolios/{p_id}/sips",
        json={
            "fund_id": str(fund.id),
            "amount": "5000.00",
            "day_of_month": 10,
            "start_date": "2026-05-10",
            "end_date": "2026-05-10",
        },
        headers=headers,
    )
    sip_id = r_sip.json()["data"]["id"]

    from tests.conftest import get_test_session_factory

    sf = get_test_session_factory()
    await SipExecutor.generate_due_installments(sf, as_of=date(2026, 5, 10))
    await SipExecutor.execute_pending(sf, as_of=date(2026, 5, 10))

    # Delete the SIP
    r_del = await client.delete(
        f"/api/v1/portfolios/{p_id}/sips/{sip_id}",
        headers=headers,
    )
    assert r_del.status_code == 200

    # Verify transaction still exists and now has sip_installment_id = None
    r_txns = await client.get(
        f"/api/v1/portfolios/{p_id}/transactions",
        headers=headers,
    )
    items = r_txns.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["sip_installment_id"] is None


@pytest.mark.asyncio
async def test_sips_query_count_no_n_plus_one(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify listing SIPs does not execute N+1 queries for stats or funds."""
    headers = await _get_auth_headers(client, "n_plus_one_user@example.com")
    fund = await _seed_test_fund(test_session, scheme_code=160009)

    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": "N+1 Test Portfolio"},
        headers=headers,
    )
    p_id = r_port.json()["data"]["id"]

    # Create 4 SIPs
    for day in [5, 10, 15, 20]:
        r = await client.post(
            f"/api/v1/portfolios/{p_id}/sips",
            json={
                "fund_id": str(fund.id),
                "amount": "1000.00",
                "day_of_month": day,
                "start_date": "2026-01-01",
            },
            headers=headers,
        )
        assert r.status_code == 201

    statements: list[str] = []

    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    sync_engine = getattr(test_session.bind, "sync_engine", get_engine().sync_engine)
    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        r_list = await client.get(f"/api/v1/portfolios/{p_id}/sips", headers=headers)
        assert r_list.status_code == 200
        items = r_list.json()["data"]["items"]
        assert len(items) == 4

        # For 4 SIPs:
        # 1. SELECT users (auth)
        # 2. SELECT portfolios (ownership)
        # 3. SELECT portfolio_targets (portfolio relation)
        # 4. SELECT sips (batch list)
        # 5. SELECT sip_pauses (batch selectinload)
        # 6. SELECT funds (batch selectinload)
        # 7. SELECT aggregated stats from sip_installments GROUP BY sip_id
        # Total SELECT queries is constant (7 <= 8) regardless of SIP count (no N+1)
        select_statements = [s for s in statements if s.strip().upper().startswith("SELECT")]
        assert len(select_statements) <= 8, (
            f"Expected <= 8 SELECT queries, got {len(select_statements)}: {select_statements}"
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", before_cursor_execute)
