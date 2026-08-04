"""Workflow runtime validation helpers for CreatorOS."""

from __future__ import annotations

from creatoros.core import WorkflowStateError
from creatoros.workflows.enums import WorkflowExecutionStatus
from creatoros.workflows.models import WorkflowExecution
from creatoros.workflows.transitions import is_terminal_status, is_transition_allowed


def _raise_workflow_state_error(
    message: str,
    *,
    code: str,
    details: dict[str, object],
) -> None:
    """Raise a workflow state error with safe details."""

    raise WorkflowStateError(message, code=code, details=details)


def validate_transition(
    current: WorkflowExecutionStatus,
    target: WorkflowExecutionStatus,
) -> None:
    """Validate that a status transition is allowed."""

    if is_transition_allowed(current, target):
        return

    _raise_workflow_state_error(
        f"Workflow execution cannot transition from '{current.value}' to '{target.value}'",
        code="workflow_invalid_transition",
        details={
            "current_status": current.value,
            "target_status": target.value,
        },
    )


def validate_execution_can_start(
    execution: WorkflowExecution,
) -> None:
    """Validate that a workflow execution can start."""

    if execution.status is not WorkflowExecutionStatus.PENDING:
        _raise_workflow_state_error(
            "Workflow execution can only start from pending status",
            code="workflow_execution_cannot_start",
            details={"current_status": execution.status.value},
        )

    if execution.started_at is not None:
        _raise_workflow_state_error(
            "Workflow execution cannot start when started_at is already set",
            code="workflow_execution_cannot_start",
            details={"current_status": execution.status.value},
        )

    if execution.completed_at is not None:
        _raise_workflow_state_error(
            "Workflow execution cannot start when completed_at is already set",
            code="workflow_execution_cannot_start",
            details={"current_status": execution.status.value},
        )


def validate_execution_can_pause(
    execution: WorkflowExecution,
) -> None:
    """Validate that a workflow execution can pause."""

    if execution.status is not WorkflowExecutionStatus.RUNNING:
        _raise_workflow_state_error(
            "Workflow execution can only pause from running status",
            code="workflow_execution_cannot_pause",
            details={"current_status": execution.status.value},
        )


def validate_execution_can_resume(
    execution: WorkflowExecution,
) -> None:
    """Validate that a workflow execution can resume."""

    if execution.status not in {
        WorkflowExecutionStatus.PAUSED,
        WorkflowExecutionStatus.AWAITING_APPROVAL,
    }:
        _raise_workflow_state_error(
            "Workflow execution can only resume from paused or awaiting_approval status",
            code="workflow_execution_cannot_resume",
            details={"current_status": execution.status.value},
        )


def validate_execution_can_complete(
    execution: WorkflowExecution,
) -> None:
    """Validate that a workflow execution can complete."""

    if execution.status is not WorkflowExecutionStatus.RUNNING:
        _raise_workflow_state_error(
            "Workflow execution can only complete from running status",
            code="workflow_execution_cannot_complete",
            details={"current_status": execution.status.value},
        )

    if execution.completed_at is not None:
        _raise_workflow_state_error(
            "Workflow execution cannot complete when completed_at is already set",
            code="workflow_execution_cannot_complete",
            details={"current_status": execution.status.value},
        )


def validate_execution_can_fail(
    execution: WorkflowExecution,
) -> None:
    """Validate that a workflow execution can fail."""

    if execution.status not in {
        WorkflowExecutionStatus.RUNNING,
        WorkflowExecutionStatus.AWAITING_APPROVAL,
    }:
        _raise_workflow_state_error(
            "Workflow execution can only fail from running or awaiting_approval status",
            code="workflow_execution_cannot_fail",
            details={"current_status": execution.status.value},
        )

    if execution.completed_at is not None:
        _raise_workflow_state_error(
            "Workflow execution cannot fail when completed_at is already set",
            code="workflow_execution_cannot_fail",
            details={"current_status": execution.status.value},
        )


def validate_execution_can_cancel(
    execution: WorkflowExecution,
) -> None:
    """Validate that a workflow execution can cancel."""

    if is_terminal_status(execution.status):
        _raise_workflow_state_error(
            "Workflow execution cannot cancel from a terminal status",
            code="workflow_execution_cannot_cancel",
            details={"current_status": execution.status.value},
        )


__all__ = [
    "validate_execution_can_cancel",
    "validate_execution_can_complete",
    "validate_execution_can_fail",
    "validate_execution_can_pause",
    "validate_execution_can_resume",
    "validate_execution_can_start",
    "validate_transition",
]
