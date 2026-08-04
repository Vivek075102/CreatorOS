"""Unit tests for CreatorOS workflow models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from creatoros.domain import ApprovalStatus, WorkflowStepResult, WorkflowStepStatus
from creatoros.workflows import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRequest,
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowStepDefinition,
    WorkflowStepKind,
)


def build_step(
    *,
    step_id: str | None = None,
    name: str = "Research",
    kind: WorkflowStepKind = WorkflowStepKind.ENGINE,
    handler_name: str | None = "research_engine",
    depends_on: list[str] | None = None,
) -> WorkflowStepDefinition:
    """Create a valid workflow step definition for tests."""

    kwargs: dict[str, object] = {
        "name": name,
        "kind": kind,
        "depends_on": [] if depends_on is None else depends_on,
    }
    if step_id is not None:
        kwargs["id"] = step_id
    if handler_name is not None:
        kwargs["handler_name"] = handler_name
    return WorkflowStepDefinition(**kwargs)


def build_workflow_step_result() -> WorkflowStepResult:
    """Create a valid workflow step result for execution tests."""

    return WorkflowStepResult(
        job_id="job_123",
        step_name="Research",
        status=WorkflowStepStatus.COMPLETED,
        approval_status=ApprovalStatus.NOT_REQUIRED,
        started_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 4, 10, 1, tzinfo=UTC),
    )


def test_workflow_step_definition_generates_expected_id_prefix() -> None:
    """Workflow steps should generate workflow_step-prefixed identifiers."""

    step = build_step()

    assert step.id.startswith("workflow_step_")


def test_workflow_step_definition_rejects_blank_strings() -> None:
    """Workflow steps should reject blank required and optional textual values."""

    with pytest.raises(ValidationError):
        build_step(name="   ")

    with pytest.raises(ValidationError):
        build_step(handler_name="   ")

    with pytest.raises(ValidationError):
        build_step(depends_on=["valid_step", "   "])


def test_workflow_step_definition_validates_engine_handler_dependencies_and_numbers() -> None:
    """Workflow steps should enforce handler, dependency, retry, and timeout rules."""

    with pytest.raises(ValidationError):
        WorkflowStepDefinition(name="Research", kind=WorkflowStepKind.ENGINE, handler_name=None)

    with pytest.raises(ValidationError):
        build_step(depends_on=["step_a", "step_a"])

    with pytest.raises(ValidationError):
        build_step(step_id="step_a", depends_on=["step_a"])

    with pytest.raises(ValidationError):
        WorkflowStepDefinition(
            name="Research",
            kind=WorkflowStepKind.ENGINE,
            handler_name="research_engine",
            retry_limit=-1,
        )

    with pytest.raises(ValidationError):
        WorkflowStepDefinition(
            name="Research",
            kind=WorkflowStepKind.ENGINE,
            handler_name="research_engine",
            timeout_seconds=0,
        )


def test_workflow_step_definition_allows_approval_and_manual_steps_without_handler_name() -> None:
    """Approval and manual steps may omit handler names."""

    approval_step = WorkflowStepDefinition(name="Approve", kind=WorkflowStepKind.APPROVAL)
    manual_step = WorkflowStepDefinition(name="Review", kind=WorkflowStepKind.MANUAL)

    assert approval_step.handler_name is None
    assert manual_step.handler_name is None


def test_workflow_step_definition_mutable_defaults_are_not_shared() -> None:
    """Workflow step defaults should not share mutable state across instances."""

    first = build_step()
    second = build_step(name="Script", handler_name="script_engine")

    first.depends_on.append("step_a")
    first.metadata["priority"] = "high"

    assert second.depends_on == []
    assert second.metadata == {}


def test_workflow_definition_generates_expected_id_prefix() -> None:
    """Workflow definitions should generate workflow-prefixed identifiers."""

    workflow = WorkflowDefinition(name="Gaming Workflow", steps=[build_step()])

    assert workflow.id.startswith("workflow_")


def test_workflow_definition_rejects_blank_and_invalid_values() -> None:
    """Workflow definitions should reject blank names and invalid versions."""

    with pytest.raises(ValidationError):
        WorkflowDefinition(name="   ", steps=[build_step()])

    with pytest.raises(ValidationError):
        WorkflowDefinition(name="Gaming Workflow", version=0, steps=[build_step()])

    with pytest.raises(ValidationError):
        WorkflowDefinition(name="Gaming Workflow", description="   ", steps=[build_step()])


def test_workflow_definition_requires_steps_and_unique_step_ids_and_names() -> None:
    """Workflow definitions should enforce step presence and uniqueness rules."""

    with pytest.raises(ValidationError):
        WorkflowDefinition(name="Gaming Workflow", steps=[])

    first_step = build_step(step_id="step_a", name="Research")
    second_step = build_step(step_id="step_a", name="Script", handler_name="script_engine")
    with pytest.raises(ValidationError):
        WorkflowDefinition(name="Gaming Workflow", steps=[first_step, second_step])

    first_named_step = build_step(step_id="step_a", name="Research")
    second_named_step = build_step(step_id="step_b", name="  research  ", handler_name="script_engine")
    with pytest.raises(ValidationError):
        WorkflowDefinition(name="Gaming Workflow", steps=[first_named_step, second_named_step])


def test_workflow_definition_rejects_unknown_dependency_ids() -> None:
    """Workflow definitions should require dependencies to reference known step IDs."""

    first_step = build_step(step_id="step_a", name="Research")
    second_step = build_step(
        step_id="step_b",
        name="Script",
        handler_name="script_engine",
        depends_on=["missing_step"],
    )

    with pytest.raises(ValidationError):
        WorkflowDefinition(name="Gaming Workflow", steps=[first_step, second_step])


def test_workflow_definition_serializes_and_restores_predictably() -> None:
    """Workflow definitions should round-trip predictably through Pydantic serialization."""

    workflow = WorkflowDefinition(
        name="Gaming Workflow",
        status=WorkflowDefinitionStatus.READY,
        steps=[
            build_step(step_id="step_a", name="Research"),
            build_step(
                step_id="step_b",
                name="Script",
                handler_name="script_engine",
                depends_on=["step_a"],
            ),
        ],
    )

    restored = WorkflowDefinition.model_validate(workflow.model_dump())

    assert restored == workflow


def test_workflow_execution_generates_expected_id_prefix_and_defaults() -> None:
    """Workflow executions should generate workflow_execution IDs and default to pending."""

    execution = WorkflowExecution(workflow_id="workflow_123", workflow_version=1, job_id="job_123")

    assert execution.id.startswith("workflow_execution_")
    assert execution.status is WorkflowExecutionStatus.PENDING


def test_workflow_execution_rejects_blank_and_invalid_values() -> None:
    """Workflow executions should reject blank identifiers and invalid versions."""

    with pytest.raises(ValidationError):
        WorkflowExecution(workflow_id="   ", workflow_version=1, job_id="job_123")

    with pytest.raises(ValidationError):
        WorkflowExecution(workflow_id="workflow_123", workflow_version=0, job_id="job_123")

    with pytest.raises(ValidationError):
        WorkflowExecution(
            workflow_id="workflow_123",
            workflow_version=1,
            job_id="job_123",
            current_step_id="   ",
        )


def test_workflow_execution_validates_timestamp_ordering() -> None:
    """Workflow executions should enforce timestamp ordering constraints."""

    created_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    started_at = datetime(2026, 8, 4, 10, 1, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 2, tzinfo=UTC)
    execution = WorkflowExecution(
        workflow_id="workflow_123",
        workflow_version=1,
        job_id="job_123",
        created_at=created_at,
        updated_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
    )

    assert execution.started_at == started_at
    assert execution.completed_at == completed_at

    with pytest.raises(ValidationError):
        WorkflowExecution(
            workflow_id="workflow_123",
            workflow_version=1,
            job_id="job_123",
            created_at=created_at,
            updated_at=created_at,
            started_at=datetime(2026, 8, 4, 9, 59, tzinfo=UTC),
        )

    with pytest.raises(ValidationError):
        WorkflowExecution(
            workflow_id="workflow_123",
            workflow_version=1,
            job_id="job_123",
            created_at=created_at,
            updated_at=created_at,
            completed_at=datetime(2026, 8, 4, 9, 59, tzinfo=UTC),
        )

    with pytest.raises(ValidationError):
        WorkflowExecution(
            workflow_id="workflow_123",
            workflow_version=1,
            job_id="job_123",
            created_at=created_at,
            updated_at=created_at,
            started_at=started_at,
            completed_at=datetime(2026, 8, 4, 10, 0, 30, tzinfo=UTC),
        )


def test_workflow_execution_rejects_naive_timestamps() -> None:
    """Workflow executions should reject naive timestamps."""

    with pytest.raises(ValidationError):
        WorkflowExecution(
            workflow_id="workflow_123",
            workflow_version=1,
            job_id="job_123",
            created_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC).replace(tzinfo=None),
        )


def test_workflow_execution_mutable_defaults_are_not_shared() -> None:
    """Workflow execution defaults should not share mutable state."""

    first = WorkflowExecution(workflow_id="workflow_123", workflow_version=1, job_id="job_123")
    second = WorkflowExecution(workflow_id="workflow_456", workflow_version=1, job_id="job_456")

    first.step_results.append(build_workflow_step_result())
    first.metadata["status"] = "changed"

    assert second.step_results == []
    assert second.metadata == {}


def test_workflow_execution_serializes_and_restores_predictably() -> None:
    """Workflow executions should round-trip predictably through Pydantic serialization."""

    execution = WorkflowExecution(
        workflow_id="workflow_123",
        workflow_version=1,
        job_id="job_123",
        current_step_id="step_a",
        step_results=[build_workflow_step_result()],
    )

    restored = WorkflowExecution.model_validate(execution.model_dump())

    assert restored == execution


def test_approval_request_validates_fields_and_prefix() -> None:
    """Approval requests should validate required fields and generate the expected prefix."""

    request = ApprovalRequest(
        execution_id="workflow_execution_123",
        step_id="step_a",
        requested_by="operator",
        reason="Human review required.",
    )

    assert request.id.startswith("approval_request_")

    with pytest.raises(ValidationError):
        ApprovalRequest(execution_id="   ", step_id="step_a", requested_by="operator")

    with pytest.raises(ValidationError):
        ApprovalRequest(execution_id="workflow_execution_123", step_id="step_a", requested_by="   ")

    with pytest.raises(ValidationError):
        ApprovalRequest(
            execution_id="workflow_execution_123",
            step_id="step_a",
            requested_by="operator",
            reason="   ",
        )

    with pytest.raises(ValidationError):
        ApprovalRequest(
            execution_id="workflow_execution_123",
            step_id="step_a",
            requested_by="operator",
            requested_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC).replace(tzinfo=None),
        )


def test_approval_request_mutable_defaults_and_serialization() -> None:
    """Approval requests should isolate metadata and round-trip predictably."""

    first = ApprovalRequest(execution_id="workflow_execution_123", step_id="step_a", requested_by="operator")
    second = ApprovalRequest(execution_id="workflow_execution_456", step_id="step_b", requested_by="reviewer")
    first.metadata["priority"] = "high"

    restored = ApprovalRequest.model_validate(first.model_dump())

    assert second.metadata == {}
    assert restored == first


def test_approval_decision_validates_fields_and_prefix() -> None:
    """Approval decisions should validate required fields and generate the expected prefix."""

    decision = ApprovalDecision(
        request_id="approval_request_123",
        decision=ApprovalDecisionType.APPROVED,
        decided_by="operator",
        comment="Looks good.",
    )

    assert decision.id.startswith("approval_decision_")

    with pytest.raises(ValidationError):
        ApprovalDecision(request_id="   ", decision=ApprovalDecisionType.APPROVED, decided_by="operator")

    with pytest.raises(ValidationError):
        ApprovalDecision(
            request_id="approval_request_123",
            decision=ApprovalDecisionType.APPROVED,
            decided_by="   ",
        )

    with pytest.raises(ValidationError):
        ApprovalDecision(
            request_id="approval_request_123",
            decision=ApprovalDecisionType.APPROVED,
            decided_by="operator",
            comment="   ",
        )

    with pytest.raises(ValidationError):
        ApprovalDecision(
            request_id="approval_request_123",
            decision=ApprovalDecisionType.APPROVED,
            decided_by="operator",
            decided_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC).replace(tzinfo=None),
        )


def test_approval_decision_mutable_defaults_and_serialization() -> None:
    """Approval decisions should isolate metadata and round-trip predictably."""

    first = ApprovalDecision(
        request_id="approval_request_123",
        decision=ApprovalDecisionType.REJECTED,
        decided_by="operator",
    )
    second = ApprovalDecision(
        request_id="approval_request_456",
        decision=ApprovalDecisionType.APPROVED,
        decided_by="reviewer",
    )
    first.metadata["reason"] = "needs update"

    restored = ApprovalDecision.model_validate(first.model_dump())

    assert second.metadata == {}
    assert restored == first


def test_workflow_event_validates_fields_and_prefix() -> None:
    """Workflow events should validate required and optional text fields."""

    event = WorkflowEvent(
        execution_id="workflow_execution_123",
        event_type=WorkflowEventType.EXECUTION_STARTED,
        step_id="step_a",
        message="Execution started.",
    )

    assert event.id.startswith("workflow_event_")

    with pytest.raises(ValidationError):
        WorkflowEvent(execution_id="   ", event_type=WorkflowEventType.EXECUTION_STARTED)

    with pytest.raises(ValidationError):
        WorkflowEvent(
            execution_id="workflow_execution_123",
            event_type=WorkflowEventType.EXECUTION_STARTED,
            step_id="   ",
        )

    with pytest.raises(ValidationError):
        WorkflowEvent(
            execution_id="workflow_execution_123",
            event_type=WorkflowEventType.EXECUTION_STARTED,
            message="   ",
        )

    with pytest.raises(ValidationError):
        WorkflowEvent(
            execution_id="workflow_execution_123",
            event_type=WorkflowEventType.EXECUTION_STARTED,
            occurred_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC).replace(tzinfo=None),
        )


def test_workflow_event_mutable_defaults_and_serialization() -> None:
    """Workflow events should isolate data defaults and round-trip predictably."""

    first = WorkflowEvent(
        execution_id="workflow_execution_123",
        event_type=WorkflowEventType.STEP_STARTED,
    )
    second = WorkflowEvent(
        execution_id="workflow_execution_456",
        event_type=WorkflowEventType.STEP_COMPLETED,
    )
    first.data["attempt"] = 1

    restored = WorkflowEvent.model_validate(first.model_dump())

    assert second.data == {}
    assert restored == first
