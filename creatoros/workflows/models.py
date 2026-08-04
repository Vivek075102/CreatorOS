"""Workflow domain data contracts for CreatorOS."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from creatoros.domain import CreatorOSModel, WorkflowStepResult, generate_id, utc_now
from creatoros.domain.base import ensure_aware_utc_datetime
from creatoros.workflows.enums import (
    ApprovalDecisionType,
    FailureBehavior,
    WorkflowDefinitionStatus,
    WorkflowEventType,
    WorkflowExecutionStatus,
    WorkflowStepKind,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank required textual values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _validate_optional_non_blank(value: str | None, *, field_name: str) -> str | None:
    """Trim and reject blank optional textual values when supplied."""

    if value is None:
        return None
    return _validate_non_blank(value, field_name=field_name)


class WorkflowStepDefinition(CreatorOSModel):
    """Declarative definition of a single workflow step."""

    id: str = Field(default_factory=lambda: generate_id("workflow_step"))
    name: str
    kind: WorkflowStepKind
    handler_name: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    retry_limit: int = 0
    timeout_seconds: float | None = None
    failure_behavior: FailureBehavior = FailureBehavior.STOP
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str, info) -> str:
        """Trim and reject blank step names."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("handler_name")
    @classmethod
    def validate_handler_name(cls, value: str | None, info) -> str | None:
        """Trim and reject blank optional handler names."""

        return _validate_optional_non_blank(value, field_name=info.field_name)

    @field_validator("depends_on")
    @classmethod
    def validate_depends_on(cls, value: list[str]) -> list[str]:
        """Require unique non-blank dependency identifiers."""

        normalized_values = [_validate_non_blank(item, field_name="depends_on") for item in value]
        if len(normalized_values) != len(set(normalized_values)):
            raise ValueError("depends_on values must be unique")
        return normalized_values

    @field_validator("retry_limit")
    @classmethod
    def validate_retry_limit(cls, value: int) -> int:
        """Require retry limits to be zero or greater."""

        if value < 0:
            raise ValueError("retry_limit must be zero or greater")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: float | None) -> float | None:
        """Require positive timeout values when supplied."""

        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return value

    @model_validator(mode="after")
    def validate_cross_field_constraints(self) -> WorkflowStepDefinition:
        """Validate workflow-step invariants that depend on multiple fields."""

        if self.kind is WorkflowStepKind.ENGINE and self.handler_name is None:
            raise ValueError("engine steps require handler_name")

        if self.id in self.depends_on:
            raise ValueError("a step must not depend on itself")

        return self


