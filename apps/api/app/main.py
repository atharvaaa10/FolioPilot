from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import ImportUploadSizeLimitMiddleware, RequestIDAndLoggingMiddleware
from app.core.redis import close_redis_client

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing startup configuration and graceful resource shutdown."""
    settings = get_settings()
    setup_logging(environment=settings.ENVIRONMENT, log_level=settings.LOG_LEVEL)
    if "*" in settings.CORS_ORIGINS:
        raise ValueError("CORS_ORIGINS cannot contain '*' when allow_credentials is True")
    logger.info("app_starting", app_name=settings.APP_NAME, environment=settings.ENVIRONMENT)

    yield

    logger.info("app_stopping")
    await close_redis_client()
    logger.info("app_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application factory."""
    active_settings = settings or get_settings()

    if "*" in active_settings.CORS_ORIGINS:
        raise ValueError("CORS_ORIGINS cannot contain '*' when allow_credentials is True")

    is_dev = active_settings.ENVIRONMENT == "development"

    app = FastAPI(
        title=active_settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs" if is_dev else None,
        redoc_url="/redoc" if is_dev else None,
        openapi_url="/openapi.json" if is_dev else None,
        lifespan=lifespan,
    )

    # Middleware: Request ID and structlog tracing (outermost execution)
    app.add_middleware(RequestIDAndLoggingMiddleware)

    # Middleware: Import upload early byte limiter (enforces 2MB max before spooling)
    app.add_middleware(ImportUploadSizeLimitMiddleware)

    # Middleware: CORS with strict credentials and explicit origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "Accept",
            "Accept-Language",
            "Content-Language",
        ],
        expose_headers=["Retry-After", "X-Request-ID"],
    )

    # Error Handlers
    register_error_handlers(app)

    # Routers
    app.include_router(api_router)

    return app


app = create_app()
