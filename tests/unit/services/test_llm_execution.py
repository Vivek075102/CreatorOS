"""Unit tests for the CreatorOS LLM execution service."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from openai.types.responses import (
    Response,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseUsage,
)

from creatoros.config import Settings
from creatoros.core import (
    ParserNotFoundError,
    PromptNotFoundError,
    ProviderNotFoundError,
    StructuredOutputError,
)
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingCTAOutput,
    ParserRegistration,
    build_builtin_parser_registry,
    create_parser_registry,
)
from creatoros.prompts import (
    GAMING_CTA,
    PromptDefinition,
    PromptFormat,
    PromptMessage,
    PromptRegistry,
    PromptRole,
    PromptStatus,
    PromptVariable,
    create_builtin_prompt_registry,
    create_prompt_registry,
)
from creatoros.providers import (
    LLMCapabilities,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderCapability,
    ProviderInfo,
    ProviderRegistry,
    create_provider_registry,
)
from creatoros.providers.mock import MockLLMProvider
from creatoros.providers.openai import DEFAULT_OPENAI_MODEL, OpenAILLMProvider
from creatoros.services import (
    LLMExecutionRequest,
    LLMExecutionResult,
    LLMExecutionService,
    create_llm_execution_service,
)

CTA_RESPONSE_TEXT = (
    "CTA:\nWhich one would you test next?\n\n"
    "ALTERNATIVE:\nWhat gaming myth should we check next?"
)


class FakeLogger:
    """Capture structured service log events for safety assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def info(self, event: str, **kwargs: object) -> None:
        """Record one info-level event."""

        self.events.append({"level": "info", "event": event, "kwargs": kwargs})

    def exception(self, event: str, **kwargs: object) -> None:
        """Record one exception-level event."""

        self.events.append({"level": "error", "event": event, "kwargs": kwargs})


class SimpleParsedOutput(CreatorOSModel):
    """Minimal typed parsed output for custom parser tests."""

    value: str


class RecordingLLMProvider:
    """Simple deterministic provider used to capture LLM requests in service tests."""

    def __init__(
        self,
        *,
        name: str = "mock",
        response_text: str = CTA_RESPONSE_TEXT,
    ) -> None:
        self._info = ProviderInfo(
            name=name,
            provider_type="llm",
            capabilities={
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.STRUCTURED_GENERATION,
            },
        )
        self._llm_capabilities = LLMCapabilities(
            supports_temperature=True,
            supports_max_output_tokens=True,
            supports_system_messages=True,
            supports_structured_text=True,
        )
        self.response_text = response_text
        self.calls = 0
        self.last_request: LLMRequest | None = None

    @property
    def info(self) -> ProviderInfo:
        return self._info

    @property
    def llm_capabilities(self) -> LLMCapabilities:
        return self._llm_capabilities

    async def health_check(self) -> bool:
        return True

    async def generate(self, request: LLMRequest, *, context=None) -> LLMResponse:
        del context
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        return LLMResponse(
            text=self.response_text,
            provider_name=self.info.name,
            model=request.model,
            finish_reason="stop",
            usage=LLMUsage(input_tokens=4, output_tokens=6, total_tokens=10),
            request_id=f"{self.info.name}_request",
            metadata={"status": "completed"},
        )

    async def generate_text(self, prompt: str, *, context=None):
        raise NotImplementedError

    async def generate_structured(self, prompt: str, *, response_model, context=None):
        raise NotImplementedError


@dataclass
class FakeResponsesClient:
    """Simple async fake that records one OpenAI responses call."""

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


