"""Unit tests for CreatorOS engine models."""

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from creatoros.engines import EngineExecutionContext, EngineResult


class StructuredData(BaseModel):
    """Simple payload model used for engine result round-trip tests."""

    message: str


def test_engine_execution_context_accepts_valid_values() -> None:
    """Execution contexts should accept valid required values."""

    context = EngineExecutionContext(
        job_id="job_123",
        step_id="step_1",
        workflow_name="gaming_short",
    )

    assert context.job_id == "job_123"
    assert context.step_id == "step_1"
    assert context.workflow_name == "gaming_short"


def test_engine_execution_context_trims_surrounding_whitespace() -> None:
    """Execution context values should be normalized by trimming whitespace."""

    context = EngineExecutionContext(
        job_id="  job_123  ",
        step_id="  step_1 ",
        workflow_name=" gaming_short ",
    )

    assert context.job_id == "job_123"
    assert context.step_id == "step_1"
    assert context.workflow_name == "gaming_short"


def test_engine_execution_context_rejects_blank_job_id() -> None:
    """Blank job identifiers should be rejected."""

    with pytest.raises(ValidationError):
        EngineExecutionContext(job_id="   ", step_id="step_1", workflow_name="workflow")


def test_engine_execution_context_rejects_blank_step_id() -> None:
    """Blank step identifiers should be rejected."""

    with pytest.raises(ValidationError):
        EngineExecutionContext(job_id="job_1", step_id="   ", workflow_name="workflow")


def test_engine_execution_context_rejects_blank_workflow_name() -> None:
    """Blank workflow names should be rejected."""

    with pytest.raises(ValidationError):
        EngineExecutionContext(job_id="job_1", step_id="step_1", workflow_name="   ")


def test_engine_execution_context_metadata_defaults_are_not_shared() -> None:
    """Execution context metadata dictionaries should not be shared."""

    first = EngineExecutionContext(job_id="job_1", step_id="step_1", workflow_name="workflow")
    second = EngineExecutionContext(job_id="job_2", step_id="step_2", workflow_name="workflow")

    first.metadata["key"] = "value"

    assert second.metadata == {}


def test_engine_result_accepts_valid_data() -> None:
    """Engine results should accept valid execution metadata."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)
    result = EngineResult[str](
        data="done",
        engine_name="script_engine",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=1.0,
    )

    assert result.data == "done"


def test_engine_result_rejects_blank_engine_name() -> None:
    """Blank engine names should be rejected."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)

    with pytest.raises(ValidationError):
        EngineResult[str](
            data="done",
            engine_name="   ",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=1.0,
        )


def test_engine_result_rejects_naive_datetimes() -> None:
    """Naive timestamps should be rejected."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC).replace(tzinfo=None)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC).replace(tzinfo=None)

    with pytest.raises(ValidationError):
        EngineResult[str](
            data="done",
            engine_name="script_engine",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=1.0,
        )


def test_engine_result_rejects_negative_duration() -> None:
    """Negative duration values should be rejected."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)

    with pytest.raises(ValidationError):
        EngineResult[str](
            data="done",
            engine_name="script_engine",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=-1.0,
        )


def test_engine_result_rejects_completed_at_before_started_at() -> None:
    """Completion timestamps should not precede start timestamps."""

    started_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)

    with pytest.raises(ValidationError):
        EngineResult[str](
            data="done",
            engine_name="script_engine",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=0.0,
        )


def test_engine_result_serializes_and_restores_predictably() -> None:
    """Engine results should round-trip predictably through Pydantic serialization."""

    original = EngineResult[StructuredData](
        data=StructuredData(message="ready"),
        engine_name="script_engine",
        started_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 4, 10, 0, 2, tzinfo=UTC),
        duration_seconds=2.0,
        metadata={"attempt": 1},
    )

    restored = EngineResult[StructuredData].model_validate(original.model_dump())

    assert restored == original


def test_engine_result_metadata_defaults_are_not_shared() -> None:
    """Engine result metadata dictionaries should not be shared."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)
    first = EngineResult[str](
        data="done",
        engine_name="script_engine",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=1.0,
    )
    second = EngineResult[str](
        data="done",
        engine_name="script_engine",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=1.0,
    )

    first.metadata["attempt"] = 1

    assert second.metadata == {}
