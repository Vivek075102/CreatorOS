"""Unit tests for CreatorOS workflow enums."""

from creatoros.workflows import (
    ApprovalDecisionType,
    FailureBehavior,
    WorkflowDefinitionStatus,
    WorkflowEventType,
    WorkflowExecutionStatus,
    WorkflowStepKind,
)


def test_workflow_definition_status_values() -> None:
    """Workflow definition status values should match the documented contract."""

    assert [status.value for status in WorkflowDefinitionStatus] == ["draft", "ready", "archived"]


def test_workflow_execution_status_values() -> None:
    """Workflow execution status values should match the documented contract."""

    assert [status.value for status in WorkflowExecutionStatus] == [
        "pending",
        "running",
        "paused",
        "awaiting_approval",
        "completed",
        "failed",
        "cancelled",
    ]


def test_workflow_step_kind_values() -> None:
    """Workflow step kind values should match the documented contract."""

    assert [kind.value for kind in WorkflowStepKind] == [
        "engine",
        "approval",
        "notification",
        "manual",
    ]


def test_workflow_event_type_values() -> None:
    """Workflow event type values should match the documented contract."""

    assert [event_type.value for event_type in WorkflowEventType] == [
        "execution_created",
        "execution_started",
        "step_started",
        "step_completed",
        "step_failed",
        "approval_requested",
        "approval_approved",
        "approval_rejected",
        "execution_paused",
        "execution_resumed",
        "execution_completed",
        "execution_failed",
        "execution_cancelled",
    ]


def test_approval_decision_type_values() -> None:
    """Approval decision values should match the documented contract."""

    assert [decision.value for decision in ApprovalDecisionType] == ["approved", "rejected"]


def test_failure_behavior_values() -> None:
    """Failure behavior values should match the documented contract."""

    assert [behavior.value for behavior in FailureBehavior] == ["stop", "continue_workflow", "pause"]
