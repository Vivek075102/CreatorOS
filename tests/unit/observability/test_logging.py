"""Unit tests for structured logging configuration."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from creatoros.config import get_settings
from creatoros.observability import bind_context, clear_context, configure_logging, get_logger


def reset_logging_state() -> None:
    """Reset logger state between tests."""

    logger = logging.getLogger("creatoros")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logging.shutdown()
    clear_context()
    get_settings.cache_clear()


def configure_test_logging(tmp_path: Path, monkeypatch, *, app_env: str = "testing") -> Path:
    """Configure logging against a temporary logs directory."""

    logs_dir = tmp_path / "logs"
    monkeypatch.setenv("APP_NAME", "CreatorOS")
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
    )
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("LOGS_DIR", str(logs_dir))
    get_settings.cache_clear()
    configure_logging()
    return logs_dir / "creatoros.log"


def test_configure_logging_can_be_called_more_than_once_without_duplicate_handlers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Repeated configuration should not duplicate handlers."""

    reset_logging_state()
    configure_test_logging(tmp_path, monkeypatch)
    logger = logging.getLogger("creatoros")
    first_handler_count = len(logger.handlers)

    configure_logging()

    assert len(logger.handlers) == first_handler_count == 2


def test_get_logger_returns_a_usable_logger(tmp_path: Path, monkeypatch) -> None:
    """A configured logger should emit events without error."""

    reset_logging_state()
    configure_test_logging(tmp_path, monkeypatch)

    logger = get_logger("unit")
    logger.info("usable logger event", sample="value")

    assert (tmp_path / "logs" / "creatoros.log").exists()


def test_log_file_is_created_in_temporary_logs_directory(tmp_path: Path, monkeypatch) -> None:
    """Configuring logging should create the target log file on first write."""

    reset_logging_state()
    log_file = configure_test_logging(tmp_path, monkeypatch)

    get_logger("unit").info("file creation test")

    assert log_file.exists()


def test_file_logs_are_valid_json_lines(tmp_path: Path, monkeypatch) -> None:
    """File output should be valid JSON lines."""

    reset_logging_state()
    log_file = configure_test_logging(tmp_path, monkeypatch)

    get_logger("unit").info("json line test", answer=42)

    line = log_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(line)

    assert payload["event"] == "json line test"
    assert payload["answer"] == 42


def test_bound_context_fields_appear_in_log_output(tmp_path: Path, monkeypatch) -> None:
    """Bound execution context should be included in emitted log records."""

    reset_logging_state()
    log_file = configure_test_logging(tmp_path, monkeypatch)

    bind_context(job_id="job-123", step_id="step-1", workflow_name="gaming-short")
    get_logger("unit").info("context test")

    payload = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert payload["job_id"] == "job-123"
    assert payload["step_id"] == "step-1"
    assert payload["workflow_name"] == "gaming-short"


def test_sensitive_values_are_redacted(tmp_path: Path, monkeypatch) -> None:
    """Top-level sensitive values should be redacted."""

    reset_logging_state()
    log_file = configure_test_logging(tmp_path, monkeypatch)

    get_logger("unit").info("redaction test", api_key="secret-value", safe="visible")

    payload = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert payload["api_key"] == "[REDACTED]"
    assert payload["safe"] == "visible"


def test_nested_sensitive_values_are_redacted(tmp_path: Path, monkeypatch) -> None:
    """Nested sensitive structures should be redacted where practical."""

    reset_logging_state()
    log_file = configure_test_logging(tmp_path, monkeypatch)

    get_logger("unit").info(
        "nested redaction test",
        payload={
            "token": "secret-token",
            "nested": {"client_secret": "very-secret", "safe": "ok"},
            "items": [{"authorization": "Bearer secret"}, {"safe": "still-ok"}],
        },
    )

    payload = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert payload["payload"]["token"] == "[REDACTED]"
    assert payload["payload"]["nested"]["client_secret"] == "[REDACTED]"
    assert payload["payload"]["nested"]["safe"] == "ok"
    assert payload["payload"]["items"][0]["authorization"] == "[REDACTED]"
    assert payload["payload"]["items"][1]["safe"] == "still-ok"


def test_non_sensitive_values_are_preserved(tmp_path: Path, monkeypatch) -> None:
    """Non-sensitive values should survive logging unchanged."""

    reset_logging_state()
    log_file = configure_test_logging(tmp_path, monkeypatch)

    get_logger("unit").info("preserve test", count=3, enabled=True)

    payload = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert payload["count"] == 3
    assert payload["enabled"] is True


def test_production_mode_produces_json_console_configuration(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Production console output should render as JSON."""

    reset_logging_state()
    configure_test_logging(tmp_path, monkeypatch, app_env="production")

    get_logger("unit").info("production console test", status="ok")

    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip().splitlines()[-1])

    assert payload["event"] == "production console test"
    assert payload["status"] == "ok"


def test_no_real_credentials_are_required(tmp_path: Path, monkeypatch) -> None:
    """Logging setup should work without provider credentials."""

    reset_logging_state()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    log_file = configure_test_logging(tmp_path, monkeypatch)
    get_logger("unit").info("no credentials test")

    assert log_file.exists()