def build_openai_response(
    *,
    text: str = CTA_RESPONSE_TEXT,
    model: str = DEFAULT_OPENAI_MODEL,
) -> Response:
    """Create a deterministic fake SDK response for end-to-end service tests."""

    response = Response.model_construct(
        id="resp_openai_execution",
        created_at=0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        model=model,
        object="response",
        output=[
            ResponseOutputMessage.model_construct(
                id="msg_openai_execution",
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
        status="completed",
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
    response._request_id = "req_openai_execution"
    return response


def build_settings(
    *,
    default_llm_provider: str = "mock",
    default_llm_model: str = "mock-model",
) -> Settings:
    """Create isolated settings without reading the live environment."""

    project_root = Path("C:/GamingAIFactory")
    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider=default_llm_provider,
        default_llm_model=default_llm_model,
        openai_api_key=None,
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        provider_max_retries=3,
        assets_dir=project_root / "assets",
        logs_dir=project_root / "logs",
        prompts_dir=project_root / "prompts",
    )


def build_prompt_definition(
    *,
    name: str = "custom_prompt",
    version: int = 1,
    status: PromptStatus = PromptStatus.ACTIVE,
) -> PromptDefinition:
    """Create a reusable prompt definition for focused service tests."""

    return PromptDefinition(
        name=name,
        version=version,
        status=status,
        format=PromptFormat.TEXT,
        messages=[
            PromptMessage(role=PromptRole.SYSTEM, content="Stay concise."),
            PromptMessage(role=PromptRole.USER, content="Topic: {topic}. Extra: {extra}."),
        ],
        variables=[
            PromptVariable(name="topic"),
            PromptVariable(name="extra", default="default-extra"),
        ],
        metadata={"owner": "creatoros"},
    )


def build_custom_service(
    *,
    prompt_registry: PromptRegistry | None = None,
    parser_registry=None,
    provider_registry: ProviderRegistry | None = None,
    settings: Settings | None = None,
) -> LLMExecutionService:
    """Create a focused service instance for unit tests."""

    resolved_prompt_registry = create_prompt_registry() if prompt_registry is None else prompt_registry
    resolved_parser_registry = create_parser_registry() if parser_registry is None else parser_registry
    resolved_provider_registry = create_provider_registry() if provider_registry is None else provider_registry
    resolved_settings = build_settings() if settings is None else settings
    return LLMExecutionService(
        resolved_prompt_registry,
        resolved_parser_registry,
        resolved_provider_registry,
        resolved_settings,
    )


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute async service calls in synchronous unit tests."""

    return asyncio.run(coro)


def test_valid_llm_execution_request_can_be_created() -> None:
    """Execution requests should accept valid provider-independent fields."""

    request = LLMExecutionRequest(
        prompt_name=" gaming_cta ",
        prompt_version=1,
        variables={"game": "Minecraft"},
        provider_name=" mock ",
        model=" mock-model ",
        temperature=0.2,
        max_output_tokens=100,
        timeout_seconds=10.0,
        metadata={"job_id": "job_123"},
    )

    assert request.prompt_name == "gaming_cta"
    assert request.prompt_version == 1
    assert request.provider_name == "mock"
    assert request.model == "mock-model"


def test_blank_prompt_name_is_rejected() -> None:
    """Blank execution prompt names should fail validation."""

    with pytest.raises(ValueError):
        LLMExecutionRequest(prompt_name="   ")


def test_invalid_prompt_version_is_rejected() -> None:
    """Prompt versions must be positive when supplied."""

    with pytest.raises(ValueError):
        LLMExecutionRequest(prompt_name="gaming_cta", prompt_version=0)


def test_request_mutable_defaults_are_isolated_and_defensively_copied() -> None:
    """Request variables and metadata should not share or leak mutable state."""

    first = LLMExecutionRequest(
        prompt_name="gaming_cta",
        variables={"items": ["one"]},
        metadata={"tags": ["safe"]},
    )
    second = LLMExecutionRequest(prompt_name="gaming_cta")
    original_items = first.variables["items"]
    original_tags = first.metadata["tags"]

    assert isinstance(original_items, list)
    assert isinstance(original_tags, list)
    original_items.append("two")
    original_tags.append("mutated")

    assert second.variables == {}
    assert second.metadata == {}


def test_result_mutable_defaults_are_isolated_and_output_is_copied() -> None:
    """Execution results should isolate metadata and typed output state."""

    output = SimpleParsedOutput(value="ready")
    first = LLMExecutionResult[SimpleParsedOutput](
        prompt_name="custom_prompt",
        prompt_version=1,
        provider_name="mock",
        model="mock-model",
        output=output,
        metadata={"tags": ["safe"]},
    )
    second = LLMExecutionResult[SimpleParsedOutput](
        prompt_name="custom_prompt",
        prompt_version=1,
        provider_name="mock",
        model="mock-model",
        output=SimpleParsedOutput(value="other"),
    )

    first.metadata["tags"].append("mutated")
    first.output.value = "changed"

    assert second.metadata == {}
    assert output.value == "ready"


def test_service_resolves_prompt_by_logical_name_and_uses_latest_active_version() -> None:
    """Omitted prompt versions should resolve the latest active prompt definition."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition(version=1, status=PromptStatus.ACTIVE))
    prompt_registry.register(build_prompt_definition(version=2, status=PromptStatus.ACTIVE))
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="custom_prompt",
            parser=lambda text: SimpleParsedOutput(value=text.strip()),
            output_model_type=SimpleParsedOutput,
        )
    )
    provider_registry = create_provider_registry()
    provider = RecordingLLMProvider(response_text="latest")
    provider_registry.register(provider)
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
    )

    result = run_async(
        service.execute(LLMExecutionRequest(prompt_name="custom_prompt", variables={"topic": "x"}))
    )

    assert result.prompt_version == 2
    assert provider.last_request is not None
    assert provider.last_request.messages[1].content == "Topic: x. Extra: default-extra."


