"""Structured logging configuration for CreatorOS."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

from creatoros.config import get_settings
from creatoros.observability.context import get_context

_BASE_LOGGER_NAME = "creatoros"
_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "credential",
)


def _add_execution_context(
    _: Any,
    __: str,
    event_dict: structlog.typing.EventDict,
) -> structlog.typing.EventDict:
    """Add execution-scoped context variables to each event."""

    for key, value in get_context().items():
        event_dict.setdefault(key, value)
    return event_dict


def _is_sensitive_key(key: str) -> bool:
    """Return whether a key name should be redacted."""

    key_lower = key.lower()
    return any(part in key_lower for part in _SENSITIVE_KEY_PARTS)


def _redact_value(value: Any) -> Any:
    """Recursively redact sensitive nested structures."""

    if isinstance(value, dict):
        return {
            nested_key: "[REDACTED]" if _is_sensitive_key(str(nested_key)) else _redact_value(nested_value)
            for nested_key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [_redact_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)

    return value


def _redact_sensitive_values(
    _: Any,
    __: str,
    event_dict: structlog.typing.EventDict,
) -> structlog.typing.EventDict:
    """Redact sensitive values before rendering log output."""

    redacted_event_dict: structlog.typing.EventDict = {}

    for key, value in event_dict.items():
        if _is_sensitive_key(key):
            redacted_event_dict[key] = "[REDACTED]"
        else:
            redacted_event_dict[key] = _redact_value(value)

    return redacted_event_dict


def _shared_processors() -> list[structlog.types.Processor]:
    """Return processors shared by console and file logging."""

    return [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_execution_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive_values,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def _build_console_renderer(app_env: str) -> structlog.types.Processor:
    """Return the console renderer for the current environment."""

    if app_env == "production":
        return structlog.processors.JSONRenderer()

    if app_env == "testing":
        return structlog.processors.KeyValueRenderer(
            key_order=["event", "level", "logger", "job_id", "step_id"],
            sort_keys=False,
        )

    return structlog.dev.ConsoleRenderer()


def _build_formatter(
    renderer: structlog.types.Processor,
) -> structlog.stdlib.ProcessorFormatter:
    """Create a structlog formatter with the shared processing chain."""

    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )


def _configure_handlers(logs_dir: Path, app_env: str) -> list[logging.Handler]:
    """Create configured console and rotating file handlers."""

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "creatoros.log"

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_build_formatter(_build_console_renderer(app_env)))

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(_build_formatter(structlog.processors.JSONRenderer()))

    return [console_handler, file_handler]


def configure_logging() -> None:
    """Configure CreatorOS structured logging for console and file output."""

    settings = get_settings()

    logger = logging.getLogger(_BASE_LOGGER_NAME)
    logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    for handler in _configure_handlers(settings.logs_dir, settings.app_env):
        logger.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.filter_by_level,
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structlog logger for CreatorOS."""

    logger_name = _BASE_LOGGER_NAME if name is None else f"{_BASE_LOGGER_NAME}.{name}"
    return structlog.get_logger(logger_name)
