from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Structured error payload for failed requests."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error explanation")
    details: Any = Field(
        default=None,
        description="Optional diagnostic details or validation items",
    )


class ResponseEnvelope[T](BaseModel):
    """Unified API response envelope."""

    success: bool
    data: T | None = None
    error: ErrorDetail | None = None


class SuccessEnvelope[T](BaseModel):
    """Typed success response envelope."""

    success: bool = True
    data: T


class FailureEnvelope(BaseModel):
    """Typed failure response envelope."""

    success: bool = False
    error: ErrorDetail
