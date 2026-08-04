"""Stable shared provider models for CreatorOS provider boundaries."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from creatoros.domain import CreatorOSModel


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Reject blank values for required textual fields."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _normalize_optional_string(value: str | None) -> str | None:
    """Normalize optional blank strings to ``None`` at provider boundaries."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


class ProviderCapability(StrEnum):
    """Capabilities supported by CreatorOS provider implementations."""

    TEXT_GENERATION = "text_generation"
    STRUCTURED_GENERATION = "structured_generation"
    TREND_RESEARCH = "trend_research"
    WEB_SEARCH = "web_search"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    VOICE_GENERATION = "voice_generation"
    MUSIC_GENERATION = "music_generation"
    STORAGE = "storage"
    PUBLISHING = "publishing"
    ANALYTICS = "analytics"


class ProviderInfo(CreatorOSModel):
    """Describes a concrete provider implementation and its capabilities."""

    name: str
    provider_type: str
    capabilities: set[ProviderCapability]
    version: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name", "provider_type")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Reject blank provider names and types."""

        return _validate_non_blank(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_capabilities(self) -> ProviderInfo:
        """Require at least one declared provider capability."""

        if not self.capabilities:
            raise ValueError("capabilities must contain at least one value")
        return self


class ProviderUsage(CreatorOSModel):
    """Captures normalized usage and estimated cost metadata for provider work."""

    input_units: int | None = None
    output_units: int | None = None
    total_units: int | None = None
    estimated_cost: float | None = None
    currency: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("input_units", "output_units", "total_units")
    @classmethod
    def validate_non_negative_ints(cls, value: int | None, info) -> int | None:
        """Require non-negative usage counts when supplied."""

        if value is not None and value < 0:
            raise ValueError(f"{info.field_name} must be zero or greater")
        return value

    @field_validator("estimated_cost")
    @classmethod
    def validate_estimated_cost(cls, value: float | None) -> float | None:
        """Require non-negative cost estimates when supplied."""

        if value is not None and value < 0:
            raise ValueError("estimated_cost must be zero or greater")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None, info) -> str | None:
        """Reject blank currency codes when a currency is provided."""

        if value is None:
            return None
        return _validate_non_blank(value, field_name=info.field_name)


class ProviderResult[T](CreatorOSModel):
    """Stable, serializable wrapper for provider responses."""

    data: T
    provider: ProviderInfo
    usage: ProviderUsage | None = None
    request_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ProviderRequestContext(CreatorOSModel):
    """Optional execution context passed to provider calls."""

    job_id: str | None = None
    step_id: str | None = None
    workflow_name: str | None = None
    timeout_seconds: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("job_id", "step_id", "workflow_name")
    @classmethod
    def normalize_optional_identifiers(cls, value: str | None) -> str | None:
        """Normalize optional blank context identifiers to ``None``."""

        return _normalize_optional_string(value)

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: float | None) -> float | None:
        """Require positive timeouts when a timeout is provided."""

        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return value


__all__ = [
    "ProviderCapability",
    "ProviderInfo",
    "ProviderRequestContext",
    "ProviderResult",
    "ProviderUsage",
]