def test_service_honors_explicit_prompt_version() -> None:
    """Explicit prompt versions should resolve that exact prompt definition."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition(version=1, status=PromptStatus.ACTIVE))
    prompt_registry.register(
        PromptDefinition(
            name="custom_prompt",
            version=2,
            status=PromptStatus.ACTIVE,
            format=PromptFormat.TEXT,
            messages=[PromptMessage(role=PromptRole.USER, content="Version two for {topic}.")],
            variables=[PromptVariable(name="topic")],
        )
    )
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="custom_prompt",
            parser=lambda text: SimpleParsedOutput(value=text.strip()),
            output_model_type=SimpleParsedOutput,
        )
    )
    provider_registry = create_provider_registry()
    provider = RecordingLLMProvider(response_text="version one")
    provider_registry.register(provider)
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
    )

    result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name="custom_prompt",
                prompt_version=1,
                variables={"topic": "Minecraft"},
            )
        )
    )

    assert result.prompt_version == 1
    assert provider.last_request is not None
    assert provider.last_request.messages[1].content == "Topic: Minecraft. Extra: default-extra."


def test_execution_request_variables_are_not_mutated_by_service() -> None:
    """Service execution should not mutate caller-owned request variables."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition())
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="custom_prompt",
            parser=lambda text: SimpleParsedOutput(value=text),
            output_model_type=SimpleParsedOutput,
        )
    )
    provider_registry = create_provider_registry()
    provider_registry.register(RecordingLLMProvider())
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
    )
    variables = {"topic": "Minecraft", "extra": "myths"}
    request = LLMExecutionRequest(prompt_name="custom_prompt", variables=variables)

    run_async(service.execute(request))
    variables["extra"] = "changed"

    assert request.variables["extra"] == "myths"


def test_default_mock_provider_is_selected_when_provider_name_is_absent() -> None:
    """Default provider selection should use settings when the request omits provider_name."""

    service = create_llm_execution_service(
        provider_registry=create_provider_registry(),
        settings=build_settings(),
    )
    service.provider_registry.register(MockLLMProvider(response_text=CTA_RESPONSE_TEXT))
    result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name=GAMING_CTA,
                variables={
                    "game": "Minecraft",
                    "topic": "gaming facts",
                    "platform": "YouTube Shorts",
                    "tone": "natural",
                },
            )
        )
    )

    assert result.provider_name == "mock"


