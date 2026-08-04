"""Unit tests for CreatorOS agent models."""

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from creatoros.agents import AgentExecutionContext, AgentResult


class StructuredData(BaseModel):
    """Simple payload model used for agent result round-trip tests."""

    message: str


def test_agent_execution_context_accepts_valid_values() -> None:
    """Execution contexts should accept valid required values."""

    context = AgentExecutionContext(
        job_id="job_123",
        step_id="step_1",
        workflow_name="gaming_short",
        engine_name="research_engine",
    )

    assert context.job_id == "job_123"
    assert context.step_id == "step_1"
    assert context.workflow_name == "gaming_short"
    assert context.engine_name == "research_engine"


def test_agent_execution_context_trims_required_strings() -> None:
    """Execution context values should be normalized by trimming whitespace."""

    context = AgentExecutionContext(
        job_id="  job_123  ",
        step_id="  step_1 ",
        workflow_name=" gaming_short ",
        engine_name=" research_engine ",
    )

    assert context.job_id == "job_123"
    assert context.step_id == "step_1"
    assert context.workflow_name == "gaming_short"
    assert context.engine_name == "research_engine"


def test_agent_execution_context_rejects_blank_job_id() -> None:
    """Blank job identifiers should be rejected."""

    with pytest.raises(ValidationError):
        AgentExecutionContext(
            job_id="   ",
            step_id="step_1",
            workflow_name="workflow",
            engine_name="engine",
        )


def test_agent_execution_context_rejects_blank_step_id() -> None:
    """Blank step identifiers should be rejected."""

    with pytest.raises(ValidationError):
        AgentExecutionContext(
            job_id="job_1",
            step_id="   ",
            workflow_name="workflow",
            engine_name="engine",
        )


def test_agent_execution_context_rejects_blank_workflow_name() -> None:
    """Blank workflow names should be rejected."""

    with pytest.raises(ValidationError):
        AgentExecutionContext(
            job_id="job_1",
            step_id="step_1",
            workflow_name="   ",
            engine_name="engine",
        )


def test_agent_execution_context_rejects_blank_engine_name() -> None:
    """Blank engine names should be rejected."""

    with pytest.raises(ValidationError):
        AgentExecutionContext(
            job_id="job_1",
            step_id="step_1",
            workflow_name="workflow",
            engine_name="   ",
        )


def test_agent_execution_context_metadata_defaults_are_not_shared() -> None:
    """Execution context metadata dictionaries should not be shared."""

    first = AgentExecutionContext(
        job_id="job_1",
        step_id="step_1",
        workflow_name="workflow",
        engine_name="engine",
    )
    second = AgentExecutionContext(
        job_id="job_2",
        step_id="step_2",
        workflow_name="workflow",
        engine_name="engine",
    )

    first.metadata["key"] = "value"

    assert second.metadata == {}


def test_agent_result_accepts_valid_data() -> None:
    """Agent results should accept valid execution metadata."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)
    result = AgentResult[str](
        data="done",
        agent_name="analysis_agent",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=1.0,
    )

    assert result.data == "done"


def test_agent_result_rejects_blank_agent_name() -> None:
    """Blank agent names should be rejected."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)

    with pytest.raises(ValidationError):
        AgentResult[str](
            data="done",
            agent_name="   ",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=1.0,
        )


def test_agent_result_rejects_naive_timestamps() -> None:
    """Naive timestamps should be rejected."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC).replace(tzinfo=None)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC).replace(tzinfo=None)

    with pytest.raises(ValidationError):
        AgentResult[str](
            data="done",
            agent_name="analysis_agent",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=1.0,
        )


def test_agent_result_rejects_negative_duration() -> None:
    """Negative duration values should be rejected."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)

    with pytest.raises(ValidationError):
        AgentResult[str](
            data="done",
            agent_name="analysis_agent",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=-1.0,
        )


def test_agent_result_rejects_completion_before_start() -> None:
    """Completion timestamps should not precede start timestamps."""

    started_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)

    with pytest.raises(ValidationError):
        AgentResult[str](
            data="done",
            agent_name="analysis_agent",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=0.0,
        )


def test_agent_result_serializes_and_restores_predictably() -> None:
    """Agent results should round-trip predictably through Pydantic serialization."""

    original = AgentResult[StructuredData](
        data=StructuredData(message="ready"),
        agent_name="analysis_agent",
        started_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 4, 10, 0, 2, tzinfo=UTC),
        duration_seconds=2.0,
        metadata={"attempt": 1},
    )

    restored = AgentResult[StructuredData].model_validate(original.model_dump())

    assert restored == original


def test_agent_result_metadata_defaults_are_not_shared() -> None:
    """Agent result metadata dictionaries should not be shared."""

    started_at = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 4, 10, 0, 1, tzinfo=UTC)
    first = AgentResult[str](
        data="done",
        agent_name="analysis_agent",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=1.0,
    )
    second = AgentResult[str](
        data="done",
        agent_name="analysis_agent",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=1.0,
    )

    first.metadata["attempt"] = 1

    assert second.metadata == {}
