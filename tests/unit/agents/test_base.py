"""Unit tests for the CreatorOS base agent lifecycle."""

from __future__ import annotations

import asyncio

import pytest

from creatoros.agents import AgentExecutionContext, AgentResult, BaseAgent
from creatoros.core import AgentError, CreatorOSError, CreatorOSValidationError
from creatoros.observability import clear_context, get_context
from creatoros.providers import (
    ProviderCapability,
    ProviderInfo,
    ProviderRegistry,
    create_provider_registry,
)


class FakeLogger:
    """Capture structured log events for agent lifecycle assertions."""

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


class FocusedAgent(BaseAgent[str, str]):
    """Concrete test agent that records lifecycle behavior."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
        logger: FakeLogger | None = None,
        agent_name: str = "focused_agent",
        fail_before: Exception | None = None,
        fail_execute: Exception | None = None,
        fail_after: Exception | None = None,
    ) -> None:
        self._agent_name = agent_name
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
        return self._agent_name

    async def before_execute(
        self,
        input_data: str,
        *,
        context: AgentExecutionContext,
    ) -> None:
        self.calls.append("before_execute")
        self.contexts_seen.append(get_context())
        if self.fail_before is not None:
            raise self.fail_before

    async def execute(
        self,
        input_data: str,
        *,
        context: AgentExecutionContext,
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
        context: AgentExecutionContext,
    ) -> None:
        self.calls.append("after_execute")
        self.contexts_seen.append(get_context())
        if self.fail_after is not None:
            raise self.fail_after

    def use_provider_name(self, provider_type: str, name: str) -> str:
        """Resolve a provider through the registry and return its canonical name."""

        provider = self.get_provider(provider_type, name)
        return provider.info.name


@pytest.fixture(autouse=True)
def clear_logging_context() -> None:
    """Ensure context state does not leak across agent tests."""

    clear_context()


def build_context() -> AgentExecutionContext:
    """Create a valid execution context for agent tests."""

    return AgentExecutionContext(
        job_id="job_123",
        step_id="step_1",
        workflow_name="gaming_short",
        engine_name="research_engine",
    )


def run_async(coro):
    """Execute an async coroutine in synchronous tests."""

    return asyncio.run(coro)


def test_run_calls_hooks_and_execute_in_order() -> None:
    """Run should call before_execute, execute, and after_execute in order."""

    agent = FocusedAgent()

    run_async(agent.run("hello", context=build_context()))

    assert agent.calls == ["before_execute", "execute", "after_execute"]


def test_run_returns_agent_result_containing_expected_data() -> None:
    """Run should return a structured agent result."""

    agent = FocusedAgent()

    result = run_async(agent.run("hello", context=build_context()))

    assert isinstance(result, AgentResult)
    assert result.data == "HELLO"


def test_run_uses_agent_name() -> None:
    """Run should store the normalized agent name in the result."""

    agent = FocusedAgent(agent_name="  analysis_agent  ")

    result = run_async(agent.run("hello", context=build_context()))

    assert result.agent_name == "analysis_agent"


def test_run_records_timezone_aware_timestamps() -> None:
    """Run should capture timezone-aware start and completion timestamps."""

    agent = FocusedAgent()

    result = run_async(agent.run("hello", context=build_context()))

    assert result.started_at.tzinfo is not None
    assert result.completed_at.tzinfo is not None
    assert result.started_at.utcoffset() is not None
    assert result.completed_at.utcoffset() is not None


def test_run_records_non_negative_duration() -> None:
    """Run should record a non-negative execution duration."""

    agent = FocusedAgent()

    result = run_async(agent.run("hello", context=build_context()))

    assert result.duration_seconds >= 0


def test_run_binds_job_step_workflow_and_engine_context() -> None:
    """Run should bind job, step, workflow, and engine logging context."""

    agent = FocusedAgent()

    run_async(agent.run("hello", context=build_context()))

    for context in agent.contexts_seen:
        assert context == {
            "job_id": "job_123",
            "step_id": "step_1",
            "workflow_name": "gaming_short",
            "engine_name": "research_engine",
        }


def test_lifecycle_logs_contain_agent_name() -> None:
    """Lifecycle events should include the agent name as structured data."""

    logger = FakeLogger()
    agent = FocusedAgent(logger=logger, agent_name="analysis_agent")

    run_async(agent.run("hello", context=build_context()))

    assert all(event["kwargs"]["agent_name"] == "analysis_agent" for event in logger.events)


def test_run_clears_context_after_successful_execution() -> None:
    """Run should clear logging context after a successful execution."""

    agent = FocusedAgent()

    run_async(agent.run("hello", context=build_context()))

    assert get_context() == {}


def test_run_clears_context_after_expected_failure() -> None:
    """Run should clear logging context when execution raises a CreatorOSError."""

    agent = FocusedAgent(fail_execute=CreatorOSError("expected failure"))

    with pytest.raises(CreatorOSError):
        run_async(agent.run("hello", context=build_context()))

    assert get_context() == {}


def test_run_clears_context_after_unexpected_failure() -> None:
    """Run should clear logging context when execution raises an unexpected exception."""

    agent = FocusedAgent(fail_execute=RuntimeError("boom"))

    with pytest.raises(AgentError):
        run_async(agent.run("hello", context=build_context()))

    assert get_context() == {}


def test_existing_creatoros_error_is_reraised_unchanged() -> None:
    """Expected CreatorOS errors should be preserved without wrapping."""

    error = CreatorOSError("expected failure")
    agent = FocusedAgent(fail_execute=error)

    with pytest.raises(CreatorOSError) as exc_info:
        run_async(agent.run("hello", context=build_context()))

    assert exc_info.value is error


def test_unexpected_exceptions_are_wrapped_as_agent_error() -> None:
    """Unexpected failures should be wrapped in AgentError."""

    agent = FocusedAgent(fail_execute=RuntimeError("boom"))

    with pytest.raises(AgentError):
        run_async(agent.run("hello", context=build_context()))


def test_agent_error_preserves_original_exception_as_cause() -> None:
    """Wrapped agent errors should keep the original exception as the cause."""

    cause = RuntimeError("boom")
    agent = FocusedAgent(fail_execute=cause)

    with pytest.raises(AgentError) as exc_info:
        run_async(agent.run("hello", context=build_context()))

    assert exc_info.value.__cause__ is cause


def test_blank_agent_name_raises_validation_error_before_execute() -> None:
    """Blank agent names should fail validation before execute is called."""

    agent = FocusedAgent(agent_name="   ")

    with pytest.raises(CreatorOSValidationError):
        run_async(agent.run("hello", context=build_context()))

    assert agent.execute_called is False


def test_supplied_provider_registry_is_used() -> None:
    """Supplied provider registries should be stored on the agent."""

    registry = create_provider_registry()
    agent = FocusedAgent(provider_registry=registry)

    assert agent.provider_registry is registry


def test_default_provider_registry_is_used_when_none_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default registry helper should be used when none is supplied."""

    registry = create_provider_registry()
    monkeypatch.setattr("creatoros.agents.base.get_provider_registry", lambda: registry)

    agent = FocusedAgent()

    assert agent.provider_registry is registry