class WorkflowDefinition(CreatorOSModel):
    """Declarative workflow definition containing ordered step contracts."""

    id: str = Field(default_factory=lambda: generate_id("workflow"))
    name: str
    version: int = 1
    status: WorkflowDefinitionStatus = WorkflowDefinitionStatus.DRAFT
    description: str | None = None
    steps: list[WorkflowStepDefinition]
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str, info) -> str:
        """Trim and reject blank workflow names."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None, info) -> str | None:
        """Trim and reject blank workflow descriptions when supplied."""

        return _validate_optional_non_blank(value, field_name=info.field_name)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        """Require workflow versions to be one or greater."""

        if value < 1:
            raise ValueError("version must be greater than or equal to 1")
        return value

    @model_validator(mode="after")
    def validate_steps(self) -> WorkflowDefinition:
        """Validate workflow-step uniqueness and dependency references."""

        if not self.steps:
            raise ValueError("steps must contain at least one step")

        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("step IDs must be unique")

        normalized_names = [step.name.strip().casefold() for step in self.steps]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("step names must be unique after trimming and case normalization")

        step_id_set = set(step_ids)
        for step in self.steps:
            for dependency_id in step.depends_on:
                if dependency_id not in step_id_set:
                    raise ValueError("every depends_on reference must match a step ID in the workflow")

        return self


class WorkflowExecution(CreatorOSModel):
    """Serializable contract representing one workflow execution instance."""

    id: str = Field(default_factory=lambda: generate_id("workflow_execution"))
    workflow_id: str
    workflow_version: int
    job_id: str
    status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING
    current_step_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    step_results: list[WorkflowStepResult] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("workflow_id", "job_id")
    @classmethod
    def validate_required_identifiers(cls, value: str, info) -> str:
        """Trim and reject blank required identifiers."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("current_step_id")
    @classmethod
    def validate_current_step_id(cls, value: str | None, info) -> str | None:
        """Trim and reject blank optional current step identifiers."""

        return _validate_optional_non_blank(value, field_name=info.field_name)

    @field_validator("workflow_version")
    @classmethod
    def validate_workflow_version(cls, value: int) -> int:
        """Require workflow versions to be one or greater."""

        if value < 1:
            raise ValueError("workflow_version must be greater than or equal to 1")
        return value

    @field_validator("created_at", "updated_at", "started_at", "completed_at")
    @classmethod
    def validate_datetimes(cls, value: datetime | None, info) -> datetime | None:
        """Require timezone-aware execution timestamps."""

        if value is None:
            return None
        return ensure_aware_utc_datetime(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_temporal_order(self) -> WorkflowExecution:
        """Validate cross-field execution timestamp ordering."""

        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not be earlier than created_at")

        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at must not be earlier than created_at")

        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at must not be earlier than started_at")

        return self


class ApprovalRequest(CreatorOSModel):
    """Serializable request for human workflow approval."""

    id: str = Field(default_factory=lambda: generate_id("approval_request"))
    execution_id: str
    step_id: str
    requested_at: datetime = Field(default_factory=utc_now)
    requested_by: str
    reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("execution_id", "step_id", "requested_by")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required approval request fields."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None, info) -> str | None:
        """Trim and reject blank optional approval reasons."""

        return _validate_optional_non_blank(value, field_name=info.field_name)

    @field_validator("requested_at")
    @classmethod
    def validate_requested_at(cls, value: datetime, info) -> datetime:
        """Require a timezone-aware request timestamp."""

        return ensure_aware_utc_datetime(value, field_name=info.field_name)


class ApprovalDecision(CreatorOSModel):
    """Serializable human decision for a workflow approval request."""

    id: str = Field(default_factory=lambda: generate_id("approval_decision"))
    request_id: str
    decision: ApprovalDecisionType
    decided_at: datetime = Field(default_factory=utc_now)
    decided_by: str
    comment: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("request_id", "decided_by")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required approval decision fields."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None, info) -> str | None:
        """Trim and reject blank optional decision comments."""

        return _validate_optional_non_blank(value, field_name=info.field_name)

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime, info) -> datetime:
        """Require a timezone-aware decision timestamp."""

        return ensure_aware_utc_datetime(value, field_name=info.field_name)


class WorkflowEvent(CreatorOSModel):
    """Serializable event emitted during workflow execution history."""

    id: str = Field(default_factory=lambda: generate_id("workflow_event"))
    execution_id: str
    event_type: WorkflowEventType
    occurred_at: datetime = Field(default_factory=utc_now)
    step_id: str | None = None
    message: str | None = None
    data: dict[str, object] = Field(default_factory=dict)

    @field_validator("execution_id")
    @classmethod
    def validate_execution_id(cls, value: str, info) -> str:
        """Trim and reject blank execution identifiers."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("step_id", "message")
    @classmethod
    def validate_optional_text(cls, value: str | None, info) -> str | None:
        """Trim and reject blank optional event text fields."""

        return _validate_optional_non_blank(value, field_name=info.field_name)

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime, info) -> datetime:
        """Require a timezone-aware event timestamp."""

        return ensure_aware_utc_datetime(value, field_name=info.field_name)


__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "WorkflowDefinition",
    "WorkflowEvent",
    "WorkflowExecution",
    "WorkflowStepDefinition",
]
