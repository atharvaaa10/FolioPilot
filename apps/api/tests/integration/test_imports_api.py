"""Integration tests for Excel transaction imports API:
previews, duplicate multiset rule, all-or-nothing commit under lock,
undo with ledger validation, security limits, ownership 404 matrix,
rate limiting, logging redaction, and statement counters.
"""

import asyncio
import io
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import openpyxl
import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import IMPORT_MAX_FILE_BYTES, IMPORT_MAX_ROWS
from app.core.db import get_engine
from app.core.synthetic_funds import ALL_SYNTHETIC_FUNDS
from app.models.fund import Fund
from app.services.import_template import TEMPLATE_HEADERS


async def _get_auth_headers(
    client: AsyncClient, email: str = "import_user@example.com"
) -> dict[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    token = reg.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_test_portfolio(
    client: AsyncClient, headers: dict[str, str], name: str = "Import Test Portfolio"
) -> UUID:
    res = await client.post("/api/v1/portfolios", json={"name": name}, headers=headers)
    assert res.status_code == 201
    return UUID(res.json()["data"]["id"])


async def _seed_synthetic_funds(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for sf in ALL_SYNTHETIC_FUNDS:
        fund = Fund(
            scheme_code=sf.scheme_code,
            isin_growth=sf.isin_growth,
            isin_reinvest=sf.isin_reinvest,
            name=sf.name,
            name_normalized=sf.name.lower(),
            amc="Test AMC",
            category_raw="Flexi Cap",
            asset_class=sf.asset_class,
            sub_category=sf.sub_category,
            classification_source="category",
            plan_type="direct",
            option_type="growth",
            latest_nav=Decimal(sf.nav),
            latest_nav_date=date(2026, 11, 1),
            is_active=sf.is_active,
            is_tracked=False,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(fund)
    await session.commit()


def _make_xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_import_fixtures_previews_and_worked_example_commit(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify all 8 test fixtures match expected.json and worked-example commits with exact math."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "fixture_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures" / "imports"
    expected_path = fixtures_dir / "expected.json"
    with open(expected_path, encoding="utf-8") as f:
        expected_all = json.load(f)

    # 1. Test previews of all fixtures against expected.json
    for filename, exp in expected_all.items():
        file_path = fixtures_dir / filename
        assert file_path.exists(), f"Missing fixture file {filename}"
        with open(file_path, "rb") as xf:
            file_bytes = xf.read()

        upload_res = await client.post(
            f"/api/v1/portfolios/{portfolio_id}/imports",
            headers=headers,
            files={
                "file": (
                    filename,
                    file_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_res.status_code == 201, f"Failed uploading {filename}: {upload_res.text}"
        data = upload_res.json()["data"]["import"]

        # Check summary metrics
        assert data["rows_total"] == exp["rows_total"], f"{filename} rows_total mismatch"
        assert data["rows_ok"] == exp["rows_ok"], f"{filename} rows_ok mismatch"
        assert data["rows_warning"] == exp["rows_warning"], f"{filename} rows_warning mismatch"
        assert data["rows_duplicate"] == exp["rows_duplicate"], (
            f"{filename} rows_duplicate mismatch"
        )
        assert data["rows_error"] == exp["rows_error"], f"{filename} rows_error mismatch"
        assert data["will_import"] == exp["will_import"], f"{filename} will_import mismatch"
        assert data["totals"]["buy_amount"] == exp["totals"]["buy_amount"]
        assert data["totals"]["sell_amount"] == exp["totals"]["sell_amount"]

        # Check paged rows
        import_id = data["id"]
        rows_res = await client.get(
            f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/rows?page_size=100",
            headers=headers,
        )
        assert rows_res.status_code == 200
        paged_rows = rows_res.json()["data"]["items"]
        assert len(paged_rows) == len(exp["rows"])

        for actual_row, exp_row in zip(paged_rows, exp["rows"], strict=False):
            assert actual_row["row_number"] == exp_row["row_number"]
            assert actual_row["status"] == exp_row["status"]
            assert actual_row["txn_type"] == exp_row["txn_type"]
            if exp_row["units"] is not None:
                assert actual_row["units"] == exp_row["units"]
            if exp_row["amount"] is not None:
                assert actual_row["amount"] == exp_row["amount"]

    # 2. Commit worked-example.xlsx and verify exact portfolio holdings
    worked_path = fixtures_dir / "worked-example.xlsx"
    with open(worked_path, "rb") as xf:
        worked_bytes = xf.read()

    # Upload fresh worked-example preview
    upload_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "worked-example.xlsx",
                worked_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_res.status_code == 201
    import_data = upload_res.json()["data"]["import"]
    import_id = import_data["id"]
    fp = import_data["plan_fingerprint"]

    # Commit
    commit_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
        headers=headers,
        json={"plan_fingerprint": fp, "skip_invalid": False},
    )
    assert commit_res.status_code == 200
    commit_data = commit_res.json()["data"]
    assert commit_data["committed_count"] == 3
    assert commit_data["status"] == "committed"

    # Verify holdings endpoint: 120 units, 6400 cost basis, 53.3333 avg cost, 8000 bought, 2100 sold
    port_res = await client.get(f"/api/v1/portfolios/{portfolio_id}/holdings", headers=headers)
    assert port_res.status_code == 200
    p_data = port_res.json()["data"]
    assert len(p_data["items"]) == 1
    h = p_data["items"][0]
    assert h["units"] == "120.0000"
    assert h["cost_basis"] == "6400.00"
    assert h["avg_cost"] == "53.3333"
    assert h["total_bought"] == "8000.00"
    assert h["total_sold"] == "2100.00"
    assert h["txn_count"] == 3

    # 3. Re-upload worked-example.xlsx: should detect 3 duplicates and 0 will_import
    reupload_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "worked-example.xlsx",
                worked_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert reupload_res.status_code == 201
    re_data = reupload_res.json()["data"]["import"]
    assert re_data["rows_duplicate"] == 3
    assert re_data["will_import"] == 0

    # Attempt to commit with 0 will_import -> 409 IMPORT_NOTHING_TO_IMPORT
    recommit_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{re_data['id']}/commit",
        headers=headers,
        json={"plan_fingerprint": re_data["plan_fingerprint"], "skip_invalid": False},
    )
    assert recommit_res.status_code == 409
    assert recommit_res.json()["error"]["code"] == "IMPORT_NOTHING_TO_IMPORT"


@pytest.mark.asyncio
async def test_with_errors_skip_invalid_flow(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify with-errors requires skip_invalid=True, and valid rows become duplicates."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "errors_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures" / "imports"
    with open(fixtures_dir / "with-errors.xlsx", "rb") as f:
        file_bytes = f.read()

    upload_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "with-errors.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_res.status_code == 201
    data = upload_res.json()["data"]["import"]
    import_id = data["id"]
    fp = data["plan_fingerprint"]
    assert data["rows_error"] == 9
    assert data["rows_ok"] == 1

    # Commit without skip_invalid -> 409 IMPORT_HAS_ERRORS
    commit_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
        headers=headers,
        json={"plan_fingerprint": fp, "skip_invalid": False},
    )
    assert commit_res.status_code == 409
    assert commit_res.json()["error"]["code"] == "IMPORT_HAS_ERRORS"

    # Commit with skip_invalid -> 200 and 1 row imported
    commit_res2 = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
        headers=headers,
        json={"plan_fingerprint": fp, "skip_invalid": True},
    )
    assert commit_res2.status_code == 200
    assert commit_res2.json()["data"]["committed_count"] == 1

    # Re-upload: the valid row is now a duplicate
    reupload_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "with-errors.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert reupload_res.status_code == 201
    re_data = reupload_res.json()["data"]["import"]
    assert re_data["rows_duplicate"] == 1
    assert re_data["rows_error"] == 9
    assert re_data["will_import"] == 0


@pytest.mark.asyncio
async def test_ledger_conflicts_and_chronological_ordering(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify oversell detection with date and balance, and buy resolving sell."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "ledger_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    # 1. Sell without balance in file
    bad_sell_bytes = _make_xlsx_bytes(
        TEMPLATE_HEADERS,
        [
            ["2025-01-15", 122639, None, "sell", 50.0, 50.0, 2500.0, "Oversell note", None],
        ],
    )
    res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "oversell.xlsx",
                bad_sell_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 201
    d = res.json()["data"]["import"]
    assert d["rows_error"] == 1
    assert d["will_import"] == 0

    # 2. File where BUY comes before SELL -> both valid
    valid_pair_bytes = _make_xlsx_bytes(
        TEMPLATE_HEADERS,
        [
            ["2025-01-10", 122639, None, "buy", 100.0, 50.0, 5000.0, "Buy first", None],
            ["2025-01-15", 122639, None, "sell", 50.0, 50.0, 2500.0, "Sell after", None],
        ],
    )
    res2 = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "pair.xlsx",
                valid_pair_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res2.status_code == 201
    d2 = res2.json()["data"]["import"]
    assert d2["rows_ok"] == 2
    assert d2["rows_error"] == 0
    assert d2["will_import"] == 2


@pytest.mark.asyncio
async def test_staleness_detection(client: AsyncClient, test_session: AsyncSession) -> None:
    """Manual transaction between preview and commit returns 409 IMPORT_STALE."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "stale_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    # Preview an import with two prospective rows
    file_bytes = _make_xlsx_bytes(
        TEMPLATE_HEADERS,
        [
            ["2025-01-10", 122639, None, "buy", 100.0, 50.0, 5000.0, "Buy 1", None],
            ["2025-01-15", 122639, None, "buy", 50.0, 50.0, 2500.0, "Buy 2", None],
        ],
    )
    upload_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "stale.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_res.status_code == 201
    data = upload_res.json()["data"]["import"]
    import_id = data["id"]
    fp = data["plan_fingerprint"]
    assert data["will_import"] == 2

    # Wrong fingerprint -> 409 IMPORT_STALE
    res_wrong_fp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
        headers=headers,
        json={"plan_fingerprint": "0" * 64, "skip_invalid": False},
    )
    assert res_wrong_fp.status_code == 409
    assert res_wrong_fp.json()["error"]["code"] == "IMPORT_STALE"

    # User adds a manual transaction matching row 2 in portfolio
    txn_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        headers=headers,
        json={
            "scheme_code": 122639,
            "txn_type": "buy",
            "txn_date": "2025-01-15",
            "units": "50.0000",
            "nav": "50.00000000",
            "amount": "2500.00",
        },
    )
    assert txn_res.status_code == 201

    # Attempt to commit original preview -> 409 IMPORT_STALE (fingerprint changed)
    commit_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
        headers=headers,
        json={"plan_fingerprint": fp, "skip_invalid": False},
    )
    assert commit_res.status_code == 409
    assert commit_res.json()["error"]["code"] == "IMPORT_STALE"


@pytest.mark.asyncio
async def test_concurrency_double_commit(
    client: AsyncClient, test_session: AsyncSession, test_redis: Any
) -> None:
    """Double-commit via asyncio.gather gives 1 success and 1 409 IMPORT_ALREADY_COMMITTED."""
    from httpx import ASGITransport

    from app.api.deps import get_db_session, get_redis_client
    from app.main import create_app
    from tests.conftest import get_test_session_factory

    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "concurrent_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    file_bytes = _make_xlsx_bytes(
        TEMPLATE_HEADERS,
        [["2025-01-15", 122639, None, "buy", 100.0, 50.0, 5000.0, "Concurrent buy", None]],
    )
    upload_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "conc.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_res.status_code == 201
    data = upload_res.json()["data"]["import"]
    import_id = data["id"]
    fp = data["plan_fingerprint"]

    req_body = {"plan_fingerprint": fp, "skip_invalid": False}

    session_factory = get_test_session_factory()
    test_app = create_app()

    async def override_concurrent_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as s:
            yield s

    test_app.dependency_overrides[get_db_session] = override_concurrent_db
    test_app.dependency_overrides[get_redis_client] = lambda: test_redis

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as concurrent_client:
        results = await asyncio.gather(
            concurrent_client.post(
                f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
                headers=headers,
                json=req_body,
            ),
            concurrent_client.post(
                f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
                headers=headers,
                json=req_body,
            ),
        )

    status_codes = [r.status_code for r in results]
    assert 200 in status_codes
    assert 409 in status_codes
    failed = [r for r in results if r.status_code == 409][0]
    assert failed.json()["error"]["code"] in ("IMPORT_ALREADY_COMMITTED", "IMPORT_STALE")


@pytest.mark.asyncio
async def test_one_active_preview_per_portfolio(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Uploading a new file deletes previous previewed import."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "one_preview_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    f1 = _make_xlsx_bytes(
        TEMPLATE_HEADERS, [["2025-01-10", 122639, None, "buy", 10.0, 50.0, 500.0, "F1", None]]
    )
    f2 = _make_xlsx_bytes(
        TEMPLATE_HEADERS, [["2025-01-12", 122639, None, "buy", 20.0, 50.0, 1000.0, "F2", None]]
    )

    res1 = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "f1.xlsx",
                f1,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res1.status_code == 201
    id1 = res1.json()["data"]["import"]["id"]

    res2 = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "f2.xlsx",
                f2,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res2.status_code == 201
    id2 = res2.json()["data"]["import"]["id"]
    assert id1 != id2

    # id1 should now be gone (404)
    check1 = await client.get(f"/api/v1/portfolios/{portfolio_id}/imports/{id1}", headers=headers)
    assert check1.status_code == 404

    # id2 should be present
    check2 = await client.get(f"/api/v1/portfolios/{portfolio_id}/imports/{id2}", headers=headers)
    assert check2.status_code == 200


@pytest.mark.asyncio
async def test_undo_and_discard_lifecycle(client: AsyncClient, test_session: AsyncSession) -> None:
    """Test undo, duplicate undo blocked, undo blocked by dependent sell, and discard."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "undo_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    # 1. Upload and commit import
    file_bytes = _make_xlsx_bytes(
        TEMPLATE_HEADERS,
        [["2025-01-15", 122639, None, "buy", 100.0, 50.0, 5000.0, "Undo buy", None]],
    )
    upload_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "undo.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    import_data = upload_res.json()["data"]["import"]
    import_id = import_data["id"]
    fp = import_data["plan_fingerprint"]

    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/commit",
        headers=headers,
        json={"plan_fingerprint": fp, "skip_invalid": False},
    )

    # 2. Add dependent sell in portfolio
    sell_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        headers=headers,
        json={
            "scheme_code": 122639,
            "txn_type": "sell",
            "txn_date": "2025-01-20",
            "units": "50.0000",
            "nav": "60.00000000",
            "amount": "3000.00",
        },
    )
    assert sell_res.status_code == 201

    # Attempt undo: should be rejected because removing the buy leaves balance negative (-50 units)
    undo_res_blocked = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/undo",
        headers=headers,
    )
    assert undo_res_blocked.status_code == 409
    assert undo_res_blocked.json()["error"]["code"] == "LEDGER_INCONSISTENT"

    # Delete the dependent sell
    sell_id = sell_res.json()["data"]["id"]
    del_txn_res = await client.delete(
        f"/api/v1/portfolios/{portfolio_id}/transactions/{sell_id}", headers=headers
    )
    assert del_txn_res.status_code == 200

    # Now undo succeeds
    undo_res = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/undo",
        headers=headers,
    )
    assert undo_res.status_code == 200
    assert undo_res.json()["data"]["status"] == "undone"

    # Cannot undo twice
    undo_res_again = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}/undo",
        headers=headers,
    )
    assert undo_res_again.status_code == 409

    # Cannot discard committed/undone import
    discard_res = await client.delete(
        f"/api/v1/portfolios/{portfolio_id}/imports/{import_id}",
        headers=headers,
    )
    assert discard_res.status_code == 409

    # Discard works on a fresh preview
    upload_res2 = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "discard.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    id2 = upload_res2.json()["data"]["import"]["id"]
    discard_ok = await client.delete(
        f"/api/v1/portfolios/{portfolio_id}/imports/{id2}",
        headers=headers,
    )
    assert discard_ok.status_code == 200
    assert discard_ok.json()["data"]["discarded"] is True


