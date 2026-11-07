import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_request_id_generated_when_missing(client: AsyncClient) -> None:
    """Verify that X-Request-ID is generated and returned in headers when omitted by client."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) > 10


@pytest.mark.asyncio
async def test_request_id_preserved_when_provided(client: AsyncClient) -> None:
    """Verify that custom X-Request-ID is preserved and propagated back in response."""
    custom_id = "req-custom-trace-uuid-98765"
    response = await client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_cors_preflight_allows_authorization(client: AsyncClient) -> None:
    """Verify OPTIONS preflight request allows authorization and content-type headers."""
    response = await client.options(
        "/api/v1/users/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    allow_headers = response.headers.get("Access-Control-Allow-Headers", "").lower()
    assert "authorization" in allow_headers
    assert "content-type" in allow_headers


@pytest.mark.asyncio
async def test_cors_exposes_retry_after_and_request_id_headers(client: AsyncClient) -> None:
    """Verify CORS headers expose Retry-After and X-Request-ID to browser code."""
    response = await client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    exposed = response.headers.get("Access-Control-Expose-Headers", "")
    assert "Retry-After" in exposed
    assert "X-Request-ID" in exposed
