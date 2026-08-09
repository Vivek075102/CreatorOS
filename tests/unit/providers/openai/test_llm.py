"""Unit tests for the CreatorOS OpenAI LLM provider adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

import httpx
import openai
import pytest
from openai.types.responses import (
    Response,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseUsage,
)
from pydantic import BaseModel

from creatoros.core import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.prompts.enums import PromptRole
from creatoros.prompts.models import PromptMessage
from creatoros.providers import (
    LLMProvider,
    LLMRequest,
    ProviderRequestContext,
    create_provider_registry,
)
from creatoros.providers.openai import (
    DEFAULT_OPENAI_MODEL,
    OpenAILLMProvider,
    register_openai_provider,
)


def build_response(
    *,
    text: str,
    model: str = DEFAULT_OPENAI_MODEL,
    request_id: str = "req_openai_123",
    status: str = "completed",
) -> Response:
    """Create a minimal OpenAI SDK response object for deterministic tests."""

    response = Response.model_construct(
        id="resp_openai_123",
        created_at=0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={"fixture": "openai"},
        model=model,
        object="response",
        output=[
            ResponseOutputMessage.model_construct(
                id="msg_openai_123",
                content=[
                    ResponseOutputText.model_construct(
                        annotations=[],
                        text=text,
                        type="output_text",
                        logprobs=[],
                    )
                ],
                role="assistant",
                status="completed",
                type="message",
                phase="output",
            )
        ],
        parallel_tool_calls=False,
        temperature=0.2,
        tool_choice="auto",
        tools=[],
        top_p=1.0,
        background=False,
        completed_at=1,
        conversation=None,
        max_output_tokens=64,
        max_tool_calls=0,
        moderation="auto",
        previous_response_id=None,
        prompt=None,
        prompt_cache_key=None,
        prompt_cache_options=None,
        prompt_cache_retention="in_memory",
        reasoning=None,
        safety_identifier=None,
        service_tier="default",
        status=status,
        text=None,
        top_logprobs=0,
        truncation="disabled",
        usage=ResponseUsage.model_construct(
            input_tokens=5,
            input_tokens_details=None,
            output_tokens=7,
            output_tokens_details=None,
            total_tokens=12,
        ),
        user=None,
    )
    response._request_id = request_id
    return response


@dataclass
class FakeResponsesClient:
    """Simple async fake that records the most recent request."""

    response: object | None = None
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    async def create(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("response must be configured for this fake")
        return self.response


@dataclass
class FakeOpenAIClient:
    """Simple injected client exposing the OpenAI responses interface."""

    responses: FakeResponsesClient


class PayloadModel(BaseModel):
    """Simple structured model used for compatibility validation tests."""

    title: str


def build_request(*, model: str = DEFAULT_OPENAI_MODEL) -> LLMRequest:
    """Create a stable normalized request used in multiple tests."""

    return LLMRequest(
        model=model,
        temperature=0.3,
        max_output_tokens=120,
        timeout_seconds=9.0,
        messages=[
            PromptMessage(role=PromptRole.SYSTEM, content="You are precise."),
            PromptMessage(role=PromptRole.USER, content="Write one sentence."),
        ],
        metadata={
            "job_id": "job_123",
            "attempt": 2,
            "debug": False,
            "ignored": ["not", "serializable"],
        },
    )


def build_provider(
    *,
    client: FakeOpenAIClient | None = None,
    api_key: str | None = None,
) -> OpenAILLMProvider:
    """Create an adapter with explicit local defaults for isolated tests."""

    return OpenAILLMProvider(
        client=client,
        api_key=api_key,
        timeout_seconds=30.0,
        max_retries=0,
    )


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in unit tests without requiring async pytest plugins."""

    return asyncio.run(coro)


def test_openai_provider_satisfies_runtime_llm_protocol() -> None:
    """The adapter should satisfy the runtime provider contract."""

    provider = build_provider(
        client=FakeOpenAIClient(FakeResponsesClient(response=build_response(text="ok")))
    )

    assert isinstance(provider, LLMProvider)


def test_generate_translates_request_and_normalizes_response() -> None:
    """The adapter should translate messages and normalize the SDK response."""

    fake_responses = FakeResponsesClient(response=build_response(text="Normalized output"))
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    response = run_async(provider.generate(build_request()))

    assert response.text == "Normalized output"
    assert response.provider_name == "openai"
    assert response.model == DEFAULT_OPENAI_MODEL
    assert response.finish_reason == "stop"
    assert response.request_id == "req_openai_123"
    assert response.usage is not None
    assert response.usage.total_tokens == 12
    assert response.metadata == {
        "status": "completed",
        "response_id": "resp_openai_123",
    }

    assert fake_responses.calls == [
        {
            "model": DEFAULT_OPENAI_MODEL,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": "You are precise."}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Write one sentence."}],
                },
            ],
            "temperature": 0.3,
            "max_output_tokens": 120,
            "timeout": 9.0,
            "metadata": {
                "job_id": "job_123",
                "attempt": 2,
                "debug": False,
            },
        }
    ]


