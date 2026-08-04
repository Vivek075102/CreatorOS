"""Unit tests for the CreatorOS base engine lifecycle."""

from __future__ import annotations

import asyncio
from datetime import UTC

import pytest

from creatoros.core import CreatorOSError, EngineError
from creatoros.engines import BaseEngine, EngineExecutionContext, EngineResult
from creatoros.observability import clear_context, get_context
from creatoros.providers import (
    ProviderCapability,
    ProviderInfo,
    ProviderRegistry,
    create_provider_registry,
)


class FakeLogger:
    """Capture structured log events for engine lifecycle assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def info(self, event: str, **kwargs: object) -> None:
        """Record an info-level structured event."""

        self.events.append(
            {
                "level": "info",
                "event": event,
                "kwargs": kwargs,
                "context": get_context(),
            },
        )

    def error(self, event: str, **kwargs: object) -> None:
        """Record an error-level structured event."""

        self.events.append(
            {
                "level": "error",
                "event": event,
                "kwargs": kwargs,
                "context": get_context(),
            },
        )

    def exception(self, event: str, **kwargs: object) -> None:
        """Record an exception-level structured event."""

        self.events.append(
            {
                "level": "error",
                "event": event,
                "kwargs": kwargs,
                "context": get_context(),
            },
        )


class FakeProvider:
    """Minimal provider object used for provider helper tests."""

    def __init__(self, *, name: str = "OpenAI", provider_type: str = "llm") -> None:
        self._info = ProviderInfo(
            name=name,
            provider_type=provider_type,
            capabilities={ProviderCapability.TEXT_GENERATION},
        )

    @property
    def info(self) -> ProviderInfo:
        return self._info

    async def health_check(self) -> bool:
        return True


class RecordingEngine(BaseEngine[str, str]):
    """Concrete test engine that records lifecycle behavior."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
        logger: FakeLogger | None = None,
        engine_name: str = "recording_engine",
        fail_before: Exception | None = None,
        fail_execute: Exception | None = None,
        fail_after: Exception | None = None,
    ) -> None:
        self._engine_name = engine_name
        self.logger_override = logger or FakeLogger()
        self.fail_before = fail_before
        self.fail_execute = fail_execute
        self.fail_after = fail_after
        self.calls: list[str] = []
        self.execute_called = False
        self.contexts_seen: list[dict[str, str]] = []
        super().__init__(provider_registry=provider_registry)
        self.logger = self.logger_override

    @property
    def name(self) -> str:
        return self._engine_name

    async def before_execute(
        self,
        input_data: str,
        *,
        context: EngineExecutionContext,
    ) -> None:
        self.calls.append("before_execute")
        self.contexts_seen.append(get_context())
        if self.fail_before is not None:
            raise self.fail_before

    async def execute(
        self,
        input_data: str,
        *,
        context: EngineExecutionContext,
    ) -> str:
        self.calls.append("execute")
        self.execute_called = True
        self.contexts_seen.append(get_context())
        if self.fail_execute is not None:
            raise self.fail_execute
        return input_data.upper()

    async def after_execute(
        self,
        result: str,
        *,
        context: EngineExecutionContext,
    ) -> None:
        self.calls.append("after_execute")
        self.contexts_seen.append(get_context())
        if self.fail_after is not None:
            raise self.fail_after


@pytest.fixture(autouse=True)
def clear_logging_context() -> None:
    """Ensure context state does not leak across engine tests."""

    clear_context()


def build_context() -> EngineExecutionContext:
    """Create a valid execution context for engine tests."""

    return EngineExecutionContext(
        job_id="job_123",
        step_id="step_1",
        workflow_name="gaming_short",
    )


def run_async(coro):
    """Execute an async coroutine in synchronous tests."""

    return asyncio.run(coro)


def test_run_calls_hooks_and_execute_in_order() -> None:
    """Run should call before_execute, execute, and after_execute in order."""

    engine = RecordingEngine()

    run_async(engine.run("hello", context=build_context()))

    assert engine.calls == ["before_execute", "execute", "after_execute"]


def test_run_returns_engine_result_with_expected_data() -> None:
    """Run should return a structured engine result."""

    engine = RecordingEngine()

    result = run_async(engine.run("hello", context=build_context()))

    assert isinstance(result, EngineResult)
    assert result.data == "HELLO"


def test_run_uses_engine_name() -> None:
    """Run should store the normalized engine name in the result."""

    engine = RecordingEngine(engine_name="  script_engine  ")

    result = run_async(engine.run("hello", context=build_context()))

    assert result.engine_name == "script_engine"


def test_run_records_timezone_aware_timestamps() -> None:
    """Run should capture timezone-aware start and completion timestamps."""

    engine = RecordingEngine()

    result = run_async(engine.run("hello", context=build_context()))

    assert result.started_at.tzinfo is not None
    assert result.completed_at.tzinfo is not None
    assert result.started_at.utcoffset() == UTC.utcoffset(result.started_at)
    assert result.completed_at.utcoffset() == UTC.utcoffset(result.completed_at)


def test_run_records_non_negative_duration() -> None:
    """Run should record a non-negative execution duration."""

    engine = RecordingEngine()

    result = run_async(engine.run("hello", context=build_context()))

    assert result.duration_seconds >= 0


