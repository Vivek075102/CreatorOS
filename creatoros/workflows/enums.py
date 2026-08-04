"""Workflow-specific enumerations for CreatorOS data contracts."""

from enum import StrEnum


class WorkflowDefinitionStatus(StrEnum):
    """Lifecycle states for stored workflow definitions."""

    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


class WorkflowExecutionStatus(StrEnum):
    """Lifecycle states for workflow executions."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepKind(StrEnum):
    """Kinds of steps supported by workflow definitions."""

    ENGINE = "engine"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    MANUAL = "manual"


class WorkflowEventType(StrEnum):
    """Event types recorded during workflow execution history."""

    EXECUTION_CREATED = "execution_created"
    EXECUTION_STARTED = "execution_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    EXECUTION_PAUSED = "execution_paused"
    EXECUTION_RESUMED = "execution_resumed"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"


class ApprovalDecisionType(StrEnum):
    """Allowed approval decision outcomes."""

    APPROVED = "approved"
    REJECTED = "rejected"


class FailureBehavior(StrEnum):
    """Configured workflow behavior after a step failure."""

    STOP = "stop"
    CONTINUE_WORKFLOW = "continue_workflow"
    PAUSE = "pause"


__all__ = [
    "ApprovalDecisionType",
    "FailureBehavior",
    "WorkflowDefinitionStatus",
    "WorkflowEventType",
    "WorkflowExecutionStatus",
    "WorkflowStepKind",
]
