"""Unit tests for the CreatorOS mock LLM provider."""

import asyncio

import pytest
from pydantic import BaseModel

from creatoros.core import CreatorOSValidationError
from creatoros.providers.mock import MockLLMProvider


class StructuredResponse(BaseModel):
    """Simple structured response model for mock LLM tests."""

    message: str


def test_generate_text_returns_deterministic_text() -> None:
    """Text generation should return the configured deterministic response."""

    provider = MockLLMProvider(text_response="Deterministic output.")

    result = asyncio.run(provider.generate_text("Generate something"))

    assert result.data == "Deterministic output."


def test_blank_prompts_are_rejected() -> None:
    """Blank prompts should be rejected for text generation."""

    provider = MockLLMProvider()

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(provider.generate_text("   "))


def test_usage_reports_zero_estimated_cost() -> None:
    """Mock text generation should report zero estimated cost."""

    provider = MockLLMProvider()

    result = asyncio.run(provider.generate_text("Generate something"))

    assert result.usage is not None
    assert result.usage.estimated_cost == 0.0


def test_request_ids_use_expected_prefix() -> None:
    """Mock request identifiers should use the mock_request prefix."""

    provider = MockLLMProvider()

    result = asyncio.run(provider.generate_text("Generate something"))

    assert result.request_id is not None
    assert result.request_id.startswith("mock_request_")


def test_structured_generation_validates_into_supplied_model() -> None:
    """Structured generation should validate into the requested model."""

    provider = MockLLMProvider(structured_payload={"message": "ready"})

    result = asyncio.run(
        provider.generate_structured("Generate structure", response_model=StructuredResponse),
    )

    assert result.data == StructuredResponse(message="ready")


def test_invalid_structured_payload_raises_validation_error() -> None:
    """Invalid structured payloads should be translated into CreatorOSValidationError."""

    provider = MockLLMProvider(structured_payload={"wrong": "field"})

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(
            provider.generate_structured("Generate structure", response_model=StructuredResponse),
        )


def test_prompt_content_is_not_included_in_metadata() -> None:
    """Prompt content should not be copied into result metadata."""

    provider = MockLLMProvider()
    prompt = "very sensitive prompt"

    result = asyncio.run(provider.generate_text(prompt))

    assert prompt not in str(result.metadata)

