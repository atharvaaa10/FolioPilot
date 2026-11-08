import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("errors")


class AppError(Exception):
    """Base application exception supporting standard error envelope formatting."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = 500,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    """Resource not found (HTTP 404)."""

    def __init__(self, message: str = "Resource not found", details: Any = None) -> None:
        super().__init__(message=message, code="NOT_FOUND", status_code=404, details=details)


class FundNotFoundError(AppError):
    """Fund with specified scheme_code not found (HTTP 404)."""

    def __init__(self, message: str = "Fund not found", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="FUND_NOT_FOUND",
            status_code=404,
            details=details,
        )


class ValidationError(AppError):
    """Business rule or input validation error (HTTP 422)."""

    def __init__(self, message: str = "Validation failed", details: Any = None) -> None:
        super().__init__(message=message, code="VALIDATION_ERROR", status_code=422, details=details)


class UnauthorizedError(AppError):
    """Authentication required or failed (HTTP 401)."""

    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "UNAUTHORIZED",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=401, details=details)


class ForbiddenError(AppError):
    """Authorization permission denied (HTTP 403)."""

    def __init__(
        self,
        message: str = "Permission denied",
        code: str = "FORBIDDEN",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=403, details=details)


class ConflictError(AppError):
    """State conflict, such as duplicate unique key (HTTP 409)."""

    def __init__(
        self,
        message: str = "Resource conflict",
        code: str = "CONFLICT",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=409, details=details)


class RateLimitedError(AppError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        code: str = "RATE_LIMITED",
        details: Any = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=429, details=details)
        self.retry_after = retry_after


# --- Portfolio & Ledger Domain Errors (Phase 3A) ---


class PortfolioNotFoundError(NotFoundError):
    """Portfolio not found for current user (HTTP 404)."""

    def __init__(self, message: str = "Portfolio not found", details: Any = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "PORTFOLIO_NOT_FOUND"


class PortfolioNameTakenError(ConflictError):
    """Portfolio name already exists for this user (HTTP 409)."""

    def __init__(
        self, message: str = "A portfolio with this name already exists", details: Any = None
    ) -> None:
        super().__init__(message=message, code="PORTFOLIO_NAME_TAKEN", details=details)


class PortfolioLimitReachedError(ValidationError):
    """User has reached the maximum allowed portfolios (HTTP 422)."""

    def __init__(
        self, message: str = "Maximum number of portfolios reached", details: Any = None
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "PORTFOLIO_LIMIT_REACHED"


class TargetsInvalidError(ValidationError):
    """Target asset allocation sum is not 100.00% or contains invalid data (HTTP 422)."""

    def __init__(
        self, message: str = "Target allocations are invalid", details: Any = None
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "TARGETS_INVALID"


class TransactionNotFoundError(NotFoundError):
    """Transaction not found in portfolio (HTTP 404)."""

    def __init__(self, message: str = "Transaction not found", details: Any = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "TRANSACTION_NOT_FOUND"


class InsufficientUnitsError(ValidationError):
    """Selling more units than available at the transaction date (HTTP 422)."""

    def __init__(
        self, message: str = "Insufficient units available to sell", details: Any = None
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "INSUFFICIENT_UNITS"


class LedgerInconsistentError(ValidationError):
    """Ledger mutation violates historical consistency or constraints (HTTP 422)."""

    def __init__(
        self, message: str = "Transaction violates ledger consistency", details: Any = None
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "LEDGER_INCONSISTENT"


class AmountMismatchError(ValidationError):
    """Provided amount differs from units * NAV beyond allowable tolerance (HTTP 422)."""

    def __init__(
        self,
        message: str = "Provided amount does not match units * nav within tolerance",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "AMOUNT_MISMATCH"


class TransactionLimitReachedError(ValidationError):
    """Maximum number of transactions reached for portfolio (HTTP 422)."""

    def __init__(
        self,
        message: str = "Maximum number of transactions reached for this portfolio",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "TRANSACTION_LIMIT_REACHED"


def register_error_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI application."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        headers: dict[str, str] = {}
        if isinstance(exc, RateLimitedError) and exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.status_code,
            headers=headers if headers else None,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            404: "NOT_FOUND",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            503: "SERVICE_UNAVAILABLE",
        }
        code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "details": None,
                },
            },
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
        settings = get_settings()
        logger.exception("unhandled_internal_error", error=str(exc))

        if settings.ENVIRONMENT == "production":
            message = "Internal server error"
            details = None
        else:
            message = str(exc)
            details = traceback.format_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": message,
                    "details": details,
                },
            },
        )
