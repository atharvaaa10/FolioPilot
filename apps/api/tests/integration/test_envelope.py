import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError, ValidationError
from app.main import create_app
from app.schemas.envelope import SuccessEnvelope

# Dummy schemas and test router to verify envelope behaviors
dummy_router = APIRouter(prefix="/test")


class DummyInput(BaseModel):
    name: str = Field(min_length=3)
    amount: int = Field(gt=0)


@dummy_router.post("/items", response_model=SuccessEnvelope[dict[str, str]])
async def create_item(payload: DummyInput) -> dict[str, object]:
    return {"success": True, "data": {"name": payload.name, "amount": str(payload.amount)}}


@dummy_router.get("/custom-not-found")
async def trigger_not_found() -> None:
    raise NotFoundError("Entity missing", details={"entity_id": "xyz"})


@dummy_router.get("/custom-validation")
async def trigger_validation() -> None:
    raise ValidationError("Invalid input state", details={"field": "pan_number"})


@pytest.fixture
def app_with_test_routes() -> FastAPI:
    app = create_app()
    app.include_router(dummy_router)
    return app


@pytest.mark.asyncio
async def test_success_envelope(app_with_test_routes: FastAPI) -> None:
    transport = ASGITransport(app=app_with_test_routes)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/test/items", json={"name": "Equity Fund", "amount": 5000})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["data"] == {"name": "Equity Fund", "amount": "5000"}
        assert "error" not in payload or payload["error"] is None


@pytest.mark.asyncio
async def test_request_validation_error_envelope(app_with_test_routes: FastAPI) -> None:
    transport = ASGITransport(app=app_with_test_routes)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid payload: name too short, amount negative
        resp = await client.post("/test/items", json={"name": "a", "amount": -10})
        assert resp.status_code == 422
        payload = resp.json()
        assert payload["success"] is False
        assert "error" in payload
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert payload["error"]["message"] == "Request validation failed"
        assert isinstance(payload["error"]["details"], list)
        assert len(payload["error"]["details"]) > 0


@pytest.mark.asyncio
async def test_custom_app_error_envelopes(app_with_test_routes: FastAPI) -> None:
    transport = ASGITransport(app=app_with_test_routes)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Not found
        resp_nf = await client.get("/test/custom-not-found")
        assert resp_nf.status_code == 404
        nf_json = resp_nf.json()
        assert nf_json["success"] is False
        assert nf_json["error"]["code"] == "NOT_FOUND"
        assert nf_json["error"]["message"] == "Entity missing"
        assert nf_json["error"]["details"] == {"entity_id": "xyz"}

        # Validation error
        resp_val = await client.get("/test/custom-validation")
        assert resp_val.status_code == 422
        val_json = resp_val.json()
        assert val_json["success"] is False
        assert val_json["error"]["code"] == "VALIDATION_ERROR"
        assert val_json["error"]["message"] == "Invalid input state"
        assert val_json["error"]["details"] == {"field": "pan_number"}
