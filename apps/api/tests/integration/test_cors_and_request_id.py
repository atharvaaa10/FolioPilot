"""Tests verifying CORS and X-Request-ID header propagation across status codes."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_cors_and_request_id_headers_200() -> None:
    """Verify 200 response contains X-Request-ID and CORS headers."""
    settings = get_settings()
    app = create_app(settings)
    origin = settings.CORS_ORIGINS[0]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Preflight OPTIONS
        preflight = await client.options(
            "/api/v1/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert preflight.status_code == 200
        assert (
            preflight.headers.get("access-control-allow-origin") == origin
            or preflight.headers.get("access-control-allow-origin") == "*"
        )
        allow_headers = preflight.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allow_headers
        assert "content-type" in allow_headers

        # Normal GET 200
        response = await client.get("/api/v1/health", headers={"Origin": origin})
        assert response.status_code == 200
        assert "x-request-id" in response.headers
        assert response.headers.get("access-control-allow-origin") == origin
        expose_headers = response.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in expose_headers or "x-request-id" in expose_headers.lower()


@pytest.mark.asyncio
async def test_cors_and_request_id_headers_404() -> None:
    """Verify 404 response contains X-Request-ID and CORS headers."""
    settings = get_settings()
    app = create_app(settings)
    origin = settings.CORS_ORIGINS[0]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/nonexistent-route-404", headers={"Origin": origin})
        assert response.status_code == 404
        assert "x-request-id" in response.headers
        assert response.headers.get("access-control-allow-origin") == origin
        expose_headers = response.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in expose_headers or "x-request-id" in expose_headers.lower()


@pytest.mark.asyncio
async def test_cors_and_request_id_headers_401() -> None:
    """Verify 401 response contains X-Request-ID and CORS headers."""
    settings = get_settings()
    app = create_app(settings)
    origin = settings.CORS_ORIGINS[0]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/users/me", headers={"Origin": origin})
        assert response.status_code == 401
        assert "x-request-id" in response.headers
        assert response.headers.get("access-control-allow-origin") == origin
        expose_headers = response.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in expose_headers or "x-request-id" in expose_headers.lower()


@pytest.mark.asyncio
async def test_cors_and_request_id_headers_429() -> None:
    """Verify 429 response contains X-Request-ID, Retry-After, and CORS headers."""
    settings = get_settings()
    app = create_app(settings)
    origin = settings.CORS_ORIGINS[0]

    # Add a temporary test route raising RateLimitedError
    from app.core.errors import RateLimitedError

    @app.get("/api/v1/test-rate-limit")
    async def trigger_rate_limit() -> None:
        raise RateLimitedError(
            message="Rate limit exceeded",
            retry_after=60,
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/test-rate-limit", headers={"Origin": origin})
        assert response.status_code == 429
        assert "x-request-id" in response.headers
        assert response.headers.get("retry-after") == "60"
        assert response.headers.get("access-control-allow-origin") == origin
        expose_headers = response.headers.get("access-control-expose-headers", "")
        assert "Retry-After" in expose_headers or "retry-after" in expose_headers.lower()
        assert "X-Request-ID" in expose_headers or "x-request-id" in expose_headers.lower()
