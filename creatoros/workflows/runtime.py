"""In-memory workflow execution runtime foundation for CreatorOS."""

from __future__ import annotations

from creatoros.core import CreatorOSValidationError, WorkflowStateError
from creatoros.domain import utc_now
from creatoros.observability import get_logger
from creatoros.workflows.enums import (
    ApprovalDecisionType,
    WorkflowEventType,
    WorkflowExecutionStatus,
)
from creatoros.workflows.models import (
    ApprovalDecision,
    ApprovalRequest,
    WorkflowEvent,
    WorkflowExecution,
)
from creatoros.workflows.validation import (
    validate_execution_can_cancel,
    validate_execution_can_complete,
    validate_execution_can_fail,
    validate_execution_can_pause,
    validate_execution_can_resume,
    validate_execution_can_start,
    validate_transition,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="workflow_invalid_text",
            details={"field": field_name},
        )
    return normalized_value


def _validate_optional_non_blank(value: str | None, *, field_name: str) -> str | None:
    """Trim and reject blank optional text values when supplied."""

    if value is None:
        return None
    return _validate_non_blank(value, field_name=field_name)


class WorkflowRuntime:
    """Manage in-memory workflow execution state and event history."""

    def __init__(
        self,
        execution: WorkflowExecution,
    ) -> None:
        self._execution = execution.model_copy(deep=True)
        self._events: list[WorkflowEvent] = []
        self._logger = get_logger("workflows.runtime")
        self._record_event(
            WorkflowEventType.EXECUTION_CREATED,
            log_event_name=None,
        )

    @property
    def execution(self) -> WorkflowExecution:
        """Return a deep copy of the current execution state."""

        return self._execution.model_copy(deep=True)

    @property
    def events(self) -> tuple[WorkflowEvent, ...]:
        """Return immutable copies of recorded workflow events."""

        return tuple(event.model_copy(deep=True) for event in self._events)

    @property
    def status(self) -> WorkflowExecutionStatus:
        """Return the current workflow execution status."""

        return self._execution.status

    def start(self) -> WorkflowExecution:
        """Start a pending workflow execution."""

        validate_execution_can_start(self._execution)
        self._change_status(WorkflowExecutionStatus.RUNNING)
        timestamp = utc_now()
        if self._execution.started_at is None:
            self._execution.started_at = timestamp
        self._execution.updated_at = timestamp
        self._record_event(
            WorkflowEventType.EXECUTION_STARTED,
            log_event_name="workflow_execution_started",
        )
        return self.execution

    def pause(
        self,
        *,
        message: str | None = None,
    ) -> WorkflowExecution:
        """Pause a running workflow execution."""

        validate_execution_can_pause(self._execution)
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._change_status(WorkflowExecutionStatus.PAUSED)
        self._execution.updated_at = utc_now()
        self._record_event(
            WorkflowEventType.EXECUTION_PAUSED,
            message=normalized_message,
            log_event_name="workflow_execution_paused",
        )
        return self.execution

    def resume(
        self,
        *,
        message: str | None = None,
    ) -> WorkflowExecution:
        """Resume a paused or awaiting-approval workflow execution."""

        validate_execution_can_resume(self._execution)
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._change_status(WorkflowExecutionStatus.RUNNING)
        self._execution.updated_at = utc_now()
        self._record_event(
            WorkflowEventType.EXECUTION_RESUMED,
            message=normalized_message,
            log_event_name="workflow_execution_resumed",
        )
        return self.execution

    def request_approval(
        self,
        *,
        step_id: str,
        message: str | None = None,
    ) -> ApprovalRequest:
        """Transition a running execution into approval wait and create a request."""

        self._require_status(
            WorkflowExecutionStatus.RUNNING,
            code="workflow_execution_cannot_request_approval",
            action="request approval",
        )
        normalized_step_id = _validate_non_blank(step_id, field_name="step_id")
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._change_status(WorkflowExecutionStatus.AWAITING_APPROVAL)
        self._execution.current_step_id = normalized_step_id
        self._execution.updated_at = utc_now()

        request = ApprovalRequest(
            execution_id=self._execution.id,
            step_id=normalized_step_id,
            requested_by="workflow_runtime",
            reason=normalized_message,
        )
        self._record_event(
            WorkflowEventType.APPROVAL_REQUESTED,
            step_id=normalized_step_id,
            message=normalized_message,
            log_event_name="workflow_approval_requested",
        )
        return request.model_copy(deep=True)

    def approve(
        self,
        request: ApprovalRequest,
        *,
        decided_by: str,
        comment: str | None = None,
    ) -> ApprovalDecision:
        """Approve a pending approval request and resume execution."""

        self._require_status(
            WorkflowExecutionStatus.AWAITING_APPROVAL,
            code="workflow_execution_cannot_approve",
            action="approve request",
        )
        self._validate_approval_request_identity(request)
        normalized_decided_by = _validate_non_blank(decided_by, field_name="decided_by")
        normalized_comment = _validate_optional_non_blank(comment, field_name="comment")

        decision = ApprovalDecision(
            request_id=request.id,
            decision=ApprovalDecisionType.APPROVED,
            decided_by=normalized_decided_by,
            comment=normalized_comment,
        )
        self._change_status(WorkflowExecutionStatus.RUNNING)
        self._execution.updated_at = utc_now()
        self._record_event(
            WorkflowEventType.APPROVAL_APPROVED,
            step_id=request.step_id,
            log_event_name="workflow_approval_approved",
        )
        return decision.model_copy(deep=True)

    def reject(
        self,
        request: ApprovalRequest,
        *,
        decided_by: str,
        comment: str | None = None,
    ) -> ApprovalDecision:
        """Reject a pending approval request and fail the execution."""

        self._require_status(
            WorkflowExecutionStatus.AWAITING_APPROVAL,
            code="workflow_execution_cannot_reject",
            action="reject request",
        )
        self._validate_approval_request_identity(request)
        normalized_decided_by = _validate_non_blank(decided_by, field_name="decided_by")
        normalized_comment = _validate_optional_non_blank(comment, field_name="comment")

        decision = ApprovalDecision(
            request_id=request.id,
            decision=ApprovalDecisionType.REJECTED,
            decided_by=normalized_decided_by,
            comment=normalized_comment,
        )
        self._change_status(WorkflowExecutionStatus.FAILED)
        timestamp = utc_now()
        self._execution.completed_at = timestamp
        self._execution.updated_at = timestamp
        self._record_event(
            WorkflowEventType.APPROVAL_REJECTED,
            step_id=request.step_id,
            log_event_name="workflow_approval_rejected",
        )
        self._record_event(
            WorkflowEventType.EXECUTION_FAILED,
            step_id=request.step_id,
            log_event_name="workflow_execution_failed",
        )
        return decision.model_copy(deep=True)

    def complete(
        self,
        *,
        message: str | None = None,
    ) -> WorkflowExecution:
        """Complete a running workflow execution."""

        validate_execution_can_complete(self._execution)
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._change_status(WorkflowExecutionStatus.COMPLETED)
        timestamp = utc_now()
        self._execution.completed_at = timestamp
        self._execution.updated_at = timestamp
        self._execution.current_step_id = None
        self._record_event(
            WorkflowEventType.EXECUTION_COMPLETED,
            message=normalized_message,
            log_event_name="workflow_execution_completed",
        )
        return self.execution

    def fail(
        self,
        *,
        message: str | None = None,
        step_id: str | None = None,
        data: dict[str, object] | None = None,
    ) -> WorkflowExecution:
        """Fail a running or awaiting-approval workflow execution."""

        validate_execution_can_fail(self._execution)
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        normalized_step_id = _validate_optional_non_blank(step_id, field_name="step_id")
        self._change_status(WorkflowExecutionStatus.FAILED)
        timestamp = utc_now()
        self._execution.completed_at = timestamp
        self._execution.updated_at = timestamp
        if normalized_step_id is not None:
            self._execution.current_step_id = normalized_step_id
        event_data = {} if data is None else dict(data)
        self._record_event(
            WorkflowEventType.EXECUTION_FAILED,
            step_id=normalized_step_id,
            message=normalized_message,
            data=event_data,
            log_event_name="workflow_execution_failed",
        )
        return self.execution

    def cancel(
        self,
        *,
        message: str | None = None,
    ) -> WorkflowExecution:
        """Cancel a non-terminal workflow execution."""

        validate_execution_can_cancel(self._execution)
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._change_status(WorkflowExecutionStatus.CANCELLED)
        timestamp = utc_now()
        self._execution.completed_at = timestamp
        self._execution.updated_at = timestamp
        self._record_event(
            WorkflowEventType.EXECUTION_CANCELLED,
            message=normalized_message,
            log_event_name="workflow_execution_cancelled",
        )
        return self.execution

    def record_step_started(
        self,
        step_id: str,
        *,
        message: str | None = None,
        data: dict[str, object] | None = None,
    ) -> WorkflowEvent:
        """Record that a workflow step has started."""

        self._require_status(
            WorkflowExecutionStatus.RUNNING,
            code="workflow_execution_cannot_record_step_started",
            action="record step started",
        )
        normalized_step_id = _validate_non_blank(step_id, field_name="step_id")
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._execution.current_step_id = normalized_step_id
        self._execution.updated_at = utc_now()
        return self._record_event(
            WorkflowEventType.STEP_STARTED,
            step_id=normalized_step_id,
            message=normalized_message,
            data={} if data is None else dict(data),
            log_event_name=None,
        )

    def record_step_completed(
        self,
        step_id: str,
        *,
        message: str | None = None,
        data: dict[str, object] | None = None,
    ) -> WorkflowEvent:
        """Record that a workflow step has completed."""

        self._require_status(
            WorkflowExecutionStatus.RUNNING,
            code="workflow_execution_cannot_record_step_completed",
            action="record step completed",
        )
        normalized_step_id = _validate_non_blank(step_id, field_name="step_id")
        if (
            self._execution.current_step_id is not None
            and self._execution.current_step_id != normalized_step_id
        ):
            raise WorkflowStateError(
                "step_id does not match current_step_id",
                code="workflow_step_mismatch",
                details={
                    "current_step_id": self._execution.current_step_id,
                    "target_step_id": normalized_step_id,
                },
            )

        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._execution.updated_at = utc_now()
        self._execution.current_step_id = None
        return self._record_event(
            WorkflowEventType.STEP_COMPLETED,
            step_id=normalized_step_id,
            message=normalized_message,
            data={} if data is None else dict(data),
            log_event_name=None,
        )

    def record_step_failed(
        self,
        step_id: str,
        *,
        message: str | None = None,
        data: dict[str, object] | None = None,
    ) -> WorkflowEvent:
        """Record that a workflow step has failed without failing the workflow."""

        self._require_status(
            WorkflowExecutionStatus.RUNNING,
            code="workflow_execution_cannot_record_step_failed",
            action="record step failed",
        )
        normalized_step_id = _validate_non_blank(step_id, field_name="step_id")
        normalized_message = _validate_optional_non_blank(message, field_name="message")
        self._execution.updated_at = utc_now()
        return self._record_event(
            WorkflowEventType.STEP_FAILED,
            step_id=normalized_step_id,
            message=normalized_message,
            data={} if data is None else dict(data),
            log_event_name=None,
        )

    def _change_status(self, target: WorkflowExecutionStatus) -> None:
        """Validate and apply an execution status transition."""

        validate_transition(self._execution.status, target)
        self._execution.status = target

    def _record_event(
        self,
        event_type: WorkflowEventType,
        *,
        step_id: str | None = None,
        message: str | None = None,
        data: dict[str, object] | None = None,
        log_event_name: str | None,
    ) -> WorkflowEvent:
        """Create, store, and optionally log a workflow event."""

        event = WorkflowEvent(
            execution_id=self._execution.id,
            event_type=event_type,
            step_id=step_id,
            message=message,
            data={} if data is None else dict(data),
        )
        self._events.append(event)
        if log_event_name is not None:
            self._logger.info(
                log_event_name,
                execution_id=self._execution.id,
                workflow_id=self._execution.workflow_id,
                workflow_status=self._execution.status.value,
                step_id=step_id,
            )
        return event.model_copy(deep=True)

    def _require_status(
        self,
        expected_status: WorkflowExecutionStatus,
        *,
        code: str,
        action: str,
    ) -> None:
        """Require the execution to currently be in the expected status."""

        if self._execution.status is not expected_status:
            raise WorkflowStateError(
                f"Workflow execution cannot {action} from '{self._execution.status.value}'",
                code=code,
                details={"current_status": self._execution.status.value},
            )

    def _validate_approval_request_identity(self, request: ApprovalRequest) -> None:
        """Ensure an approval request belongs to the current execution and step."""

        if request.execution_id != self._execution.id:
            raise WorkflowStateError(
                "approval request execution_id does not match the current execution",
                code="workflow_approval_request_mismatch",
                details={
                    "execution_id": self._execution.id,
                    "request_execution_id": request.execution_id,
                },
            )

        if self._execution.current_step_id is None or request.step_id != self._execution.current_step_id:
            raise WorkflowStateError(
                "approval request step_id does not match the current workflow step",
                code="workflow_approval_request_mismatch",
                details={
                    "current_step_id": self._execution.current_step_id,
                    "request_step_id": request.step_id,
                },
            )


__all__ = ["WorkflowRuntime"]
