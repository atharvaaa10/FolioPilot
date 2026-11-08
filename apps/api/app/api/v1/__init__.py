"""API v1 routers package."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.funds import router as funds_router
from app.api.v1.health import router as health_router
from app.api.v1.nav import router as nav_router
from app.api.v1.users import router as users_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(health_router)
v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(funds_router)
v1_router.include_router(nav_router)

__all__ = ["v1_router"]