def test_run_binds_logging_context_values() -> None:
    """Run should bind job, step, workflow, and engine logging context."""

    engine = RecordingEngine(engine_name="script_engine")

    run_async(engine.run("hello", context=build_context()))

    for context in engine.contexts_seen:
        assert context == {
            "job_id": "job_123",
            "step_id": "step_1",
            "workflow_name": "gaming_short",
            "engine_name": "script_engine",
        }


def test_run_clears_logging_context_after_success() -> None:
    """Run should clear logging context after a successful execution."""

    engine = RecordingEngine()

    run_async(engine.run("hello", context=build_context()))

    assert get_context() == {}


def test_run_clears_logging_context_after_expected_failure() -> None:
    """Run should clear logging context when execution raises a CreatorOSError."""

    engine = RecordingEngine(fail_execute=CreatorOSError("expected failure"))

    with pytest.raises(CreatorOSError):
        run_async(engine.run("hello", context=build_context()))

    assert get_context() == {}


def test_run_clears_logging_context_after_unexpected_failure() -> None:
    """Run should clear logging context when execution raises an unexpected exception."""

    engine = RecordingEngine(fail_execute=RuntimeError("boom"))

    with pytest.raises(EngineError):
        run_async(engine.run("hello", context=build_context()))

    assert get_context() == {}


def test_existing_creatoros_error_is_reraised_unchanged() -> None:
    """Expected CreatorOS errors should be preserved without wrapping."""

    error = CreatorOSError("expected failure")
    engine = RecordingEngine(fail_execute=error)

    with pytest.raises(CreatorOSError) as exc_info:
        run_async(engine.run("hello", context=build_context()))

    assert exc_info.value is error


def test_unexpected_exceptions_are_wrapped_as_engine_error() -> None:
    """Unexpected failures should be wrapped in EngineError."""

    engine = RecordingEngine(fail_execute=RuntimeError("boom"))

    with pytest.raises(EngineError):
        run_async(engine.run("hello", context=build_context()))


def test_wrapped_engine_error_preserves_original_cause() -> None:
    """Wrapped engine errors should keep the original exception as the cause."""

    cause = RuntimeError("boom")
    engine = RecordingEngine(fail_execute=cause)

    with pytest.raises(EngineError) as exc_info:
        run_async(engine.run("hello", context=build_context()))

    assert exc_info.value.__cause__ is cause


def test_invalid_blank_engine_name_raises_before_execute() -> None:
    """Blank engine names should fail validation before execute is called."""

    engine = RecordingEngine(engine_name="   ")

    with pytest.raises(CreatorOSError):
        run_async(engine.run("hello", context=build_context()))

    assert engine.execute_called is False


def test_supplied_provider_registry_is_used() -> None:
    """Supplied provider registries should be stored on the engine."""

    registry = create_provider_registry()
    engine = RecordingEngine(provider_registry=registry)

    assert engine.provider_registry is registry


def test_default_provider_registry_is_used_when_none_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default registry helper should be used when none is supplied."""

    registry = create_provider_registry()
    monkeypatch.setattr("creatoros.engines.base.get_provider_registry", lambda: registry)

    engine = RecordingEngine()

    assert engine.provider_registry is registry


def test_get_provider_delegates_correctly() -> None:
    """BaseEngine should delegate provider lookups to the registry."""

    registry = create_provider_registry()
    provider = FakeProvider()
    registry.register(provider)
    engine = RecordingEngine(provider_registry=registry)

    assert engine.get_provider("llm", "openai") is provider


def test_get_typed_provider_delegates_correctly() -> None:
    """BaseEngine should delegate typed provider lookups to the registry."""

    registry = create_provider_registry()
    provider = FakeProvider()
    registry.register(provider)
    engine = RecordingEngine(provider_registry=registry)

    assert engine.get_typed_provider("llm", "openai", FakeProvider) is provider


def test_input_and_output_values_are_not_logged_automatically() -> None:
    """Lifecycle logs should not automatically include input or output payloads."""

    logger = FakeLogger()
    engine = RecordingEngine(logger=logger)

    run_async(engine.run("secret_input", context=build_context()))

    combined = "".join(str(event["kwargs"]) for event in logger.events)
    assert "secret_input" not in combined
    assert "SECRET_INPUT" not in combined


def test_before_execute_failure_follows_expected_error_handling_rules() -> None:
    """Failures in before_execute should follow the same wrapping rules as execute."""

    engine = RecordingEngine(fail_before=RuntimeError("before failed"))

    with pytest.raises(EngineError):
        run_async(engine.run("hello", context=build_context()))


def test_after_execute_failure_follows_expected_error_handling_rules() -> None:
    """Failures in after_execute should follow the same wrapping rules as execute."""

    engine = RecordingEngine(fail_after=RuntimeError("after failed"))

    with pytest.raises(EngineError):
        run_async(engine.run("hello", context=build_context()))


def test_expected_failures_log_engine_failed() -> None:
    """Expected CreatorOS failures should emit an engine_failed log event."""

    logger = FakeLogger()
    engine = RecordingEngine(logger=logger, fail_execute=CreatorOSError("expected failure"))

    with pytest.raises(CreatorOSError):
        run_async(engine.run("hello", context=build_context()))

    assert any(event["event"] == "engine_failed" for event in logger.events)


def test_successful_execution_logs_engine_started_and_engine_completed() -> None:
    """Successful executions should log engine_started and engine_completed."""

    logger = FakeLogger()
    engine = RecordingEngine(logger=logger)

    run_async(engine.run("hello", context=build_context()))

    assert [event["event"] for event in logger.events] == ["engine_started", "engine_completed"]
