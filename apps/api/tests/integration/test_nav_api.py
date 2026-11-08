"""Integration tests for /api/v1/nav/status endpoint."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_run import NavSyncRun


async def _get_auth_headers(
    client: AsyncClient, email: str = "nav_status_user@example.com"
) -> dict[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    token = reg.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_nav_status_when_no_runs_exist(client: AsyncClient) -> None:
    headers = await _get_auth_headers(client, "fresh_user1@example.com")
    res = await client.get("/api/v1/nav/status", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["last_run_time"] is None
    assert data["last_run_status"] is None
    assert data["last_success_time"] is None
    assert data["schemes_parsed"] == 0
    assert data["is_stale"] is True


@pytest.mark.asyncio
async def test_nav_status_fresh_and_stale_flag(
    client: AsyncClient,
    test_session: AsyncSession,
) -> None:
    headers = await _get_auth_headers(client, "fresh_user2@example.com")

    # 1. Fresh success run (10 hours ago)
    t_fresh = datetime.now(UTC) - timedelta(hours=10)
    run_fresh = NavSyncRun(
        source="amfi_navall",
        status="success",
        started_at=t_fresh,
        finished_at=t_fresh + timedelta(seconds=15),
        schemes_parsed=14400,
        funds_created=14400,
        funds_updated=0,
        nav_rows_written=5,
        duration_ms=15000,
    )
    test_session.add(run_fresh)
    await test_session.commit()

    res1 = await client.get("/api/v1/nav/status", headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()["data"]
    assert data1["last_run_status"] == "success"
    assert data1["schemes_parsed"] == 14400
    assert data1["funds_created"] == 14400
    assert data1["is_stale"] is False

    # 2. Older success run (37 hours ago)
    await test_session.delete(run_fresh)
    t_old = datetime.now(UTC) - timedelta(hours=37)
    run_old = NavSyncRun(
        source="amfi_navall",
        status="success",
        started_at=t_old,
        finished_at=t_old + timedelta(seconds=15),
        schemes_parsed=14400,
        funds_created=0,
        funds_updated=14400,
        nav_rows_written=5,
        duration_ms=15000,
    )
    test_session.add(run_old)
    await test_session.commit()

    res2 = await client.get("/api/v1/nav/status", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()["data"]
    assert data2["is_stale"] is True