def test_explicit_provider_overrides_default_settings_provider() -> None:
    """An explicit provider name should override the configured default provider."""

    prompt_registry = create_builtin_prompt_registry()
    parser_registry = build_builtin_parser_registry()
    provider_registry = create_provider_registry()
    provider_registry.register(RecordingLLMProvider(name="mock"))
    provider_registry.register(RecordingLLMProvider(name="openai"))
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
        settings=build_settings(default_llm_provider="mock"),
    )

    result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name=GAMING_CTA,
                provider_name="openai",
                variables={
                    "game": "Minecraft",
                    "topic": "gaming facts",
                    "platform": "YouTube Shorts",
                    "tone": "natural",
                },
            )
        )
    )

    assert result.provider_name == "openai"


def test_unknown_provider_fails_safely_without_fallback() -> None:
    """Unknown provider names should raise the typed provider registry error."""

    service = create_llm_execution_service(settings=build_settings())

    with pytest.raises(ProviderNotFoundError):
        run_async(
            service.execute(
                LLMExecutionRequest(
                    prompt_name=GAMING_CTA,
                    provider_name="missing",
                    variables={
                        "game": "Minecraft",
                        "topic": "gaming facts",
                        "platform": "YouTube Shorts",
                        "tone": "natural",
                    },
                )
            )
        )


def test_model_defaults_from_settings_and_explicit_model_overrides() -> None:
    """Model resolution should prefer request.model over settings.default_llm_model."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition())
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="custom_prompt",
            parser=lambda text: SimpleParsedOutput(value=text),
            output_model_type=SimpleParsedOutput,
        )
    )
    provider_registry = create_provider_registry()
    provider = RecordingLLMProvider()
    provider_registry.register(provider)
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
        settings=build_settings(default_llm_model="default-model"),
    )

    default_result = run_async(
        service.execute(LLMExecutionRequest(prompt_name="custom_prompt", variables={"topic": "A"}))
    )
    assert default_result.model == "default-model"
    assert provider.last_request is not None
    assert provider.last_request.model == "default-model"

    explicit_result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name="custom_prompt",
                model="explicit-model",
                variables={"topic": "B"},
            )
        )
    )
    assert explicit_result.model == "explicit-model"
    assert provider.last_request is not None
    assert provider.last_request.model == "explicit-model"


def test_rendered_message_order_roles_and_generation_parameters_are_preserved() -> None:
    """Rendered prompt messages and generation controls should flow into the LLM request unchanged."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition())
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="custom_prompt",
            parser=lambda text: SimpleParsedOutput(value=text),
            output_model_type=SimpleParsedOutput,
        )
    )
    provider_registry = create_provider_registry()
    provider = RecordingLLMProvider()
    provider_registry.register(provider)
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
    )

    run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name="custom_prompt",
                variables={"topic": "Minecraft", "extra": "myths"},
                temperature=0.4,
                max_output_tokens=80,
                timeout_seconds=12.0,
                metadata={"job_id": "job_123"},
            )
        )
    )

    assert provider.last_request is not None
    assert [message.role for message in provider.last_request.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
    ]
    assert [message.content for message in provider.last_request.messages] == [
        "Stay concise.",
        "Topic: Minecraft. Extra: myths.",
    ]
    assert provider.last_request.temperature == 0.4
    assert provider.last_request.max_output_tokens == 80
    assert provider.last_request.timeout_seconds == 12.0
    assert "api_key" not in provider.last_request.metadata


def test_parser_registry_is_used_and_typed_output_is_returned() -> None:
    """Execution should parse provider text through ParserRegistry and return a typed model."""

    service = create_llm_execution_service(
        provider_registry=create_provider_registry(),
        settings=build_settings(),
    )
    service.provider_registry.register(MockLLMProvider(response_text=CTA_RESPONSE_TEXT))

    result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name=GAMING_CTA,
                variables={
                    "game": "Minecraft",
                    "topic": "gaming facts",
                    "platform": "YouTube Shorts",
                    "tone": "natural",
                },
            )
        )
    )

    assert isinstance(result.output, GamingCTAOutput)
    assert result.metadata["output_model_type"] == "GamingCTAOutput"


