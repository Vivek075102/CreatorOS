"""Unit tests for the CreatorOS mock LLM provider."""

import asyncio

import pytest
from pydantic import BaseModel

from creatoros.core import CreatorOSValidationError, ProviderResponseError
from creatoros.prompts import PromptMessage, PromptRole
from creatoros.providers import LLMRequest, LLMResponse
from creatoros.providers.mock import MockLLMProvider


class StructuredResponse(BaseModel):
    """Simple structured response model for mock LLM tests."""

    message: str


def test_generate_returns_normalized_response() -> None:
    """The normalized LLM boundary should return an LLMResponse."""

    provider = MockLLMProvider(response_text="Deterministic output.")
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert isinstance(result, LLMResponse)
    assert result.text == "Deterministic output."


def test_configured_response_text_is_returned() -> None:
    """The configured deterministic response text should be returned."""

    provider = MockLLMProvider(response_text="Configured response.")
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert result.text == "Configured response."


def test_provider_name_is_deterministic() -> None:
    """The mock provider should report a stable provider name."""

    provider = MockLLMProvider()
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert result.provider_name == "mock"


def test_model_name_is_deterministic() -> None:
    """The mock provider should echo the requested normalized model name."""

    provider = MockLLMProvider()
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert result.model == "mock-model"


def test_same_request_produces_deterministic_result() -> None:
    """Identical requests should produce identical normalized mock responses."""

    provider = MockLLMProvider()
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    first = asyncio.run(provider.generate(request))
    second = asyncio.run(provider.generate(request))

    assert first == second


def test_blank_prompts_are_rejected_for_legacy_generate_text() -> None:
    """Blank prompts should still be rejected for the compatibility helper."""

    provider = MockLLMProvider()

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(provider.generate_text("   "))


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

    with pytest.raises(ProviderResponseError):
        asyncio.run(
            provider.generate_structured("Generate structure", response_model=StructuredResponse),
        )


def test_prompt_content_is_not_included_in_normalized_response_metadata() -> None:
    """Prompt content should not be copied into normalized response metadata."""

    provider = MockLLMProvider()
    prompt = "very sensitive prompt"
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content=prompt)],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert prompt not in str(result.metadata)


def test_response_text_is_not_logged_automatically() -> None:
    """Mock generation should not expose response text through metadata."""

    response_text = "very sensitive response"
    provider = MockLLMProvider(response_text=response_text)
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert response_text not in str(result.metadata)


def test_no_parser_is_invoked() -> None:
    """The mock provider should not invoke parser infrastructure."""

    provider = MockLLMProvider()
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert result.text == "Mock generated text."


def test_no_prompt_registry_lookup_is_required() -> None:
    """The mock provider should consume normalized requests directly."""

    provider = MockLLMProvider()
    request = LLMRequest(
        messages=[PromptMessage(role=PromptRole.USER, content="Generate something")],
        model="mock-model",
    )

    result = asyncio.run(provider.generate(request))

    assert result.model == "mock-model"
