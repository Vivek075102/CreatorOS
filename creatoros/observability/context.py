"""Execution-scoped logging context helpers."""

from contextvars import ContextVar

_job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
_step_id_var: ContextVar[str | None] = ContextVar("step_id", default=None)
_workflow_name_var: ContextVar[str | None] = ContextVar("workflow_name", default=None)
_engine_name_var: ContextVar[str | None] = ContextVar("engine_name", default=None)
_provider_name_var: ContextVar[str | None] = ContextVar("provider_name", default=None)

_CONTEXT_VARS: dict[str, ContextVar[str | None]] = {
    "job_id": _job_id_var,
    "step_id": _step_id_var,
    "workflow_name": _workflow_name_var,
    "engine_name": _engine_name_var,
    "provider_name": _provider_name_var,
}


def bind_context(
    *,
    job_id: str | None = None,
    step_id: str | None = None,
    workflow_name: str | None = None,
    engine_name: str | None = None,
    provider_name: str | None = None,
) -> None:
    """Bind non-empty context values to the current execution context."""

    values = {
        "job_id": job_id,
        "step_id": step_id,
        "workflow_name": workflow_name,
        "engine_name": engine_name,
        "provider_name": provider_name,
    }

    for key, value in values.items():
        if value is None:
            continue

        normalized_value = value.strip()
        if not normalized_value:
            continue

        _CONTEXT_VARS[key].set(normalized_value)


def clear_context() -> None:
    """Clear all bound context values from the current execution context."""

    for context_var in _CONTEXT_VARS.values():
        context_var.set(None)


def get_context() -> dict[str, str]:
    """Return a copy of the current non-empty logging context."""

    context: dict[str, str] = {}

    for key, context_var in _CONTEXT_VARS.items():
        value = context_var.get()
        if value is not None:
            context[key] = value

    return context
