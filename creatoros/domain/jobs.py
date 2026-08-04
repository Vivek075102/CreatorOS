"""Job-oriented domain models for CreatorOS."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from creatoros.domain.base import CreatorOSModel, ensure_aware_utc_datetime, generate_id, utc_now
from creatoros.domain.enums import (
    ApprovalStatus,
    ContentPlatform,
    WorkflowStatus,
    WorkflowStepStatus,
)


class ContentJob(CreatorOSModel):
    """Represents a unit of content workflow execution."""

    id: str = Field(default_factory=lambda: generate_id("job"))
    workflow_name: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    platform: ContentPlatform
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_step_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("workflow_name")
    @classmethod
    def validate_workflow_name(cls, value: str) -> str:
        """Reject blank workflow names."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("workflow_name must not be blank")
        return normalized_value

    @field_validator("created_at", "updated_at", "started_at", "completed_at")
    @classmethod
    def validate_datetimes(
        cls,
        value: datetime | None,
        info,
    ) -> datetime | None:
        """Ensure all supplied datetimes are timezone-aware."""

        if value is None:
            return None
        return ensure_aware_utc_datetime(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_temporal_order(self) -> ContentJob:
        """Validate temporal relationships for job timestamps."""

        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not be earlier than created_at")

        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at must not be earlier than created_at")

        return self


class WorkflowStepResult(CreatorOSModel):
    """Represents the result of a workflow step execution."""

    id: str = Field(default_factory=lambda: generate_id("step_result"))
    job_id: str
    step_name: str
    status: WorkflowStepStatus
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output: dict[str, object] = Field(default_factory=dict)
    error: dict[str, object] | None = None
    retry_count: int = 0

    @field_validator("job_id", "step_name")
    @classmethod
    def validate_non_blank_strings(cls, value: str, info) -> str:
        """Reject blank string identifiers and names."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized_value

    @field_validator("retry_count")
    @classmethod
    def validate_retry_count(cls, value: int) -> int:
        """Ensure retry counts are not negative."""

        if value < 0:
            raise ValueError("retry_count must be zero or greater")
        return value

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_datetimes(
        cls,
        value: datetime | None,
        info,
    ) -> datetime | None:
        """Ensure workflow step datetimes are timezone-aware."""

        if value is None:
            return None
        return ensure_aware_utc_datetime(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_cross_field_constraints(self) -> WorkflowStepResult:
        """Validate cross-field workflow step invariants."""

        if self.completed_at is not None and self.started_at is None:
            raise ValueError("completed_at cannot be supplied without started_at")

        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at must not be earlier than started_at")

        if (
            self.status == WorkflowStepStatus.AWAITING_APPROVAL
            and self.approval_status != ApprovalStatus.PENDING
        ):
            raise ValueError("awaiting_approval status requires pending approval")

        if (
            self.approval_status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}
            and self.status == WorkflowStepStatus.PENDING
        ):
            raise ValueError("approved or rejected approval_status is incompatible with pending status")

        return self
