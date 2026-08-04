"""Unit tests for shared CreatorOS provider boundary models."""

import pytest
from pydantic import BaseModel, ValidationError

from creatoros.providers import (
    ProviderCapability,
    ProviderInfo,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)


class StructuredResponse(BaseModel):
    """Simple structured model used to validate generic provider results."""

    message: str
    score: int


def build_provider_info() -> ProviderInfo:
    """Create a minimal valid provider metadata object."""

    return ProviderInfo(
        name="Test Provider",
        provider_type="llm",
        capabilities={ProviderCapability.TEXT_GENERATION},
    )


def test_provider_info_rejects_blank_name() -> None:
    """ProviderInfo should reject blank provider names."""

    with pytest.raises(ValidationError):
        ProviderInfo(
            name="   ",
            provider_type="llm",
            capabilities={ProviderCapability.TEXT_GENERATION},
        )


def test_provider_info_rejects_blank_provider_type() -> None:
    """ProviderInfo should reject blank provider type values."""

    with pytest.raises(ValidationError):
        ProviderInfo(
            name="Test Provider",
            provider_type="   ",
            capabilities={ProviderCapability.TEXT_GENERATION},
        )


def test_provider_info_requires_at_least_one_capability() -> None:
    """ProviderInfo should require at least one capability."""

    with pytest.raises(ValidationError):
        ProviderInfo(name="Test Provider", provider_type="llm", capabilities=set())


def test_provider_info_metadata_defaults_are_not_shared() -> None:
    """ProviderInfo metadata dictionaries should not be shared."""

    first = build_provider_info()
    second = build_provider_info()

    first.metadata["region"] = "us"

    assert second.metadata == {}


def test_provider_usage_rejects_negative_values() -> None:
    """ProviderUsage should reject negative numeric values."""

    with pytest.raises(ValidationError):
        ProviderUsage(input_units=-1)

    with pytest.raises(ValidationError):
        ProviderUsage(output_units=-1)

    with pytest.raises(ValidationError):
        ProviderUsage(total_units=-1)

    with pytest.raises(ValidationError):
        ProviderUsage(estimated_cost=-0.01)


def test_provider_usage_accepts_zero_values() -> None:
    """ProviderUsage should allow zero-valued usage and cost metrics."""

    usage = ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
    )

    assert usage.input_units == 0
    assert usage.output_units == 0
    assert usage.total_units == 0
    assert usage.estimated_cost == 0.0


def test_provider_usage_rejects_blank_currency() -> None:
    """ProviderUsage should reject blank currency values."""

    with pytest.raises(ValidationError):
        ProviderUsage(currency="   ")


def test_provider_result_round_trips_predictably_for_string_data() -> None:
    """ProviderResult should restore predictably for primitive payloads."""

    result = ProviderResult[str](
        data="Generated script text",
        provider=build_provider_info(),
        usage=ProviderUsage(total_units=42),
        request_id="req_123",
    )

    restored = ProviderResult[str].model_validate(result.model_dump())

    assert restored == result


def test_provider_result_round_trips_predictably_for_structured_data() -> None:
    """ProviderResult should restore predictably for Pydantic payloads."""

    result = ProviderResult[StructuredResponse](
        data=StructuredResponse(message="Ready", score=95),
        provider=build_provider_info(),
        metadata={"source": "test"},
    )

    restored = ProviderResult[StructuredResponse].model_validate(result.model_dump())

    assert restored == result


def test_provider_result_metadata_defaults_are_not_shared() -> None:
    """ProviderResult metadata dictionaries should not be shared."""

    first = ProviderResult[str](data="first", provider=build_provider_info())
    second = ProviderResult[str](data="second", provider=build_provider_info())

    first.metadata["request"] = "a"

    assert second.metadata == {}


def test_provider_request_context_validates_positive_timeout() -> None:
    """ProviderRequestContext should require positive timeout values."""

    with pytest.raises(ValidationError):
        ProviderRequestContext(timeout_seconds=0)

    with pytest.raises(ValidationError):
        ProviderRequestContext(timeout_seconds=-1)


def test_provider_request_context_metadata_defaults_are_not_shared() -> None:
    """ProviderRequestContext metadata dictionaries should not be shared."""

    first = ProviderRequestContext()
    second = ProviderRequestContext()

    first.metadata["step"] = "research"

    assert second.metadata == {}


def test_provider_request_context_normalizes_blank_optional_identifiers() -> None:
    """Optional context identifiers should normalize blank values to ``None``."""

    context = ProviderRequestContext(job_id="   ", step_id=" ", workflow_name="\t")

    assert context.job_id is None
    assert context.step_id is None
    assert context.workflow_name is None