def test_generate_uses_context_timeout_when_request_timeout_is_absent() -> None:
    """Context timeout should flow through when the request leaves it unset."""

    fake_responses = FakeResponsesClient(response=build_response(text="context timeout"))
    provider = build_provider(client=FakeOpenAIClient(fake_responses))
    request = build_request().model_copy(update={"timeout_seconds": None})

    response = run_async(provider.generate(
        request,
        context=ProviderRequestContext(timeout_seconds=4.5),
    ))

    assert response.text == "context timeout"
    assert fake_responses.calls[0]["timeout"] == 4.5


def test_generate_text_uses_default_model_and_returns_provider_result() -> None:
    """Compatibility text generation should route through the normalized boundary."""

    fake_responses = FakeResponsesClient(response=build_response(text="Plain text", model="gpt-5-mini"))
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    result = run_async(provider.generate_text("Summarize this."))

    assert result.data == "Plain text"
    assert result.provider.name == "openai"
    assert result.metadata == {"model": DEFAULT_OPENAI_MODEL}
    assert fake_responses.calls[0]["model"] == DEFAULT_OPENAI_MODEL


def test_generate_structured_validates_json_from_text_response() -> None:
    """Structured compatibility should validate JSON into the requested Pydantic model."""

    fake_responses = FakeResponsesClient(response=build_response(text='{"title":"CreatorOS"}'))
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    result = run_async(provider.generate_structured("Return JSON.", response_model=PayloadModel))

    assert result.data == PayloadModel(title="CreatorOS")


def test_generate_structured_raises_typed_error_for_invalid_json() -> None:
    """Malformed structured text should raise a normalized provider response error."""

    fake_responses = FakeResponsesClient(response=build_response(text="not json"))
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate_structured("Return JSON.", response_model=PayloadModel))


def test_generate_raises_authentication_error_when_api_key_is_missing() -> None:
    """Requests should fail safely when no injected client or API key is available."""

    provider = build_provider(api_key=None)

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        run_async(provider.generate(build_request()))

    assert exc_info.value.code == "provider_authentication_missing"
    assert exc_info.value.details == {"provider_name": "openai"}


def test_health_check_is_local_and_does_not_require_network() -> None:
    """Readiness should be computed from local configuration only."""

    assert run_async(build_provider(client=FakeOpenAIClient(FakeResponsesClient(response=build_response(text="ok")))).health_check()) is True
    assert run_async(build_provider(api_key="sk-test").health_check()) is True
    assert run_async(build_provider(api_key=None).health_check()) is False


def test_rate_limit_errors_are_translated() -> None:
    """Rate limits should be translated into the CreatorOS provider exception hierarchy."""

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request)
    fake_responses = FakeResponsesClient(
        error=openai.RateLimitError("rate limited", response=response, body=None)
    )
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    with pytest.raises(ProviderRateLimitError) as exc_info:
        run_async(provider.generate(build_request()))

    assert exc_info.value.code == "provider_rate_limited"
    assert exc_info.value.details["provider_name"] == "openai"


def test_timeout_errors_are_translated() -> None:
    """SDK timeout failures should become normalized timeout errors."""

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    fake_responses = FakeResponsesClient(error=openai.APITimeoutError(request))
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    with pytest.raises(ProviderTimeoutError):
        run_async(provider.generate(build_request()))


def test_connection_errors_are_translated() -> None:
    """Connection failures should become provider unavailable errors."""

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    fake_responses = FakeResponsesClient(
        error=openai.APIConnectionError(message="connection error", request=request)
    )
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    with pytest.raises(ProviderUnavailableError):
        run_async(provider.generate(build_request()))


def test_missing_output_text_raises_provider_response_error() -> None:
    """Responses without readable text should not escape the adapter boundary."""

    fake_responses = FakeResponsesClient(response=object())
    provider = build_provider(client=FakeOpenAIClient(fake_responses))

    with pytest.raises(ProviderResponseError):
        run_async(provider.generate(build_request()))


def test_register_openai_provider_registers_adapter_without_changing_default_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit registration should work while the global default still remains mock."""

    class StubSettings:
        openai_api_key = "sk-test"
        default_llm_model = "mock-model"
        provider_timeout_seconds = 30.0
        provider_max_retries = 3

    registry = create_provider_registry()
    monkeypatch.setattr("creatoros.providers.openai.bootstrap.get_settings", lambda: StubSettings())

    fake_responses = FakeResponsesClient(response=build_response(text="Registered helper"))
    provider = register_openai_provider(registry, client=FakeOpenAIClient(fake_responses))

    assert provider is registry.get("llm", "openai")
    assert registry.contains("llm", "openai")
    assert provider.info.name == "openai"
    assert provider.info.provider_type == "llm"
    assert provider._timeout_seconds == 30.0
    assert provider._max_retries == 0

    run_async(provider.generate_text("Use helper defaults."))
    assert fake_responses.calls[0]["model"] == DEFAULT_OPENAI_MODEL
