import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

logger = get_logger("http.request")


class RequestIDAndLoggingMiddleware:
    """Pure ASGI middleware that propagates X-Request-ID and logs request metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)
        request_id = headers.get("x-request-id")
        if not request_id:
            request_id = uuid.uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                res_headers = MutableHeaders(scope=message)
                res_headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.exception(
                "request_failed",
                method=scope.get("method"),
                path=scope.get("path"),
                duration_ms=round(duration_ms, 2),
            )
            structlog.contextvars.clear_contextvars()
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "request_finished",
            method=scope.get("method"),
            path=scope.get("path"),
            status=status_code,
            duration_ms=round(duration_ms, 2),
        )
        structlog.contextvars.clear_contextvars()