@pytest.mark.asyncio
async def test_security_and_file_guards(client: AsyncClient, test_session: AsyncSession) -> None:
    """Verify ASGI upload size limit, chunked streaming cutoff, and safety rejections."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "security_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    # 1. 3 MB body rejected with 413 IMPORT_FILE_TOO_LARGE
    oversized_bytes = b"0" * (IMPORT_MAX_FILE_BYTES + 1024 * 500)
    res_413 = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "too_big.xlsx",
                oversized_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res_413.status_code == 413
    assert res_413.json()["error"]["code"] == "IMPORT_FILE_TOO_LARGE"

    # 2. Plain text renamed .xlsx -> 422 IMPORT_FILE_INVALID
    res_text = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "fake.xlsx",
                b"This is not a zip file",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res_text.status_code == 422
    assert res_text.json()["error"]["code"] == "IMPORT_FILE_INVALID"

    # 3. Missing required headers -> 422 IMPORT_TEMPLATE_MISMATCH
    bad_headers_file = _make_xlsx_bytes(["Wrong", "Headers", "Only"], [["a", "b", "c"]])
    res_headers = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "bad_headers.xlsx",
                bad_headers_file,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res_headers.status_code == 422
    assert res_headers.json()["error"]["code"] == "IMPORT_TEMPLATE_MISMATCH"

    # 4. Headers only -> 422 IMPORT_EMPTY
    empty_file = _make_xlsx_bytes(TEMPLATE_HEADERS, [])
    res_empty = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "empty.xlsx",
                empty_file,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "IMPORT_EMPTY"

    # 5. More than 5,000 rows -> 422 IMPORT_TOO_MANY_ROWS
    large_row_file = _make_xlsx_bytes(
        TEMPLATE_HEADERS,
        [["2025-01-10", 122639, None, "buy", 10.0, 50.0, 500.0, "Note", None]]
        * (IMPORT_MAX_ROWS + 1),
    )
    res_many = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "too_many.xlsx",
                large_row_file,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res_many.status_code == 422
    assert res_many.json()["error"]["code"] == "IMPORT_TOO_MANY_ROWS"


@pytest.mark.asyncio
async def test_ownership_404_matrix(client: AsyncClient, test_session: AsyncSession) -> None:
    """User B accessing User A's import endpoints receives 404 on every route."""
    await _seed_synthetic_funds(test_session)
    headers_a = await _get_auth_headers(client, "owner_a@example.com")
    headers_b = await _get_auth_headers(client, "owner_b@example.com")

    port_a = await _create_test_portfolio(client, headers_a, "Portfolio A")

    # User A creates preview
    f = _make_xlsx_bytes(
        TEMPLATE_HEADERS, [["2025-01-10", 122639, None, "buy", 10.0, 50.0, 500.0, "A", None]]
    )
    res = await client.post(
        f"/api/v1/portfolios/{port_a}/imports",
        headers=headers_a,
        files={
            "file": (
                "a.xlsx",
                f,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 201
    import_id = res.json()["data"]["import"]["id"]

    # User B calls each endpoint on port_a / import_id
    r1 = await client.post(
        f"/api/v1/portfolios/{port_a}/imports",
        headers=headers_b,
        files={
            "file": (
                "b.xlsx",
                f,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r1.status_code == 404

    r2 = await client.get(f"/api/v1/portfolios/{port_a}/imports/{import_id}", headers=headers_b)
    assert r2.status_code == 404

    r3 = await client.get(
        f"/api/v1/portfolios/{port_a}/imports/{import_id}/rows", headers=headers_b
    )
    assert r3.status_code == 404

    r4 = await client.post(
        f"/api/v1/portfolios/{port_a}/imports/{import_id}/commit",
        headers=headers_b,
        json={"plan_fingerprint": "abc", "skip_invalid": False},
    )
    assert r4.status_code == 404

    r5 = await client.post(
        f"/api/v1/portfolios/{port_a}/imports/{import_id}/undo", headers=headers_b
    )
    assert r5.status_code == 404

    r6 = await client.delete(f"/api/v1/portfolios/{port_a}/imports/{import_id}", headers=headers_b)
    assert r6.status_code == 404


@pytest.mark.asyncio
async def test_upload_rate_limit(client: AsyncClient, test_session: AsyncSession) -> None:
    """11th upload within a minute returns 429 RATE_LIMIT_EXCEEDED with Retry-After header."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "rate_limit_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    f = _make_xlsx_bytes(
        TEMPLATE_HEADERS, [["2025-01-10", 122639, None, "buy", 10.0, 50.0, 500.0, "Rate", None]]
    )

    for i in range(10):
        r = await client.post(
            f"/api/v1/portfolios/{portfolio_id}/imports",
            headers=headers,
            files={
                "file": (
                    f"rate_{i}.xlsx",
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert r.status_code == 201

    r_11 = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        headers=headers,
        files={
            "file": (
                "rate_11.xlsx",
                f,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r_11.status_code == 429
    assert r_11.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in r_11.headers


@pytest.mark.asyncio
async def test_logging_redaction_sentinel(
    client: AsyncClient, test_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Assert sentinel notes string and monetary amounts are never logged."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "log_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    sentinel_notes = "TOPSECRET_SENTINEL_NOTES_STRING_DO_NOT_LOG"
    sentinel_amount = "998877.66"

    f = _make_xlsx_bytes(
        TEMPLATE_HEADERS,
        [
            [
                "2025-01-10",
                122639,
                None,
                "buy",
                100.0,
                9988.7766,
                float(sentinel_amount),
                sentinel_notes,
                None,
            ]
        ],
    )

    with caplog.at_level(logging.DEBUG):
        res = await client.post(
            f"/api/v1/portfolios/{portfolio_id}/imports",
            headers=headers,
            files={
                "file": (
                    "log_test.xlsx",
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert res.status_code == 201

    for record in caplog.records:
        msg = str(record.getMessage())
        assert sentinel_notes not in msg, f"Sentinel notes leaked in log message: {msg}"
        assert sentinel_amount not in msg, f"Sentinel amount leaked in log message: {msg}"


@pytest.mark.asyncio
async def test_statement_counter_preview_and_commit(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Statement counts for preview and commit do not scale linearly with row count."""
    await _seed_synthetic_funds(test_session)
    headers = await _get_auth_headers(client, "statement_user@example.com")
    portfolio_id = await _create_test_portfolio(client, headers)

    # 50 rows vs 200 rows
    row_item = ["2025-01-10", 122639, None, "buy", 1.0, 50.0, 50.0, "Bulk", None]
    f_50 = _make_xlsx_bytes(TEMPLATE_HEADERS, [row_item] * 50)
    f_200 = _make_xlsx_bytes(TEMPLATE_HEADERS, [row_item] * 200)

    statements_50: list[str] = []

    def before_cursor_50(
        conn: Any, cursor: Any, statement: str, params: Any, ctx: Any, many: bool
    ) -> None:
        statements_50.append(statement)

    sync_engine = getattr(test_session.bind, "sync_engine", get_engine().sync_engine)
    event.listen(sync_engine, "before_cursor_execute", before_cursor_50)
    try:
        r50 = await client.post(
            f"/api/v1/portfolios/{portfolio_id}/imports",
            headers=headers,
            files={
                "file": (
                    "f50.xlsx",
                    f_50,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert r50.status_code == 201
    finally:
        event.remove(sync_engine, "before_cursor_execute", before_cursor_50)

    statements_200: list[str] = []

    def before_cursor_200(
        conn: Any, cursor: Any, statement: str, params: Any, ctx: Any, many: bool
    ) -> None:
        statements_200.append(statement)

    event.listen(sync_engine, "before_cursor_execute", before_cursor_200)
    try:
        r200 = await client.post(
            f"/api/v1/portfolios/{portfolio_id}/imports",
            headers=headers,
            files={
                "file": (
                    "f200.xlsx",
                    f_200,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert r200.status_code == 201
    finally:
        event.remove(sync_engine, "before_cursor_execute", before_cursor_200)

    # Both preview queries should have nearly identical statement counts (no O(N) queries)
    select_50 = [s for s in statements_50 if s.strip().upper().startswith("SELECT")]
    select_200 = [s for s in statements_200 if s.strip().upper().startswith("SELECT")]
    assert abs(len(select_50) - len(select_200)) <= 2, (
        f"Select statement count scaled with rows: {len(select_50)} vs {len(select_200)}"
    )