def test_get_provider_delegates_to_registry() -> None:
    """BaseAgent should delegate provider lookups to the registry."""

    registry = create_provider_registry()
    provider = FakeProvider()
    registry.register(provider)
    agent = FocusedAgent(provider_registry=registry)

    assert agent.get_provider("llm", "openai") is provider


def test_get_typed_provider_delegates_to_registry() -> None:
    """BaseAgent should delegate typed provider lookups to the registry."""

    registry = create_provider_registry()
    provider = FakeProvider()
    registry.register(provider)
    agent = FocusedAgent(provider_registry=registry)

    assert agent.get_typed_provider("llm", "openai", FakeProvider) is provider


def test_input_and_output_values_are_not_logged_automatically() -> None:
    """Lifecycle logs should not automatically include input or output payloads."""

    logger = FakeLogger()
    agent = FocusedAgent(logger=logger)

    run_async(agent.run("secret_input", context=build_context()))

    combined = "".join(str(event["kwargs"]) for event in logger.events)
    assert "secret_input" not in combined
    assert "SECRET_INPUT" not in combined


def test_before_execute_failures_follow_normal_error_handling() -> None:
    """Failures in before_execute should follow the same wrapping rules as execute."""

    agent = FocusedAgent(fail_before=RuntimeError("before failed"))

    with pytest.raises(AgentError):
        run_async(agent.run("hello", context=build_context()))


def test_after_execute_failures_follow_normal_error_handling() -> None:
    """Failures in after_execute should follow the same wrapping rules as execute."""

    agent = FocusedAgent(fail_after=RuntimeError("after failed"))

    with pytest.raises(AgentError):
        run_async(agent.run("hello", context=build_context()))


def test_successful_execution_logs_agent_started_and_agent_completed() -> None:
    """Successful executions should log agent_started and agent_completed."""

    logger = FakeLogger()
    agent = FocusedAgent(logger=logger)

    run_async(agent.run("hello", context=build_context()))

    assert [event["event"] for event in logger.events] == ["agent_started", "agent_completed"]


def test_expected_failures_log_agent_failed() -> None:
    """Expected CreatorOS failures should emit an agent_failed log event."""

    logger = FakeLogger()
    agent = FocusedAgent(logger=logger, fail_execute=CreatorOSError("expected failure"))

    with pytest.raises(CreatorOSError):
        run_async(agent.run("hello", context=build_context()))

    assert any(event["event"] == "agent_failed" for event in logger.events)


def test_base_agent_contains_no_engine_resolution_or_orchestration_methods() -> None:
    """BaseAgent should not expose engine-resolution or orchestration methods."""

    assert not hasattr(BaseAgent, "get_engine")
    assert not hasattr(BaseAgent, "get_typed_engine")
    assert not hasattr(BaseAgent, "orchestrate")


def test_focused_agent_can_use_fake_provider_through_registry() -> None:
    """A minimal focused agent should be able to use a fake provider via the registry."""

    registry = create_provider_registry()
    provider = FakeProvider(name="Anthropic")
    registry.register(provider)
    agent = FocusedAgent(provider_registry=registry)

    assert agent.use_provider_name("llm", "anthropic") == "Anthropic"
