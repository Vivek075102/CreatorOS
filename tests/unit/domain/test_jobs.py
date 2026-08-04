"""Unit tests for CreatorOS job-oriented domain models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from creatoros.domain.enums import (
    ApprovalStatus,
    ContentPlatform,
    WorkflowStatus,
    WorkflowStepStatus,
)
from creatoros.domain.jobs import ContentJob, WorkflowStepResult


def aware_datetime(hour: int) -> datetime:
    """Create a timezone-aware UTC datetime for deterministic tests."""

    return datetime(2026, 8, 4, hour, 0, tzinfo=UTC)


def test_content_job_default_id_starts_with_job() -> None:
    """Content jobs should generate job-prefixed identifiers by default."""

    job = ContentJob(platform=ContentPlatform.YOUTUBE_SHORTS, workflow_name="gaming_short")

    assert job.id.startswith("job_")


def test_content_job_default_timestamps_are_timezone_aware() -> None:
    """Default timestamps should be timezone-aware."""

    job = ContentJob(platform=ContentPlatform.YOUTUBE_SHORTS, workflow_name="gaming_short")

    assert job.created_at.tzinfo is not None
    assert job.updated_at.tzinfo is not None


def test_content_job_default_status_is_pending() -> None:
    """Content jobs should default to pending workflow status."""

    job = ContentJob(platform=ContentPlatform.YOUTUBE_SHORTS, workflow_name="gaming_short")

    assert job.status == WorkflowStatus.PENDING


def test_content_job_metadata_dictionaries_are_not_shared_between_instances() -> None:
    """Mutable metadata should not be shared across instances."""

    first = ContentJob(platform=ContentPlatform.YOUTUBE_SHORTS, workflow_name="gaming_short")
    second = ContentJob(platform=ContentPlatform.TIKTOK, workflow_name="gaming_fact")

    first.metadata["key"] = "value"

    assert second.metadata == {}


def test_content_job_blank_workflow_name_is_rejected() -> None:
    """Blank workflow names should not validate."""

    with pytest.raises(ValidationError):
        ContentJob(platform=ContentPlatform.YOUTUBE_SHORTS, workflow_name="   ")


def test_content_job_naive_datetimes_are_rejected() -> None:
    """Naive datetimes should be rejected."""

    naive_datetime = datetime.fromisoformat("2026-08-04T10:00:00")

    with pytest.raises(ValidationError):
        ContentJob(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            workflow_name="gaming_short",
            created_at=naive_datetime,
        )


def test_content_job_started_at_before_created_at_is_rejected() -> None:
    """started_at must not be earlier than created_at."""

    with pytest.raises(ValidationError):
        ContentJob(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            workflow_name="gaming_short",
            created_at=aware_datetime(10),
            started_at=aware_datetime(9),
        )


def test_content_job_completed_at_before_created_at_is_rejected() -> None:
    """completed_at must not be earlier than created_at."""

    with pytest.raises(ValidationError):
        ContentJob(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            workflow_name="gaming_short",
            created_at=aware_datetime(10),
            completed_at=aware_datetime(9),
        )


def test_valid_content_job_serializes_and_restores_predictably() -> None:
    """Valid content jobs should round-trip through Pydantic serialization."""

    job = ContentJob(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        workflow_name="gaming_short",
        created_at=aware_datetime(10),
        updated_at=aware_datetime(11),
        started_at=aware_datetime(10),
        metadata={"series": "facts"},
    )

    restored = ContentJob.model_validate(job.model_dump())

    assert restored == job


def test_workflow_step_result_default_id_starts_with_step_result() -> None:
    """Workflow step results should generate step_result-prefixed identifiers by default."""

    result = WorkflowStepResult(job_id="job_123", step_name="research", status=WorkflowStepStatus.PENDING)

    assert result.id.startswith("step_result_")


def test_workflow_step_result_blank_job_id_is_rejected() -> None:
    """Blank job identifiers should not validate."""

    with pytest.raises(ValidationError):
        WorkflowStepResult(job_id="   ", step_name="research", status=WorkflowStepStatus.PENDING)


def test_workflow_step_result_blank_step_name_is_rejected() -> None:
    """Blank step names should not validate."""

    with pytest.raises(ValidationError):
        WorkflowStepResult(job_id="job_123", step_name="   ", status=WorkflowStepStatus.PENDING)


def test_workflow_step_result_negative_retry_count_is_rejected() -> None:
    """Retry counts must not be negative."""

    with pytest.raises(ValidationError):
        WorkflowStepResult(
            job_id="job_123",
            step_name="research",
            status=WorkflowStepStatus.PENDING,
            retry_count=-1,
        )


def test_workflow_step_result_output_dictionaries_are_not_shared_between_instances() -> None:
    """Mutable output payloads should not be shared."""

    first = WorkflowStepResult(job_id="job_123", step_name="research", status=WorkflowStepStatus.PENDING)
    second = WorkflowStepResult(job_id="job_456", step_name="script", status=WorkflowStepStatus.RUNNING)

    first.output["key"] = "value"

    assert second.output == {}


def test_workflow_step_result_completed_at_without_started_at_is_rejected() -> None:
    """completed_at requires started_at."""

    with pytest.raises(ValidationError):
        WorkflowStepResult(
            job_id="job_123",
            step_name="research",
            status=WorkflowStepStatus.COMPLETED,
            completed_at=aware_datetime(10),
        )


def test_workflow_step_result_completed_at_before_started_at_is_rejected() -> None:
    """completed_at must not be earlier than started_at."""

    with pytest.raises(ValidationError):
        WorkflowStepResult(
            job_id="job_123",
            step_name="research",
            status=WorkflowStepStatus.COMPLETED,
            started_at=aware_datetime(10),
            completed_at=aware_datetime(9),
        )


def test_workflow_step_result_awaiting_approval_requires_pending_approval() -> None:
    """Awaiting approval status requires pending approval status."""

    with pytest.raises(ValidationError):
        WorkflowStepResult(
            job_id="job_123",
            step_name="approval",
            status=WorkflowStepStatus.AWAITING_APPROVAL,
            approval_status=ApprovalStatus.NOT_REQUIRED,
        )


def test_valid_approved_result_is_accepted() -> None:
    """An approved workflow step result with a non-pending status should validate."""

    result = WorkflowStepResult(
        job_id="job_123",
        step_name="approval",
        status=WorkflowStepStatus.COMPLETED,
        approval_status=ApprovalStatus.APPROVED,
        started_at=aware_datetime(10),
        completed_at=aware_datetime(11),
    )

    assert result.approval_status == ApprovalStatus.APPROVED


def test_valid_failed_result_can_contain_structured_error() -> None:
    """Failed workflow step results may include structured error metadata."""

    result = WorkflowStepResult(
        job_id="job_123",
        step_name="provider_call",
        status=WorkflowStepStatus.FAILED,
        started_at=aware_datetime(10),
        completed_at=aware_datetime(11),
        error={"type": "ProviderTimeoutError", "retryable": True},
    )

    assert result.error == {"type": "ProviderTimeoutError", "retryable": True}


def test_valid_workflow_step_result_serializes_and_restores_predictably() -> None:
    """Valid workflow step results should round-trip predictably."""

    result = WorkflowStepResult(
        job_id="job_123",
        step_name="research",
        status=WorkflowStepStatus.COMPLETED,
        started_at=aware_datetime(10),
        completed_at=aware_datetime(11),
        output={"items": 3},
        retry_count=1,
    )

    restored = WorkflowStepResult.model_validate(result.model_dump())

    assert restored == result
