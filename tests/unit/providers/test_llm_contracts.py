"""Unit tests for normalized CreatorOS LLM provider contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from creatoros.prompts import PromptMessage, PromptRole
from creatoros.providers import (
    LLMRequest,
    LLMResponse,
    LLMUsage,
)


def build_message(content: str = "Hello there.") -> PromptMessage:
    """Build a reusable provider-independent prompt message."""

    return PromptMessage(role=PromptRole.USER, content=content)


def test_valid_llm_request_can_be_created() -> None:
    """A valid provider-neutral LLM request should be accepted."""

    request = LLMRequest(messages=[build_message()], model="mock-model")

    assert request.model == "mock-model"


def test_blank_model_is_rejected() -> None:
    """LLM requests should reject blank model identifiers."""

    with pytest.raises(ValidationError):
        LLMRequest(messages=[build_message()], model="   ")


def test_invalid_max_output_tokens_is_rejected() -> None:
    """LLM requests should require positive token limits when supplied."""

    with pytest.raises(ValidationError):
        LLMRequest(messages=[build_message()], model="mock-model", max_output_tokens=0)


def test_invalid_timeout_is_rejected() -> None:
    """LLM requests should require positive timeouts when supplied."""

    with pytest.raises(ValidationError):
        LLMRequest(messages=[build_message()], model="mock-model", timeout_seconds=0)


def test_request_metadata_defaults_are_isolated() -> None:
    """LLM request metadata dictionaries should not be shared."""

    first = LLMRequest(messages=[build_message()], model="mock-model")
    second = LLMRequest(messages=[build_message()], model="mock-model")
    first.metadata["owner"] = "first"

    assert second.metadata == {}


def test_request_serialization_contains_no_credentials() -> None:
    """Request serialization should contain only provider-neutral fields."""

    request = LLMRequest(messages=[build_message()], model="mock-model")
    dumped = request.model_dump(mode="python")

    assert "api_key" not in dumped
    assert "authorization" not in dumped


def test_rendered_messages_are_preserved() -> None:
    """LLM requests should preserve rendered provider-independent messages."""

    message = build_message("Keep this exact content.")
    request = LLMRequest(messages=[message], model="mock-model")

    assert request.messages == [message]


def test_request_does_not_require_provider_sdk_types() -> None:
    """LLM requests should use only project-owned prompt message types."""

    request = LLMRequest(messages=[build_message()], model="mock-model")

    assert isinstance(request.messages[0], PromptMessage)


def test_valid_llm_usage_is_accepted() -> None:
    """Valid normalized token usage should be accepted."""

    usage = LLMUsage(input_tokens=2, output_tokens=3, total_tokens=5)

    assert usage.total_tokens == 5


def test_negative_token_counts_are_rejected() -> None:
    """LLM usage should reject negative token counts."""

    with pytest.raises(ValidationError):
        LLMUsage(input_tokens=-1)


def test_matching_total_tokens_is_accepted() -> None:
    """LLM usage should accept matching token totals."""

    usage = LLMUsage(input_tokens=4, output_tokens=5, total_tokens=9)

    assert usage.total_tokens == 9


def test_mismatched_total_tokens_is_rejected() -> None:
    """LLM usage should reject inconsistent token totals."""

    with pytest.raises(ValidationError):
        LLMUsage(input_tokens=4, output_tokens=5, total_tokens=10)


def test_partial_usage_is_accepted() -> None:
    """Partial usage data should remain valid."""

    usage = LLMUsage(input_tokens=4)

    assert usage.input_tokens == 4
    assert usage.total_tokens is None


def test_valid_llm_response_is_accepted() -> None:
    """A valid normalized LLM response should be accepted."""

    response = LLMResponse(
        text="Mock generated text.",
        provider_name="mock",
        model="mock-model",
    )

    assert response.provider_name == "mock"


def test_blank_provider_name_is_rejected() -> None:
    """LLM responses should reject blank provider identifiers."""

    with pytest.raises(ValidationError):
        LLMResponse(text="hello", provider_name="   ", model="mock-model")


def test_blank_model_is_rejected_for_response() -> None:
    """LLM responses should reject blank model identifiers."""

    with pytest.raises(ValidationError):
        LLMResponse(text="hello", provider_name="mock", model="   ")


def test_response_metadata_defaults_are_isolated() -> None:
    """LLM response metadata dictionaries should not be shared."""

    first = LLMResponse(text="one", provider_name="mock", model="mock-model")
    second = LLMResponse(text="two", provider_name="mock", model="mock-model")
    first.metadata["request"] = "first"

    assert second.metadata == {}


def test_normalized_response_contains_no_sdk_object_requirement() -> None:
    """LLM responses should restore from plain serialized data only."""

    response = LLMResponse(
        text="Mock generated text.",
        provider_name="mock",
        model="mock-model",
        usage=LLMUsage(input_tokens=1, output_tokens=2, total_tokens=3),
    )

    restored = LLMResponse.model_validate(response.model_dump(mode="python"))

    assert restored == response
