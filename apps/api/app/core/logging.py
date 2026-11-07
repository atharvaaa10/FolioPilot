import logging
import sys
from typing import Any

import structlog

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "set-cookie",
        "secret",
    }
)


def _redact_value(val: Any) -> Any:
    if isinstance(val, dict):
        return {
            k: (
                "[REDACTED]"
                if str(k).lower() in SENSITIVE_KEYS
                or any(s in str(k).lower() for s in ("password", "token", "secret"))
                else _redact_value(v)
            )
            for k, v in val.items()
        }
    if isinstance(val, list):
        return [_redact_value(v) for v in val]
    return val


def redact_sensitive_keys(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact sensitive keys from structlog event dictionaries."""
    for key in list(event_dict.keys()):
        lower_key = str(key).lower()
        if lower_key in SENSITIVE_KEYS or any(
            s in lower_key for s in ("password", "token", "secret")
        ):
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def setup_logging(environment: str = "development", log_level: str = "INFO") -> None:
    """Configure structured logging using structlog.

    Uses readable ConsoleRenderer for development and JSONRenderer for production.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive_keys,
    ]

    renderer: Any
    if environment == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # Silence overly verbose third-party loggers
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
