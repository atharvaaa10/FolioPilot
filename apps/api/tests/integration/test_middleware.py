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
