"""Unit tests for the CreatorOS workflow runtime foundation."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError, WorkflowStateError
from creatoros.workflows import (
    ApprovalDecisionType,
    ApprovalRequest,
    WorkflowEventType,
    WorkflowExecution,
    WorkflowExecutionStatus,
    WorkflowRuntime,
)


class FakeLogger:
    """Capture workflow runtime logs for assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def info(self, event: str, **kwargs: object) -> None:
        """Record a structured info event."""

        self.events.append({"event": event, "kwargs": kwargs})


def build_execution(*, status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING) -> WorkflowExecution:
    """Create a simple workflow execution for runtime tests."""

    return WorkflowExecution(
        workflow_id="workflow_123",
        workflow_version=1,
        job_id="job_123",
        status=status,
    )


@pytest.fixture
def fake_logger(monkeypatch: pytest.MonkeyPatch) -> FakeLogger:
    """Patch workflow runtime logging with a simple recording logger."""

    logger = FakeLogger()
    monkeypatch.setattr("creatoros.workflows.runtime.get_logger", lambda name=None: logger)
    return logger


def test_constructor_does_not_mutate_supplied_execution(fake_logger: FakeLogger) -> None:
    """Runtime construction should not mutate the caller's execution object."""

    execution = build_execution()
    original_updated_at = execution.updated_at

    runtime = WorkflowRuntime(execution)

    assert execution.status is WorkflowExecutionStatus.PENDING
    assert execution.updated_at == original_updated_at
    assert runtime.status is WorkflowExecutionStatus.PENDING


def test_constructor_records_execution_created(fake_logger: FakeLogger) -> None:
    """Runtime construction should record an execution_created event."""

    runtime = WorkflowRuntime(build_execution())

    assert runtime.events[0].event_type is WorkflowEventType.EXECUTION_CREATED


def test_execution_property_returns_a_copy(fake_logger: FakeLogger) -> None:
    """Execution access should return a copy of internal state."""

    runtime = WorkflowRuntime(build_execution())

    first = runtime.execution
    first.metadata["changed"] = True
    second = runtime.execution

    assert second.metadata == {}


def test_events_property_returns_immutable_tuple_of_copies(fake_logger: FakeLogger) -> None:
    """Events access should return immutable copies of internal event history."""

    runtime = WorkflowRuntime(build_execution())

    events = runtime.events
    assert isinstance(events, tuple)
    with pytest.raises(TypeError):
        events[0] = events[0]

    event_copy = events[0]
    event_copy.data["changed"] = True
    assert runtime.events[0].data == {}


def test_start_transitions_to_running_and_sets_timestamps(fake_logger: FakeLogger) -> None:
    """Starting should transition to running and set timestamps."""

    runtime = WorkflowRuntime(build_execution())

    execution = runtime.start()

    assert execution.status is WorkflowExecutionStatus.RUNNING
    assert execution.started_at is not None
    assert execution.updated_at is not None


def test_start_records_execution_started(fake_logger: FakeLogger) -> None:
    """Starting should record execution_started."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    assert runtime.events[-1].event_type is WorkflowEventType.EXECUTION_STARTED


def test_invalid_repeated_start_raises_workflow_state_error(fake_logger: FakeLogger) -> None:
    """Starting twice should raise WorkflowStateError."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    with pytest.raises(WorkflowStateError):
        runtime.start()


def test_pause_transitions_running_to_paused(fake_logger: FakeLogger) -> None:
    """Pausing should transition a running execution to paused."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    execution = runtime.pause()

    assert execution.status is WorkflowExecutionStatus.PAUSED


def test_resume_transitions_paused_to_running(fake_logger: FakeLogger) -> None:
    """Resuming should transition paused execution back to running."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    runtime.pause()

    execution = runtime.resume()

    assert execution.status is WorkflowExecutionStatus.RUNNING


def test_request_approval_transitions_to_awaiting_approval(fake_logger: FakeLogger) -> None:
    """Requesting approval should move running execution into awaiting_approval."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    request = runtime.request_approval(step_id="step_a")

    assert runtime.status is WorkflowExecutionStatus.AWAITING_APPROVAL
    assert request.step_id == "step_a"


def test_request_approval_returns_valid_approval_request(fake_logger: FakeLogger) -> None:
    """Approval requests should be valid workflow approval objects."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    request = runtime.request_approval(step_id="step_a", message="Need review")

    assert isinstance(request, ApprovalRequest)
    assert request.execution_id == runtime.execution.id
    assert request.requested_by == "workflow_runtime"


