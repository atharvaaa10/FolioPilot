"""Integration tests for Portfolio management, limits, ownership 404s, and target allocations."""

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PORTFOLIOS_PER_USER
from app.models.fund import Fund


async def _get_auth_headers(
    client: AsyncClient, email: str = "portfolio_user@example.com"
) -> dict[str, str]:
    """Helper to register user and obtain valid Authorization headers."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SuperSecret123!"},
    )
    token = reg.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_portfolio_lifecycle_and_ownership_404(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    # 1. Setup User A and User B
    headers_a = await _get_auth_headers(client, "user_a@example.com")
    headers_b = await _get_auth_headers(client, "user_b@example.com")

    # 2. User A creates portfolio
    resp_create = await client.post(
        "/api/v1/portfolios",
        json={"name": "Retirement Corpus", "description": "Long-term goal"},
        headers=headers_a,
    )
    assert resp_create.status_code == 201
    p_data = resp_create.json()["data"]
    p_id = p_data["id"]
    assert p_data["name"] == "Retirement Corpus"
    assert p_data["description"] == "Long-term goal"

    # 3. User A lists portfolios
    resp_list = await client.get("/api/v1/portfolios", headers=headers_a)
    assert resp_list.status_code == 200
    items = resp_list.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == p_id

    # 4. User B cannot see User A's portfolio in list
    resp_list_b = await client.get("/api/v1/portfolios", headers=headers_b)
    assert resp_list_b.status_code == 200
    assert len(resp_list_b.json()["data"]) == 0

    # 5. Ownership 404 rule: User B requests User A's portfolio by ID -> MUST return 404 (never 403)
    resp_detail_b = await client.get(f"/api/v1/portfolios/{p_id}", headers=headers_b)
    assert resp_detail_b.status_code == 404
    assert resp_detail_b.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"

    # 6. User B can create portfolio with identical name
    resp_create_b = await client.post(
        "/api/v1/portfolios",
        json={"name": "Retirement Corpus"},
        headers=headers_b,
    )
    assert resp_create_b.status_code == 201

    # 7. User A duplicate name rejected with 409 PORTFOLIO_NAME_TAKEN (case-insensitive)
    resp_dup = await client.post(
        "/api/v1/portfolios",
        json={"name": "retirement corpus"},
        headers=headers_a,
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["error"]["code"] == "PORTFOLIO_NAME_TAKEN"

    # 8. User A updates portfolio
    resp_patch = await client.patch(
        f"/api/v1/portfolios/{p_id}",
        json={"name": "Retirement Fund 2050", "description": "Updated"},
        headers=headers_a,
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["data"]["name"] == "Retirement Fund 2050"

    # 9. User A deletes portfolio
    resp_del = await client.delete(f"/api/v1/portfolios/{p_id}", headers=headers_a)
    assert resp_del.status_code == 200
    assert resp_del.json()["data"]["deleted"] is True

    # 10. Portfolio is gone
    resp_get_deleted = await client.get(f"/api/v1/portfolios/{p_id}", headers=headers_a)
    assert resp_get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_portfolio_limit_enforced(client: AsyncClient, test_session: AsyncSession) -> None:
    headers = await _get_auth_headers(client, "max_portfolios@example.com")

    # Create up to MAX_PORTFOLIOS_PER_USER (20)
    for i in range(MAX_PORTFOLIOS_PER_USER):
        r = await client.post(
            "/api/v1/portfolios",
            json={"name": f"Portfolio {i + 1}"},
            headers=headers,
        )
        assert r.status_code == 201

    # Attempting to create the 21st portfolio fails with 409 PORTFOLIO_LIMIT_REACHED
    r_exceed = await client.post(
        "/api/v1/portfolios",
        json={"name": "One Too Many"},
        headers=headers,
    )
    assert r_exceed.status_code == 409
    assert r_exceed.json()["error"]["code"] == "PORTFOLIO_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_target_allocations_api(client: AsyncClient, test_session: AsyncSession) -> None:
    headers_a = await _get_auth_headers(client, "targets_a@example.com")
    headers_b = await _get_auth_headers(client, "targets_b@example.com")

    # Create portfolio
    r_create = await client.post(
        "/api/v1/portfolios",
        json={"name": "Asset Allocation Portfolio"},
        headers=headers_a,
    )
    p_id = r_create.json()["data"]["id"]

    # 1. Valid targets: 60 equity, 30 debt, 10 gold -> 200
    r_targets = await client.put(
        f"/api/v1/portfolios/{p_id}/targets",
        json={
            "targets": [
                {"asset_class": "equity", "target_pct": "60.00"},
                {"asset_class": "debt", "target_pct": "30.00"},
                {"asset_class": "gold", "target_pct": "10.00"},
            ]
        },
        headers=headers_a,
    )
    assert r_targets.status_code == 200
    targets = r_targets.json()["data"]
    assert len(targets) == 3

    # Check targets appear in portfolio detail
    r_detail = await client.get(f"/api/v1/portfolios/{p_id}", headers=headers_a)
    assert r_detail.status_code == 200
    detail_targets = r_detail.json()["data"]["targets"]
    assert len(detail_targets) == 3

    # 2. Invalid sum: 33.33 + 33.33 + 33.33 = 99.99 -> 422 TARGETS_INVALID (details.sum = 99.99)
    r_invalid_sum = await client.put(
        f"/api/v1/portfolios/{p_id}/targets",
        json={
            "targets": [
                {"asset_class": "equity", "target_pct": "33.33"},
                {"asset_class": "debt", "target_pct": "33.33"},
                {"asset_class": "gold", "target_pct": "33.33"},
            ]
        },
        headers=headers_a,
    )
    assert r_invalid_sum.status_code == 422
    err_body = r_invalid_sum.json()["error"]
    assert err_body["code"] == "TARGETS_INVALID"
    assert err_body["details"]["sum"] == "99.99"

    # 3. Ownership check: User B cannot set targets on User A's portfolio -> 404
    r_foreign = await client.put(
        f"/api/v1/portfolios/{p_id}/targets",
        json={"targets": []},
        headers=headers_b,
    )
    assert r_foreign.status_code == 404
    assert r_foreign.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"

    # 4. Empty targets is valid (unallocated)
    r_clear = await client.put(
        f"/api/v1/portfolios/{p_id}/targets",
        json={"targets": []},
        headers=headers_a,
    )
    assert r_clear.status_code == 200
    assert len(r_clear.json()["data"]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,endpoint_template,json_body",
    [
        ("GET", "/api/v1/portfolios/{portfolio_id}", None),
        ("PATCH", "/api/v1/portfolios/{portfolio_id}", {"name": "Hacked Name"}),
        ("DELETE", "/api/v1/portfolios/{portfolio_id}", None),
        ("PUT", "/api/v1/portfolios/{portfolio_id}/targets", {"targets": []}),
        ("GET", "/api/v1/portfolios/{portfolio_id}/transactions", None),
        (
            "POST",
            "/api/v1/portfolios/{portfolio_id}/transactions",
            {
                "scheme_code": 100099,
                "txn_type": "BUY",
                "txn_date": "2026-11-01",
                "units": "10.0000",
                "nav": "100.00000000",
            },
        ),
        ("GET", "/api/v1/portfolios/{portfolio_id}/transactions/{txn_id}", None),
        (
            "PATCH",
            "/api/v1/portfolios/{portfolio_id}/transactions/{txn_id}",
            {"notes": "Malicious update"},
        ),
        ("DELETE", "/api/v1/portfolios/{portfolio_id}/transactions/{txn_id}", None),
        ("GET", "/api/v1/portfolios/{portfolio_id}/holdings", None),
    ],
)
async def test_ownership_matrix_404(
    client: AsyncClient,
    test_session: AsyncSession,
    method: str,
    endpoint_template: str,
    json_body: dict[str, Any] | None,
) -> None:
    """Parametrized Ownership Matrix: User B receives 404 on every route of User A."""
    h_suffix = abs(hash(method + endpoint_template))
    headers_a = await _get_auth_headers(client, f"owner_matrix_a_{h_suffix}@example.com")
    headers_b = await _get_auth_headers(client, f"owner_matrix_b_{h_suffix}@example.com")

    # Seed fund for transaction endpoints
    s_code = 100000 + (h_suffix % 800000)
    fund = Fund(
        scheme_code=s_code,
        isin_growth=f"INF{s_code}",
        name=f"Ownership Test Fund {s_code}",
        name_normalized=f"ownership test fund {s_code}",
        amc="Test AMC",
        category_raw="Equity",
        asset_class="equity",
        sub_category="flexi-cap",
        classification_source="category",
        plan_type="direct",
        option_type="growth",
        latest_nav=100.0,
        is_active=True,
        is_tracked=False,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    test_session.add(fund)
    await test_session.commit()

    # User A creates portfolio
    r_port = await client.post(
        "/api/v1/portfolios",
        json={"name": f"Owner A Portfolio {s_code}"},
        headers=headers_a,
    )
    p_id = r_port.json()["data"]["id"]

    # User A creates a transaction
    r_txn = await client.post(
        f"/api/v1/portfolios/{p_id}/transactions",
        json={
            "fund_id": str(fund.id),
            "txn_type": "BUY",
            "txn_date": "2026-11-01",
            "units": "10.0000",
            "nav": "100.00000000",
        },
        headers=headers_a,
    )
    t_id = r_txn.json()["data"]["id"]

    url = endpoint_template.format(portfolio_id=p_id, txn_id=t_id)

    # In POST transactions, update scheme_code in payload if present
    req_json = dict(json_body) if json_body is not None else None
    if req_json and "scheme_code" in req_json:
        req_json["scheme_code"] = s_code

    # User B calls User A's resource
    response = await client.request(
        method=method,
        url=url,
        json=req_json,
        headers=headers_b,
    )

    # Must be 404, never 401/403/500
    assert response.status_code == 404
    error_code = response.json()["error"]["code"]
    assert error_code in ("PORTFOLIO_NOT_FOUND", "TRANSACTION_NOT_FOUND")
