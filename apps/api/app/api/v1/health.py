from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import check_db_health, get_db_session
from app.core.logging import get_logger
from app.core.redis import check_redis_health
from app.schemas.envelope import SuccessEnvelope

logger = get_logger("health")

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=SuccessEnvelope[dict[str, str]], status_code=status.HTTP_200_OK)
async def liveness_check() -> dict[str, Any]:
    """Lightweight liveness probe with zero external service dependencies."""
    return {"success": True, "data": {"status": "ok"}}


@router.get("/ready")
async def readiness_check(
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """Readiness probe verifying PostgreSQL and Redis reachability."""
    db_status = "healthy"
    try:
        if not await check_db_health(session):
            db_status = "unhealthy"
    except Exception as exc:
        logger.warning("readiness_db_check_failed", error=str(exc))
        db_status = f"unhealthy: {exc}"

    redis_status = "healthy"
    try:
        if not await check_redis_health():
            redis_status = "unhealthy"
    except Exception as exc:
        logger.warning("readiness_redis_check_failed", error=str(exc))
        redis_status = f"unhealthy: {exc}"

    is_ready = (db_status == "healthy") and (redis_status == "healthy")

    if is_ready:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": {
                    "status": "ready",
                    "database": "healthy",
                    "redis": "healthy",
                },
            },
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "success": False,
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": "One or more dependent services are unavailable",
                "details": {
                    "database": db_status,
                    "redis": redis_status,
                },
            },
        },
    )