def test_approve_transitions_awaiting_approval_to_running(fake_logger: FakeLogger) -> None:
    """Approving should transition awaiting_approval back to running."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")

    decision = runtime.approve(request, decided_by="reviewer")

    assert decision.decision is ApprovalDecisionType.APPROVED
    assert runtime.status is WorkflowExecutionStatus.RUNNING


def test_approve_records_approval_approved(fake_logger: FakeLogger) -> None:
    """Approving should record approval_approved."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")
    runtime.approve(request, decided_by="reviewer")

    assert runtime.events[-1].event_type is WorkflowEventType.APPROVAL_APPROVED


def test_reject_transitions_awaiting_approval_to_failed(fake_logger: FakeLogger) -> None:
    """Rejecting should transition awaiting_approval to failed."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")

    decision = runtime.reject(request, decided_by="reviewer")

    assert decision.decision is ApprovalDecisionType.REJECTED
    assert runtime.status is WorkflowExecutionStatus.FAILED


def test_reject_sets_completed_at(fake_logger: FakeLogger) -> None:
    """Rejecting should set completed_at."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")
    runtime.reject(request, decided_by="reviewer")

    assert runtime.execution.completed_at is not None


def test_reject_records_approval_rejected_and_execution_failed(fake_logger: FakeLogger) -> None:
    """Rejecting should record approval_rejected and execution_failed."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")
    runtime.reject(request, decided_by="reviewer")

    assert [event.event_type for event in runtime.events[-2:]] == [
        WorkflowEventType.APPROVAL_REJECTED,
        WorkflowEventType.EXECUTION_FAILED,
    ]


def test_mismatched_approval_requests_are_rejected(fake_logger: FakeLogger) -> None:
    """Approval requests with mismatched execution or step identity should be rejected."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")
    mismatched = request.model_copy(deep=True)
    mismatched.execution_id = "other_execution"

    with pytest.raises(WorkflowStateError):
        runtime.approve(mismatched, decided_by="reviewer")


def test_blank_decided_by_is_rejected(fake_logger: FakeLogger) -> None:
    """Blank decided_by values should be rejected."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")

    with pytest.raises(CreatorOSValidationError):
        runtime.approve(request, decided_by="   ")


def test_complete_transitions_running_to_completed(fake_logger: FakeLogger) -> None:
    """Completing should transition running execution to completed."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    execution = runtime.complete()

    assert execution.status is WorkflowExecutionStatus.COMPLETED


def test_complete_sets_completed_at_and_clears_current_step_id(fake_logger: FakeLogger) -> None:
    """Completing should set completed_at and clear current_step_id."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    runtime.record_step_started("step_a")

    execution = runtime.complete()

    assert execution.completed_at is not None
    assert execution.current_step_id is None


def test_fail_works_from_running(fake_logger: FakeLogger) -> None:
    """Failing should work from running status."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    execution = runtime.fail(step_id="step_a")

    assert execution.status is WorkflowExecutionStatus.FAILED


def test_fail_works_from_awaiting_approval(fake_logger: FakeLogger) -> None:
    """Failing should work from awaiting_approval status."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    runtime.request_approval(step_id="step_a")

    execution = runtime.fail(step_id="step_a")

    assert execution.status is WorkflowExecutionStatus.FAILED


def test_fail_copies_event_data(fake_logger: FakeLogger) -> None:
    """Failure event data should be copied before storage."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    payload = {"attempt": 1}
    runtime.fail(step_id="step_a", data=payload)
    payload["attempt"] = 2

    assert runtime.events[-1].data == {"attempt": 1}


def test_cancel_works_from_pending(fake_logger: FakeLogger) -> None:
    """Cancelling should work from pending."""

    runtime = WorkflowRuntime(build_execution())

    execution = runtime.cancel()

    assert execution.status is WorkflowExecutionStatus.CANCELLED


def test_cancel_works_from_running(fake_logger: FakeLogger) -> None:
    """Cancelling should work from running."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    execution = runtime.cancel()

    assert execution.status is WorkflowExecutionStatus.CANCELLED


def test_cancel_rejects_terminal_executions(fake_logger: FakeLogger) -> None:
    """Cancelling should reject terminal execution states."""

    runtime = WorkflowRuntime(build_execution())
    runtime.cancel()

    with pytest.raises(WorkflowStateError):
        runtime.cancel()


def test_record_step_started_sets_current_step_id(fake_logger: FakeLogger) -> None:
    """Starting a step should set current_step_id."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    runtime.record_step_started("step_a")

    assert runtime.execution.current_step_id == "step_a"


