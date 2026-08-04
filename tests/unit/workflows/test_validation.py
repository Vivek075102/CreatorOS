"""Unit tests for CreatorOS workflow runtime validation helpers."""

import pytest

from creatoros.core import WorkflowStateError
from creatoros.workflows import WorkflowExecutionStatus, validate_transition
from creatoros.workflows.models import WorkflowExecution
from creatoros.workflows.validation import (
    validate_execution_can_cancel,
    validate_execution_can_complete,
    validate_execution_can_fail,
    validate_execution_can_pause,
    validate_execution_can_resume,
    validate_execution_can_start,
)


def build_execution(*, status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING) -> WorkflowExecution:
    """Create a simple workflow execution for validation tests."""

    return WorkflowExecution(
        workflow_id="workflow_123",
        workflow_version=1,
        job_id="job_123",
        status=status,
    )


def test_validate_transition_accepts_valid_transitions() -> None:
    """Transition validation should allow documented transitions."""

    validate_transition(WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.RUNNING)
    validate_transition(WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.PAUSED)


def test_validate_transition_raises_for_invalid_transitions() -> None:
    """Invalid transitions should raise WorkflowStateError."""

    with pytest.raises(WorkflowStateError):
        validate_transition(WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.COMPLETED)


def test_validate_transition_error_code_and_safe_details_are_correct() -> None:
    """Invalid transition errors should use the documented code and safe details."""

    with pytest.raises(WorkflowStateError) as exc_info:
        validate_transition(WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.COMPLETED)

    assert exc_info.value.code == "workflow_invalid_transition"
    assert exc_info.value.details == {
        "current_status": "pending",
        "target_status": "completed",
    }


def test_start_validation_accepts_fresh_pending_execution() -> None:
    """A fresh pending execution should be startable."""

    validate_execution_can_start(build_execution())


def test_start_validation_rejects_invalid_status_or_existing_timestamps() -> None:
    """Start validation should reject invalid status and existing timestamps."""

    with pytest.raises(WorkflowStateError):
        validate_execution_can_start(build_execution(status=WorkflowExecutionStatus.RUNNING))

    execution = build_execution()
    execution.started_at = execution.created_at
    with pytest.raises(WorkflowStateError):
        validate_execution_can_start(execution)

    execution = build_execution()
    execution.completed_at = execution.created_at
    with pytest.raises(WorkflowStateError):
        validate_execution_can_start(execution)


def test_pause_validation_requires_running() -> None:
    """Pause validation should require running status."""

    validate_execution_can_pause(build_execution(status=WorkflowExecutionStatus.RUNNING))

    with pytest.raises(WorkflowStateError):
        validate_execution_can_pause(build_execution(status=WorkflowExecutionStatus.PAUSED))


def test_resume_validation_allows_paused_and_awaiting_approval_only() -> None:
    """Resume validation should allow paused and awaiting_approval only."""

    validate_execution_can_resume(build_execution(status=WorkflowExecutionStatus.PAUSED))
    validate_execution_can_resume(build_execution(status=WorkflowExecutionStatus.AWAITING_APPROVAL))

    with pytest.raises(WorkflowStateError):
        validate_execution_can_resume(build_execution(status=WorkflowExecutionStatus.RUNNING))


def test_complete_validation_requires_running() -> None:
    """Complete validation should require running status."""

    validate_execution_can_complete(build_execution(status=WorkflowExecutionStatus.RUNNING))

    with pytest.raises(WorkflowStateError):
        validate_execution_can_complete(build_execution(status=WorkflowExecutionStatus.PAUSED))


def test_fail_validation_allows_running_and_awaiting_approval() -> None:
    """Fail validation should allow running and awaiting_approval only."""

    validate_execution_can_fail(build_execution(status=WorkflowExecutionStatus.RUNNING))
    validate_execution_can_fail(build_execution(status=WorkflowExecutionStatus.AWAITING_APPROVAL))

    with pytest.raises(WorkflowStateError):
        validate_execution_can_fail(build_execution(status=WorkflowExecutionStatus.PENDING))


def test_cancel_validation_rejects_terminal_states() -> None:
    """Cancel validation should reject terminal statuses."""

    validate_execution_can_cancel(build_execution(status=WorkflowExecutionStatus.PENDING))
    validate_execution_can_cancel(build_execution(status=WorkflowExecutionStatus.RUNNING))

    with pytest.raises(WorkflowStateError):
        validate_execution_can_cancel(build_execution(status=WorkflowExecutionStatus.COMPLETED))
