from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_db_session
from app.main import create_app


@pytest.mark.asyncio
async def test_health_liveness(client: AsyncClient) -> None:
    """Verify that liveness endpoint returns 200 OK with no dependencies checked."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"success": True, "data": {"status": "ok"}}


@pytest.mark.asyncio
async def test_health_readiness_all_healthy() -> None:
    """Verify that readiness probe returns 200 when DB and Redis are healthy."""
    test_app = create_app()

    # Override get_db_session with a mock session
    mock_session = AsyncMock()

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    test_app.dependency_overrides[get_db_session] = override_db

    with (
        patch("app.api.v1.health.check_db_health", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health.check_redis_health", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.return_value = True
        mock_redis.return_value = True

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert payload["data"] == {
                "status": "ready",
                "database": "healthy",
                "redis": "healthy",
            }


@pytest.mark.asyncio
async def test_health_readiness_db_unhealthy() -> None:
    """Verify that readiness probe returns 503 when the database check fails."""
    test_app = create_app()

    mock_session = AsyncMock()

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    test_app.dependency_overrides[get_db_session] = override_db

    with (
        patch("app.api.v1.health.check_db_health", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health.check_redis_health", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.side_effect = Exception("DB connection timeout")
        mock_redis.return_value = True

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            assert response.status_code == 503
            payload = response.json()
            assert payload["success"] is False
            assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"
            assert payload["error"]["details"]["database"] == "unhealthy"
            assert payload["error"]["details"]["redis"] == "healthy"


@pytest.mark.asyncio
async def test_health_readiness_redis_unhealthy() -> None:
    """Verify that readiness probe returns 503 when the Redis check fails."""
    test_app = create_app()

    mock_session = AsyncMock()

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    test_app.dependency_overrides[get_db_session] = override_db

    with (
        patch("app.api.v1.health.check_db_health", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health.check_redis_health", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.return_value = True
        mock_redis.return_value = False

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            assert response.status_code == 503
            payload = response.json()
            assert payload["success"] is False
            assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"
            assert payload["error"]["details"]["database"] == "healthy"
            assert payload["error"]["details"]["redis"] == "unhealthy"
