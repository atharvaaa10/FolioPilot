import json
from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_DEFAULT_JWT_SECRET = "dev-insecure-secret-key-change-in-production-min-32-chars"


class Settings(BaseSettings):
    """Application settings read from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "FolioPilot"
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://foliopilot:foliopilot@localhost:5432/foliopilot"
    REDIS_URL: str = "redis://localhost:6379/0"
    TEST_DATABASE_URL: str = (
        "postgresql+asyncpg://foliopilot:foliopilot@localhost:5432/foliopilot_test"
    )
    TEST_REDIS_URL: str = "redis://localhost:6379/1"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    JWT_SECRET: str = DEV_DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    LOG_LEVEL: str = "INFO"
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7
    REFRESH_GRACE_SECONDS: int = 10
    REFRESH_COOKIE_NAME: str = "fp_refresh"
    TRUST_PROXY_HEADERS: bool = False

    # AMFI & MFAPI Data Sources
    AMFI_NAV_URL: str = "https://www.amfiindia.com/spages/NAVAll.txt"
    MFAPI_BASE_URL: str = "https://api.mfapi.in"
    FUND_SYNC_MIN_SCHEMES: int = 5000
    FUND_INACTIVE_AFTER_DAYS: int = 30
    HTTP_TIMEOUT_SECONDS: float = 30.0
    HTTP_MAX_RETRIES: int = 3
    FUND_SEARCH_RATE_LIMIT_PER_MIN: int = 60

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            val_str = value.strip()
            if val_str.startswith("[") and val_str.endswith("]"):
                try:
                    parsed = json.loads(val_str)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in val_str.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(item) for item in value]
        return ["http://localhost:3000"]

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """Fail fast if configuration is insecure."""
        if "*" in self.CORS_ORIGINS:
            raise ValueError(
                "CORS_ORIGINS cannot contain '*' because credentials require explicit origins"
            )
        if self.ENVIRONMENT != "development":
            if (
                not self.JWT_SECRET
                or self.JWT_SECRET == DEV_DEFAULT_JWT_SECRET
                or len(self.JWT_SECRET) < 32
            ):
                raise ValueError(
                    "JWT_SECRET must be explicitly set to a secure secret of >= 32 chars "
                    f"outside development mode (current ENVIRONMENT={self.ENVIRONMENT!r})"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
