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


class PortfolioLimitReachedError(ConflictError):
    """User has reached the maximum allowed portfolios (HTTP 409)."""

    def __init__(
        self, message: str = "Maximum number of portfolios reached", details: Any = None
    ) -> None:
        super().__init__(message=message, code="PORTFOLIO_LIMIT_REACHED", details=details)


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


class InsufficientUnitsError(ConflictError):
    """Selling more units than available at the transaction date (HTTP 409)."""

    def __init__(
        self, message: str = "Insufficient units available to sell", details: Any = None
    ) -> None:
        super().__init__(message=message, code="INSUFFICIENT_UNITS", details=details)


class LedgerInconsistentError(ConflictError):
    """Ledger mutation violates historical consistency or constraints (HTTP 409)."""

    def __init__(
        self, message: str = "Transaction violates ledger consistency", details: Any = None
    ) -> None:
        super().__init__(message=message, code="LEDGER_INCONSISTENT", details=details)


class AmountMismatchError(ValidationError):
    """Provided amount differs from units * NAV beyond allowable tolerance (HTTP 422)."""

    def __init__(
        self,
        message: str = "Provided amount does not match units * nav within tolerance",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "AMOUNT_MISMATCH"


class TransactionLimitReachedError(ConflictError):
    """Maximum number of transactions reached for portfolio (HTTP 409)."""

    def __init__(
        self,
        message: str = "Maximum number of transactions reached for this portfolio",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code="TRANSACTION_LIMIT_REACHED", details=details)


# Phase 3B: SIP Exceptions
class SipNotFoundError(NotFoundError):
    """SIP not found (HTTP 404)."""

    def __init__(self, message: str = "SIP not found", details: Any = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "SIP_NOT_FOUND"


class SipLimitReachedError(ConflictError):
    """Maximum number of SIPs reached for portfolio (HTTP 409)."""

    def __init__(
        self,
        message: str = "Maximum number of SIPs reached for this portfolio",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code="SIP_LIMIT_REACHED", details=details)


class SipInvalidScheduleError(ValidationError):
    """Invalid SIP schedule or range containing no due dates (HTTP 422)."""

    def __init__(
        self,
        message: str = "Invalid SIP schedule",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "SIP_INVALID_SCHEDULE"


class SipAlreadyPausedError(ConflictError):
    """SIP is already paused (HTTP 409)."""

    def __init__(self, message: str = "SIP is already paused", details: Any = None) -> None:
        super().__init__(message=message, code="SIP_ALREADY_PAUSED", details=details)


class SipNotPausedError(ConflictError):
    """SIP is not paused (HTTP 409)."""

    def __init__(self, message: str = "SIP is not paused", details: Any = None) -> None:
        super().__init__(message=message, code="SIP_NOT_PAUSED", details=details)


class SipAlreadyEndedError(ConflictError):
    """SIP is already ended (HTTP 409)."""

    def __init__(self, message: str = "SIP is already ended", details: Any = None) -> None:
        super().__init__(message=message, code="SIP_ALREADY_ENDED", details=details)


class InstallmentNotFoundError(NotFoundError):
    """Installment not found (HTTP 404)."""

    def __init__(self, message: str = "Installment not found", details: Any = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "INSTALLMENT_NOT_FOUND"


class InstallmentNotSkippableError(ConflictError):
    """Installment cannot be skipped (HTTP 409)."""

    def __init__(self, message: str = "Installment cannot be skipped", details: Any = None) -> None:
        super().__init__(message=message, code="INSTALLMENT_NOT_SKIPPABLE", details=details)


class TransactionManagedBySipError(ConflictError):
    """Transaction is managed by a SIP and cannot be modified directly (HTTP 409)."""

    def __init__(
        self,
        message: str = "Transaction is managed by a SIP and cannot be modified or deleted directly",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code="TRANSACTION_MANAGED_BY_SIP", details=details)


class FundInactiveError(ConflictError):
    """Fund is inactive and cannot accept new investments (HTTP 409)."""

    def __init__(self, message: str = "Fund is inactive", details: Any = None) -> None:
        super().__init__(message=message, code="FUND_INACTIVE", details=details)


# Excel Import Errors (Phase 4)
class ImportFileInvalidError(ValidationError):
    """Uploaded file failed safety or format validation (HTTP 422)."""

    def __init__(self, message: str = "Invalid import file", details: Any = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "IMPORT_FILE_INVALID"


class ImportFileTooLargeError(AppError):
    """Uploaded file exceeds max size limit (HTTP 413)."""

    def __init__(self, message: str = "Import file too large", details: Any = None) -> None:
        super().__init__(
            message=message, code="IMPORT_FILE_TOO_LARGE", status_code=413, details=details
        )


class ImportTooManyRowsError(ValidationError):
    """File contains more rows than maximum allowed limit (HTTP 422)."""

    def __init__(
        self, message: str = "Import file contains too many rows", details: Any = None
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "IMPORT_TOO_MANY_ROWS"


class ImportEmptyError(ValidationError):
    """File contains no data rows (HTTP 422)."""

    def __init__(
        self, message: str = "Import file contains no data rows", details: Any = None
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "IMPORT_EMPTY"


class ImportTemplateMismatchError(ValidationError):
    """Required headers missing from template (HTTP 422)."""

    def __init__(self, message: str = "Import template mismatch", details: Any = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "IMPORT_TEMPLATE_MISMATCH"


class ImportNotFoundError(NotFoundError):
    """Import batch not found (HTTP 404)."""

    def __init__(self, message: str = "Import not found", details: Any = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "IMPORT_NOT_FOUND"


class ImportAlreadyCommittedError(ConflictError):
    """Import is already committed or undone (HTTP 409)."""

    def __init__(self, message: str = "Import is already committed", details: Any = None) -> None:
        super().__init__(message=message, code="IMPORT_ALREADY_COMMITTED", details=details)


class ImportNotCommittedError(ConflictError):
    """Import is not committed (HTTP 409)."""

    def __init__(self, message: str = "Import is not committed", details: Any = None) -> None:
        super().__init__(message=message, code="IMPORT_NOT_COMMITTED", details=details)


class ImportHasErrorsError(ConflictError):
    """Import contains error rows and skip_invalid is false (HTTP 409)."""

    def __init__(self, message: str = "Import has invalid rows", details: Any = None) -> None:
        super().__init__(message=message, code="IMPORT_HAS_ERRORS", details=details)


class ImportStaleError(ConflictError):
    """Import preview plan is stale due to concurrent changes or fingerprint mismatch (HTTP 409)."""

    def __init__(
        self, message: str = "Import preview is stale. Please re-upload.", details: Any = None
    ) -> None:
        super().__init__(message=message, code="IMPORT_STALE", details=details)


class ImportNothingToImportError(ConflictError):
    """Import has zero candidate rows to import (HTTP 409)."""

    def __init__(self, message: str = "No rows to import", details: Any = None) -> None:
        super().__init__(message=message, code="IMPORT_NOTHING_TO_IMPORT", details=details)


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
        from fastapi.encoders import jsonable_encoder

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": jsonable_encoder(exc.errors()),
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
            413: "IMPORT_FILE_TOO_LARGE",
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
