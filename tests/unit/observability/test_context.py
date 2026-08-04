"""Unit tests for observability context helpers."""

from contextvars import Context

from creatoros.observability.context import bind_context, clear_context, get_context


def test_context_starts_empty() -> None:
    """Context should be empty when nothing has been bound."""

    clear_context()

    assert get_context() == {}


def test_bind_context_stores_supplied_values() -> None:
    """Binding context should store the provided non-empty values."""

    clear_context()

    bind_context(
        job_id="job-123",
        step_id="step-1",
        workflow_name="gaming-short",
        engine_name="script",
        provider_name="mock",
    )

    assert get_context() == {
        "job_id": "job-123",
        "step_id": "step-1",
        "workflow_name": "gaming-short",
        "engine_name": "script",
        "provider_name": "mock",
    }


def test_none_values_are_ignored() -> None:
    """None values should not be stored in the context."""

    clear_context()

    bind_context(job_id="job-123", step_id=None)

    assert get_context() == {"job_id": "job-123"}


def test_blank_strings_are_ignored() -> None:
    """Blank strings should not be stored in the context."""

    clear_context()

    bind_context(job_id="   ", step_id="")

    assert get_context() == {}


def test_clear_context_removes_values() -> None:
    """Clearing the context should remove all stored values."""

    bind_context(job_id="job-123", step_id="step-1")

    clear_context()

    assert get_context() == {}


def test_get_context_returns_a_copy() -> None:
    """Mutating the returned context should not affect stored state."""

    clear_context()
    bind_context(job_id="job-123")

    context = get_context()
    context["job_id"] = "mutated"

    assert get_context() == {"job_id": "job-123"}


def test_context_values_do_not_leak_across_isolated_contexts() -> None:
    """Execution context values should remain isolated."""

    clear_context()
    bind_context(job_id="job-123")

    isolated_context = Context()
    isolated_values = isolated_context.run(get_context)

    assert isolated_values == {}
    assert get_context() == {"job_id": "job-123"}
