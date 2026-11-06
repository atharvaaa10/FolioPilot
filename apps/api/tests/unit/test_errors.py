from app.core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


def test_app_error_defaults() -> None:
    err = AppError("Something went wrong")
    assert err.message == "Something went wrong"
    assert err.code == "INTERNAL_SERVER_ERROR"
    assert err.status_code == 500
    assert err.details is None


def test_not_found_error() -> None:
    err = NotFoundError("Portfolio not found", details={"id": "123"})
    assert err.message == "Portfolio not found"
    assert err.code == "NOT_FOUND"
    assert err.status_code == 404
    assert err.details == {"id": "123"}


def test_validation_error() -> None:
    err = ValidationError("Invalid amount", details={"field": "amount"})
    assert err.message == "Invalid amount"
    assert err.code == "VALIDATION_ERROR"
    assert err.status_code == 422


def test_unauthorized_error() -> None:
    err = UnauthorizedError()
    assert err.message == "Authentication required"
    assert err.code == "UNAUTHORIZED"
    assert err.status_code == 401


def test_forbidden_error() -> None:
    err = ForbiddenError("Insufficient rights")
    assert err.message == "Insufficient rights"
    assert err.code == "FORBIDDEN"
    assert err.status_code == 403


def test_conflict_error() -> None:
    err = ConflictError("Email already registered")
    assert err.message == "Email already registered"
    assert err.code == "CONFLICT"
    assert err.status_code == 409
