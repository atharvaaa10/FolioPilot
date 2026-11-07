import pytest
from pydantic import ValidationError

from app.core.config import DEV_DEFAULT_JWT_SECRET, Settings


def test_settings_development_defaults() -> None:
    """Verify that default settings succeed in development environment."""
    settings = Settings(ENVIRONMENT="development", JWT_SECRET=DEV_DEFAULT_JWT_SECRET)
    assert settings.APP_NAME == "FolioPilot"
    assert settings.ENVIRONMENT == "development"
    assert settings.JWT_ALGORITHM == "HS256"
    assert "http://localhost:3000" in settings.CORS_ORIGINS


def test_settings_fail_fast_in_production_with_dev_secret() -> None:
    """Verify Settings raises ValidationError in production if JWT_SECRET is the dev fallback."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=DEV_DEFAULT_JWT_SECRET,
        )
    assert "JWT_SECRET must be explicitly set" in str(exc_info.value)


def test_settings_fail_fast_in_production_with_empty_secret() -> None:
    """Verify Settings raises ValidationError in production if JWT_SECRET is empty."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="",
        )
    assert "JWT_SECRET must be explicitly set" in str(exc_info.value)


def test_settings_succeeds_in_production_with_custom_secret() -> None:
    """Verify Settings succeeds in production when a non-dev secret is supplied."""
    secure_secret = "super-secret-production-random-key-12345"
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET=secure_secret,
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.JWT_SECRET == secure_secret


def test_cors_origins_parsing_variants() -> None:
    """Verify parsing of JSON list and comma-separated string for CORS_ORIGINS."""
    settings_json = Settings(
        ENVIRONMENT="development",
        CORS_ORIGINS='["https://app.foliopilot.in", "https://admin.foliopilot.in"]',  # type: ignore[arg-type]
    )
    assert settings_json.CORS_ORIGINS == [
        "https://app.foliopilot.in",
        "https://admin.foliopilot.in",
    ]

    settings_csv = Settings(
        ENVIRONMENT="development",
        CORS_ORIGINS="https://app.foliopilot.in, https://admin.foliopilot.in",  # type: ignore[arg-type]
    )
    assert settings_csv.CORS_ORIGINS == [
        "https://app.foliopilot.in",
        "https://admin.foliopilot.in",
    ]


def test_cors_origins_wildcard_rejected() -> None:
    """Verify Settings rejects wildcard '*' in CORS_ORIGINS due to credential security."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(CORS_ORIGINS=["*"])
    assert "CORS_ORIGINS cannot contain '*'" in str(exc_info.value)


def test_create_app_rejects_wildcard_cors() -> None:
    """Verify create_app fails fast if CORS_ORIGINS contains wildcard '*'."""
    from app.main import create_app

    bad_settings = Settings.model_construct(CORS_ORIGINS=["*"])
    with pytest.raises(ValueError, match="CORS_ORIGINS cannot contain"):
        create_app(bad_settings)