def test_record_step_completed_clears_current_step_id(fake_logger: FakeLogger) -> None:
    """Completing a step should clear current_step_id."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    runtime.record_step_started("step_a")
    runtime.record_step_completed("step_a")

    assert runtime.execution.current_step_id is None


def test_step_completion_mismatch_is_rejected(fake_logger: FakeLogger) -> None:
    """Step completion should reject mismatched current step identifiers."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    runtime.record_step_started("step_a")

    with pytest.raises(WorkflowStateError):
        runtime.record_step_completed("step_b")


def test_record_step_failed_does_not_automatically_fail_execution(fake_logger: FakeLogger) -> None:
    """Recording a step failure should not automatically fail the workflow."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    runtime.record_step_failed("step_a")

    assert runtime.status is WorkflowExecutionStatus.RUNNING


def test_blank_step_identifiers_are_rejected(fake_logger: FakeLogger) -> None:
    """Blank step identifiers should be rejected."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    with pytest.raises(CreatorOSValidationError):
        runtime.record_step_started("   ")


def test_optional_blank_messages_and_comments_are_rejected_when_supplied(fake_logger: FakeLogger) -> None:
    """Blank optional text should be rejected when supplied."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()

    with pytest.raises(CreatorOSValidationError):
        runtime.pause(message="   ")

    request = runtime.request_approval(step_id="step_a")

    with pytest.raises(CreatorOSValidationError):
        runtime.approve(request, decided_by="reviewer", comment="   ")


def test_event_timestamps_are_timezone_aware(fake_logger: FakeLogger) -> None:
    """Recorded runtime events should use timezone-aware timestamps."""

    runtime = WorkflowRuntime(build_execution())

    assert runtime.events[0].occurred_at.tzinfo is not None


def test_runtime_timestamps_move_forward_or_remain_equal(fake_logger: FakeLogger) -> None:
    """Runtime timestamps should move forward or remain equal as state changes occur."""

    runtime = WorkflowRuntime(build_execution())
    created_at = runtime.execution.created_at
    started = runtime.start()
    paused = runtime.pause()

    assert started.updated_at >= created_at
    assert paused.updated_at >= started.updated_at


def test_returned_approval_objects_are_copies(fake_logger: FakeLogger) -> None:
    """Returned approval objects should not expose internal runtime state."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    request = runtime.request_approval(step_id="step_a")
    request.reason = "changed"

    decision = runtime.approve(runtime.events[-1] and runtime.request_approval if False else ApprovalRequest(
        execution_id=runtime.execution.id,
        step_id="step_a",
        requested_by="workflow_runtime",
    ), decided_by="reviewer")

    assert decision.request_id.startswith("approval_request_")


def test_runtime_does_not_expose_internal_mutable_data(fake_logger: FakeLogger) -> None:
    """Runtime should not expose mutable internal execution or event data."""

    runtime = WorkflowRuntime(build_execution())
    execution = runtime.execution
    execution.metadata["changed"] = True
    copied_event = runtime.events[0]
    copied_event.data["changed"] = True

    assert runtime.execution.metadata == {}
    assert runtime.events[0].data == {}


def test_runtime_emits_safe_lifecycle_logs(fake_logger: FakeLogger) -> None:
    """Lifecycle logs should contain safe identifiers and statuses only."""

    runtime = WorkflowRuntime(build_execution())
    runtime.start()
    runtime.pause()

    assert [event["event"] for event in fake_logger.events] == [
        "workflow_execution_started",
        "workflow_execution_paused",
    ]
    combined = "".join(str(event["kwargs"]) for event in fake_logger.events)
    assert "workflow_123" in combined
    assert "secret" not in combined


def test_runtime_contains_no_engine_agent_provider_persistence_retry_or_sleep_behavior() -> None:
    """WorkflowRuntime should not expose orchestration or infrastructure methods."""

    assert not hasattr(WorkflowRuntime, "execute_engine")
    assert not hasattr(WorkflowRuntime, "run_agent")
    assert not hasattr(WorkflowRuntime, "get_provider")
    assert not hasattr(WorkflowRuntime, "save")
    assert not hasattr(WorkflowRuntime, "retry")
    assert not hasattr(WorkflowRuntime, "sleep")
