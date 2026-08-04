"""Shared execution models for CreatorOS engines."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from creatoros.domain import CreatorOSModel
from creatoros.domain.base import ensure_aware_utc_datetime


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank values for required textual fields."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class EngineExecutionContext(CreatorOSModel):
    """Execution-scoped identifiers passed through engine runs."""

    job_id: str
    step_id: str
    workflow_name: str
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("job_id", "step_id", "workflow_name")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank identifier values."""

        return _validate_non_blank(value, field_name=info.field_name)


class EngineResult[T](CreatorOSModel):
    """Serializable wrapper describing the outcome of an engine execution."""

    data: T
    engine_name: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("engine_name")
    @classmethod
    def validate_engine_name(cls, value: str, info) -> str:
        """Trim and reject blank engine names."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_datetimes(cls, value: datetime, info) -> datetime:
        """Require timezone-aware timestamps."""

        return ensure_aware_utc_datetime(value, field_name=info.field_name)

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require non-negative execution duration values."""

        if value < 0:
            raise ValueError("duration_seconds must be zero or greater")
        return value

    @model_validator(mode="after")
    def validate_temporal_order(self) -> EngineResult[T]:
        """Require completion timestamps to be no earlier than start timestamps."""

        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be earlier than started_at")
        return self


__all__ = [
    "EngineExecutionContext",
    "EngineResult",
]
