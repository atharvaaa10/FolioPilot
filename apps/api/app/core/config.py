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
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    JWT_SECRET: str = DEV_DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    LOG_LEVEL: str = "INFO"

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
        """Fail fast outside dev if JWT_SECRET is missing or using dev fallback."""
        if self.ENVIRONMENT != "development":
            if not self.JWT_SECRET or self.JWT_SECRET == DEV_DEFAULT_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET must be explicitly set to a secure secret "
                    f"outside development mode (current ENVIRONMENT={self.ENVIRONMENT!r})"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