def test_unknown_parser_fails_safely() -> None:
    """A missing parser registration should raise the typed parser error."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition())
    provider_registry = create_provider_registry()
    provider_registry.register(RecordingLLMProvider())
    service = build_custom_service(
        prompt_registry=prompt_registry,
        provider_registry=provider_registry,
    )

    with pytest.raises(ParserNotFoundError):
        run_async(
            service.execute(LLMExecutionRequest(prompt_name="custom_prompt", variables={"topic": "x"}))
        )


def test_malformed_provider_output_raises_parser_error_safely() -> None:
    """Malformed provider text should surface parser failures without repair or retry."""

    prompt_registry = create_builtin_prompt_registry()
    parser_registry = build_builtin_parser_registry()
    provider_registry = create_provider_registry()
    provider_registry.register(RecordingLLMProvider(response_text="Not the expected CTA format"))
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
    )

    with pytest.raises(StructuredOutputError):
        run_async(
            service.execute(
                LLMExecutionRequest(
                    prompt_name=GAMING_CTA,
                    variables={
                        "game": "Minecraft",
                        "topic": "gaming facts",
                        "platform": "YouTube Shorts",
                        "tone": "natural",
                    },
                )
            )
        )


def test_service_source_contains_no_hardcoded_prompt_name_branching() -> None:
    """The service implementation should stay registry-driven rather than prompt-specific."""

    source = Path("creatoros/services/llm_execution.py").read_text(encoding="utf-8")

    assert "GAMING_CTA" not in source
    assert "YOUTUBE_SHORTS_SCRIPT" not in source
    assert "if request.prompt_name" not in source


def test_mock_end_to_end_gaming_cta_executes_fully_offline() -> None:
    """The first full prompt -> provider -> parser path should work offline with the mock provider."""

    prompt_registry = create_builtin_prompt_registry()
    parser_registry = build_builtin_parser_registry()
    provider_registry = create_provider_registry()
    provider_registry.register(MockLLMProvider(response_text=CTA_RESPONSE_TEXT))
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
        settings=build_settings(),
    )

    result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name=GAMING_CTA,
                variables={
                    "game": "Minecraft",
                    "topic": "gaming facts",
                    "platform": "YouTube Shorts",
                    "tone": "natural",
                },
            )
        )
    )

    assert isinstance(result.output, GamingCTAOutput)
    assert result.output.cta == "Which one would you test next?"
    assert result.provider_name == "mock"


def test_openai_provider_with_fake_client_executes_fully_offline() -> None:
    """OpenAI should plug into the same application service path without a real API key."""

    prompt_registry = create_builtin_prompt_registry()
    parser_registry = build_builtin_parser_registry()
    provider_registry = create_provider_registry()
    fake_responses = FakeResponsesClient(response=build_openai_response())
    provider_registry.register(
        OpenAILLMProvider(
            client=FakeOpenAIClient(fake_responses),
            timeout_seconds=30.0,
            max_retries=0,
        )
    )
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
        settings=build_settings(default_llm_provider="mock", default_llm_model=DEFAULT_OPENAI_MODEL),
    )

    result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name=GAMING_CTA,
                provider_name="openai",
                model=DEFAULT_OPENAI_MODEL,
                variables={
                    "game": "Minecraft",
                    "topic": "gaming facts",
                    "platform": "YouTube Shorts",
                    "tone": "natural",
                },
                temperature=0.3,
                max_output_tokens=120,
                timeout_seconds=9.0,
            )
        )
    )

    assert isinstance(result.output, GamingCTAOutput)
    assert result.provider_name == "openai"
    assert result.output.alternative == "What gaming myth should we check next?"
    assert fake_responses.calls[0]["model"] == DEFAULT_OPENAI_MODEL
    assert fake_responses.calls[0]["input"][0]["role"] == "system"
    assert fake_responses.calls[0]["input"][1]["role"] == "user"


def test_service_logs_only_safe_lifecycle_information() -> None:
    """Service logs should avoid prompt content, variable values, and provider response text."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition())
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="custom_prompt",
            parser=lambda text: SimpleParsedOutput(value=text),
            output_model_type=SimpleParsedOutput,
        )
    )
    provider_registry = create_provider_registry()
    provider_registry.register(RecordingLLMProvider(response_text="VERY_SECRET_RESPONSE"))
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
    )
    logger = FakeLogger()
    service.logger = logger

    run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name="custom_prompt",
                variables={
                    "topic": "VERY_SECRET_TOPIC",
                    "extra": "safe",
                },
            )
        )
    )

    combined = "".join(str(event["kwargs"]) for event in logger.events)
    assert "VERY_SECRET_TOPIC" not in combined
    assert "Stay concise." not in combined
    assert "VERY_SECRET_RESPONSE" not in combined
    assert any(event["event"] == "llm_execution_started" for event in logger.events)
    assert any(event["event"] == "llm_execution_completed" for event in logger.events)


