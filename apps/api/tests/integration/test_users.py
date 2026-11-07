from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.services.security import create_access_token


@pytest.mark.asyncio
async def test_get_current_user_me_success(client: AsyncClient) -> None:
    """Verify /users/me returns authenticated user details."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "me@example.com", "password": "Password123!"},
    )
    token = reg.json()["data"]["access_token"]

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["email"] == "me@example.com"
    assert payload["data"]["is_active"] is True
    assert "id" in payload["data"]


@pytest.mark.asyncio
async def test_get_current_user_me_missing_or_malformed_header(client: AsyncClient) -> None:
    """Verify missing or malformed header returns 401 INVALID_TOKEN."""
    res1 = await client.get("/api/v1/users/me")
    assert res1.status_code == 401
    assert res1.json()["error"]["code"] == "INVALID_TOKEN"

    res2 = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert res2.status_code == 401
    assert res2.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_get_current_user_me_expired_token(client: AsyncClient) -> None:
    """Verify expired access token returns 401 TOKEN_EXPIRED."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "expired@example.com", "password": "Password123!"},
    )
    settings = get_settings()

    # Forge expired token for this user
    expired_token = create_access_token(
        user_id="d3b07384-d113-4a44-9388-372a818c34f8",
        secret=settings.JWT_SECRET,
        expires_delta=timedelta(seconds=-10),
        now=datetime.now(UTC),
    )

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_get_current_user_me_inactive_user(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify inactive user cannot access /users/me even with valid access token."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "inactive@example.com", "password": "Password123!"},
    )
    token = reg.json()["data"]["access_token"]

    # Deactivate user in database
    await test_session.execute(
        update(User).where(User.email == "inactive@example.com").values(is_active=False)
    )
    await test_session.commit()

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
