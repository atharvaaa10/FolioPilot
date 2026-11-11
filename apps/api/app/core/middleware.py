import json
import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.constants import IMPORT_MAX_FILE_BYTES
from app.core.errors import ImportFileTooLargeError
from app.core.logging import get_logger

logger = get_logger("http.request")
IMPORT_UPLOAD_PATH_PATTERN = re.compile(r"^/api/v1/portfolios/[^/]+/imports/?$")


class ImportUploadSizeLimitMiddleware:
    """Pure ASGI middleware enforcing IMPORT_MAX_FILE_BYTES early at the ASGI level.

    Counts incoming request bytes chunk-by-chunk to cut off oversized bodies before
    multipart buffering or spooling, supporting chunked uploads without Content-Length.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not IMPORT_UPLOAD_PATH_PATTERN.match(path):
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)
        content_length_str = headers.get("content-length")

        if content_length_str:
            try:
                cl = int(content_length_str)
                if cl > IMPORT_MAX_FILE_BYTES:
                    await self._send_413_response(send, cl)
                    return
            except ValueError:
                pass

        total_received = 0
        exceeded = False

        async def limited_receive() -> Message:
            nonlocal total_received, exceeded
            if exceeded:
                return {"type": "http.request", "body": b"", "more_body": False}
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                total_received += len(chunk)
                if total_received > IMPORT_MAX_FILE_BYTES:
                    exceeded = True
                    raise ImportFileTooLargeError(
                        f"Upload size {total_received} exceeds limit of "
                        f"{IMPORT_MAX_FILE_BYTES} bytes",
                        details={"file_size": total_received, "max_bytes": IMPORT_MAX_FILE_BYTES},
                    )
            return message

        try:
            await self.app(scope, limited_receive, send)
        except ImportFileTooLargeError as exc:
            file_size_val = (
                exc.details.get("file_size", total_received)
                if isinstance(exc.details, dict)
                else total_received
            )
            await self._send_413_response(send, file_size_val)

    async def _send_413_response(self, send: Send, file_size: int) -> None:
        content = json.dumps(
            {
                "success": False,
                "error": {
                    "code": "IMPORT_FILE_TOO_LARGE",
                    "message": (
                        f"Upload exceeds maximum allowed size of {IMPORT_MAX_FILE_BYTES} bytes"
                    ),
                    "details": {
                        "file_size": file_size,
                        "max_bytes": IMPORT_MAX_FILE_BYTES,
                    },
                },
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(content)).encode("ascii")),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": content,
                "more_body": False,
            }
        )


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