def test_result_preserves_normalized_identity_and_omits_raw_response_field() -> None:
    """Execution results should preserve safe identities without storing a raw response field."""

    service = create_llm_execution_service(
        provider_registry=create_provider_registry(),
        settings=build_settings(),
    )
    service.provider_registry.register(MockLLMProvider(response_text=CTA_RESPONSE_TEXT))

    result = run_async(
        service.execute(
            LLMExecutionRequest(
                prompt_name=GAMING_CTA,
                variables={
                    "game": "Minecraft",
                    "topic": "gaming facts",
                    "platform": "YouTube Shorts",
                    "tone": "natural",
                },
            )
        )
    )

    assert result.prompt_name == GAMING_CTA
    assert result.provider_name == "mock"
    assert result.model == "mock-model"
    assert "text" not in result.model_dump()
    assert "raw_response" not in result.model_dump()


def test_service_produces_no_registry_side_effects_and_no_retries() -> None:
    """Execution should not mutate registries and should call the provider only once."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(build_prompt_definition())
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="custom_prompt",
            parser=lambda text: SimpleParsedOutput(value=text),
            output_model_type=SimpleParsedOutput,
        )
    )
    provider_registry = create_provider_registry()
    provider = RecordingLLMProvider()
    provider_registry.register(provider)
    service = build_custom_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        provider_registry=provider_registry,
    )
    before_prompts = prompt_registry.list_prompts()
    before_parsers = parser_registry.list_prompt_names()
    before_providers = provider_registry.list_providers()

    run_async(
        service.execute(LLMExecutionRequest(prompt_name="custom_prompt", variables={"topic": "x"}))
    )

    assert provider.calls == 1
    assert prompt_registry.list_prompts() == before_prompts
    assert parser_registry.list_prompt_names() == before_parsers
    assert provider_registry.list_providers() == before_providers


def test_factory_builds_safe_mock_only_service() -> None:
    """The convenience factory should support offline mock-only execution by default."""

    prompt_registry = create_prompt_registry()
    prompt_registry.register(
        PromptDefinition(
            name="factory_prompt",
            version=1,
            status=PromptStatus.ACTIVE,
            format=PromptFormat.TEXT,
            messages=[PromptMessage(role=PromptRole.USER, content="Factory prompt.")],
            variables=[],
        )
    )
    parser_registry = create_parser_registry()
    parser_registry.register(
        ParserRegistration(
            prompt_name="factory_prompt",
            parser=lambda text: SimpleParsedOutput(value=text),
            output_model_type=SimpleParsedOutput,
        )
    )
    service = create_llm_execution_service(
        prompt_registry=prompt_registry,
        parser_registry=parser_registry,
        settings=build_settings(),
    )

    assert service.provider_registry.contains("llm", "mock") is True
    assert service.provider_registry.contains("llm", "openai") is False

    result = run_async(
        service.execute(
            LLMExecutionRequest(prompt_name="factory_prompt")
        )
    )

    assert isinstance(result.output, SimpleParsedOutput)


def test_missing_prompt_fails_with_existing_prompt_registry_error() -> None:
    """Missing prompts should preserve the existing prompt registry exception type."""

    service = create_llm_execution_service(settings=build_settings())

    with pytest.raises(PromptNotFoundError):
        run_async(service.execute(LLMExecutionRequest(prompt_name="missing_prompt")))
