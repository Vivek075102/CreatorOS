"""Unit tests for the provider-independent gaming script agent."""

from __future__ import annotations

import asyncio
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

from creatoros.agents import (
    GamingCTAGenerationRequest,
    GamingHookGenerationRequest,
    GamingScriptAgent,
    GamingScriptGenerationRequest,
    ResearchExecutionOptions,
)
from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderAuthenticationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import GamingCTAOutput, GamingHookOutput, YouTubeShortsScriptOutput
from creatoros.prompts import (
    GAMING_CTA,
    GAMING_HOOK,
    YOUTUBE_SHORTS_SCRIPT,
    create_builtin_prompt_registry,
)
from creatoros.providers import create_provider_registry
from creatoros.providers.mock import MockLLMProvider
from creatoros.providers.openai import DEFAULT_OPENAI_MODEL, OpenAILLMProvider
from creatoros.services import (
    LLMExecutionRequest,
    LLMExecutionResult,
    LLMExecutionService,
    create_llm_execution_service,
)

SCRIPT_RESPONSE = (
    "TITLE:\nMinecraft Myth Test\n"
    "HOOK:\nYou probably still believe this Minecraft myth.\n"
    "BODY:\nPlayers keep repeating this mechanic claim, but the supplied evidence suggests it needs a closer look.\n"
    "ENDING:\nSo before you trust the myth, test the mechanic yourself.\n"
    "CALL_TO_ACTION:\nWhich Minecraft myth should we check next?\n"
    "ESTIMATED_DURATION_SECONDS:\n30\n"
    "EVIDENCE_NOTE:\nThe script uses only the supplied research summary and treats uncertain claims cautiously."
)

HOOK_RESPONSE = (
    "HOOK_1:\nYou probably still believe this Minecraft myth.\n"
    "HOOK_2:\nThis Minecraft mechanic might not work the way you think.\n"
    "HOOK_3:\nPlayers keep repeating this Minecraft claim - but is it actually true?\n"
    "BEST_HOOK:\nYou probably still believe this Minecraft myth.\n"
    "WHY:\nIt creates curiosity quickly without making an unsupported factual claim."
)

CTA_RESPONSE = (
    "CTA:\nWhich Minecraft myth should we test next?\n"
    "ALTERNATIVE:\nTry this yourself and tell me what happened."
)


@dataclass
class FakeResponsesClient:
    """Simple async fake that records OpenAI responses calls."""

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
    """Injected fake OpenAI client for provider-independent script tests."""

    responses: FakeResponsesClient


class SpyExecutionService(LLMExecutionService):
    """Minimal fake LLM execution service for agent-unit boundary tests."""

    def __init__(self, output: CreatorOSModel) -> None:
        self.prompt_registry = None
        self.parser_registry = None
        self.provider_registry = None
        self.settings = None
        self.prompt_renderer = None
        self.logger = None
        self.output = output
        self.calls: list[LLMExecutionRequest] = []

    async def execute(self, request: LLMExecutionRequest) -> LLMExecutionResult[CreatorOSModel]:
        self.calls.append(request.model_copy(deep=True))
        return LLMExecutionResult[CreatorOSModel](
            prompt_name=request.prompt_name,
            prompt_version=1,
            provider_name=request.provider_name or "mock",
            model=request.model or "mock-model",
            output=self.output,
            usage=None,
            request_id="spy_request",
            metadata={},
        )


def build_openai_response(
    *,
    text: str = SCRIPT_RESPONSE,
    model: str = DEFAULT_OPENAI_MODEL,
) -> Response:
    """Create a deterministic fake SDK response for the OpenAI script-agent test."""

    response = Response.model_construct(
        id="resp_openai_script",
        created_at=0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        model=model,
        object="response",
        output=[
            ResponseOutputMessage.model_construct(
                id="msg_openai_script",
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
    response._request_id = "req_openai_script"
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


def run_async(coro) -> Any:
    """Execute async agent calls in synchronous tests."""

    return asyncio.run(coro)


def build_mock_service(*, response_text: str) -> LLMExecutionService:
    """Create a real LLMExecutionService wired to the builtin prompt/parser path and mock provider."""

    provider_registry = create_provider_registry()
    provider_registry.register(MockLLMProvider(response_text=response_text))
    return create_llm_execution_service(
        prompt_registry=create_builtin_prompt_registry(),
        provider_registry=provider_registry,
        settings=build_settings(),
    )


def test_script_agent_accepts_llm_execution_service() -> None:
    """The script agent should accept a real LLMExecutionService dependency."""

    agent = GamingScriptAgent(build_mock_service(response_text=SCRIPT_RESPONSE))

    assert isinstance(agent.llm_execution_service, LLMExecutionService)


def test_script_agent_requires_valid_service_dependency() -> None:
    """Invalid dependencies should be rejected safely."""

    with pytest.raises(CreatorOSValidationError, match="llm_execution_service must be an LLMExecutionService"):
        GamingScriptAgent(object())  # type: ignore[arg-type]


def test_script_generation_request_trims_values() -> None:
    """Script-generation inputs should trim surrounding whitespace."""

    request = GamingScriptGenerationRequest(
        title="  Minecraft Myth Test  ",
        game="  Minecraft  ",
        topic="  gaming myths  ",
        angle="  test one mechanic claim  ",
        hook_direction="  challenge a common belief  ",
        platform="  youtube_shorts  ",
        target_duration_seconds=30,
        source_summary="  supplied research summary  ",
    )

    assert request.title == "Minecraft Myth Test"
    assert request.game == "Minecraft"
    assert request.topic == "gaming myths"
    assert request.angle == "test one mechanic claim"
    assert request.hook_direction == "challenge a common belief"
    assert request.platform == "youtube_shorts"
    assert request.source_summary == "supplied research summary"


def test_script_generation_request_rejects_blank_required_fields() -> None:
    """Blank required script-generation fields should fail validation."""

    with pytest.raises(ValueError, match="title must not be blank"):
        GamingScriptGenerationRequest(
            title="   ",
            game="Minecraft",
            topic="gaming myths",
            angle="test one mechanic claim",
            hook_direction="challenge a common belief",
            platform="youtube_shorts",
            target_duration_seconds=30,
            source_summary="supplied research summary",
        )


def test_script_generation_request_rejects_non_positive_duration() -> None:
    """Target duration must be positive for full script generation."""

    with pytest.raises(ValueError):
        GamingScriptGenerationRequest(
            title="Minecraft Myth Test",
            game="Minecraft",
            topic="gaming myths",
            angle="test one mechanic claim",
            hook_direction="challenge a common belief",
            platform="youtube_shorts",
            target_duration_seconds=0,
            source_summary="supplied research summary",
        )


def test_hook_generation_request_validation_works() -> None:
    """Hook-generation input validation should reject blank required fields."""

    with pytest.raises(ValueError, match="source_summary must not be blank"):
        GamingHookGenerationRequest(
            game="Minecraft",
            title="Minecraft Myth Test",
            topic="gaming myths",
            angle="test one mechanic claim",
            source_summary="   ",
            platform="youtube_shorts",
        )


def test_cta_generation_request_validation_works() -> None:
    """CTA-generation input validation should reject blank required fields."""

    with pytest.raises(ValueError, match="tone must not be blank"):
        GamingCTAGenerationRequest(
            game="Minecraft",
            topic="gaming myths",
            platform="youtube_shorts",
            tone="   ",
        )


def test_generate_script_uses_expected_prompt_and_variables() -> None:
    """Full script generation should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        YouTubeShortsScriptOutput(
            title="Minecraft Myth Test",
            hook="You probably still believe this Minecraft myth.",
            body="Players keep repeating this mechanic claim, but the supplied evidence suggests it needs a closer look.",
            ending="So before you trust the myth, test the mechanic yourself.",
            call_to_action="Which Minecraft myth should we check next?",
            estimated_duration_seconds=30,
            evidence_note="The script uses only the supplied research summary and treats uncertain claims cautiously.",
        )
    )
    agent = GamingScriptAgent(spy_service)

    result = run_async(
        agent.generate_script(
            GamingScriptGenerationRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                hook_direction="challenge a common belief",
                platform="youtube_shorts",
                target_duration_seconds=30,
                source_summary="supplied research summary",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.title == "Minecraft Myth Test"
    assert result.estimated_duration_seconds == 30
    assert recorded_request.prompt_name == YOUTUBE_SHORTS_SCRIPT
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "game": "Minecraft",
        "topic": "gaming myths",
        "angle": "test one mechanic claim",
        "hook_direction": "challenge a common belief",
        "platform": "youtube_shorts",
        "target_duration_seconds": 30,
        "source_summary": "supplied research summary",
    }


def test_generate_hooks_uses_expected_prompt_and_variables() -> None:
    """Hook generation should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingHookOutput(
            hook_1="You probably still believe this Minecraft myth.",
            hook_2="This Minecraft mechanic might not work the way you think.",
            hook_3="Players keep repeating this Minecraft claim - but is it actually true?",
            best_hook="You probably still believe this Minecraft myth.",
            why="It creates curiosity quickly without making an unsupported factual claim.",
        )
    )
    agent = GamingScriptAgent(spy_service)

    result = run_async(
        agent.generate_hooks(
            GamingHookGenerationRequest(
                game="Minecraft",
                title="Minecraft Myth Test",
                topic="gaming myths",
                angle="test one mechanic claim",
                source_summary="supplied research summary",
                platform="youtube_shorts",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.best_hook == "You probably still believe this Minecraft myth."
    assert recorded_request.prompt_name == GAMING_HOOK
    assert recorded_request.variables == {
        "game": "Minecraft",
        "title": "Minecraft Myth Test",
        "topic": "gaming myths",
        "angle": "test one mechanic claim",
        "source_summary": "supplied research summary",
        "platform": "youtube_shorts",
    }


def test_generate_cta_uses_expected_prompt_and_variables() -> None:
    """CTA generation should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingCTAOutput(
            cta="Which Minecraft myth should we test next?",
            alternative="Try this yourself and tell me what happened.",
        )
    )
    agent = GamingScriptAgent(spy_service)

    result = run_async(
        agent.generate_cta(
            GamingCTAGenerationRequest(
                game="Minecraft",
                topic="gaming myths",
                platform="youtube_shorts",
                tone="natural",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.cta == "Which Minecraft myth should we test next?"
    assert recorded_request.prompt_name == GAMING_CTA
    assert recorded_request.variables == {
        "game": "Minecraft",
        "topic": "gaming myths",
        "platform": "youtube_shorts",
        "tone": "natural",
    }


def test_script_agent_reuses_application_boundary_execution_options() -> None:
    """Provider-neutral execution overrides should reuse the shared application-level model."""

    spy_service = SpyExecutionService(
        YouTubeShortsScriptOutput(
            title="Minecraft Myth Test",
            hook="You probably still believe this Minecraft myth.",
            body="Players keep repeating this mechanic claim, but the supplied evidence suggests it needs a closer look.",
            ending="So before you trust the myth, test the mechanic yourself.",
            call_to_action="Which Minecraft myth should we check next?",
            estimated_duration_seconds=30,
            evidence_note="The script uses only the supplied research summary and treats uncertain claims cautiously.",
        )
    )
    agent = GamingScriptAgent(spy_service)

    run_async(
        agent.generate_script(
            GamingScriptGenerationRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                hook_direction="challenge a common belief",
                platform="youtube_shorts",
                target_duration_seconds=30,
                source_summary="supplied research summary",
            ),
            execution_options=ResearchExecutionOptions(
                provider_name="openai",
                model="gpt-5-mini",
                temperature=0.3,
                max_output_tokens=120,
                timeout_seconds=9.0,
            ),
        )
    )

    recorded_request = spy_service.calls[0]
    assert recorded_request.provider_name == "openai"
    assert recorded_request.model == "gpt-5-mini"
    assert recorded_request.temperature == 0.3
    assert recorded_request.max_output_tokens == 120
    assert recorded_request.timeout_seconds == 9.0


def test_unexpected_script_output_type_is_rejected_safely() -> None:
    """The script agent should fail safely if full script execution returns the wrong typed model."""

    spy_service = SpyExecutionService(
        GamingHookOutput(
            hook_1="You probably still believe this Minecraft myth.",
            hook_2="This Minecraft mechanic might not work the way you think.",
            hook_3="Players keep repeating this Minecraft claim - but is it actually true?",
            best_hook="You probably still believe this Minecraft myth.",
            why="It creates curiosity quickly without making an unsupported factual claim.",
        )
    )
    agent = GamingScriptAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_script(
                GamingScriptGenerationRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    topic="gaming myths",
                    angle="test one mechanic claim",
                    hook_direction="challenge a common belief",
                    platform="youtube_shorts",
                    target_duration_seconds=30,
                    source_summary="supplied research summary",
                )
            )
        )


def test_unexpected_hook_output_type_is_rejected_safely() -> None:
    """The script agent should fail safely if hook execution returns the wrong typed model."""

    spy_service = SpyExecutionService(
        GamingCTAOutput(
            cta="Which Minecraft myth should we test next?",
            alternative="Try this yourself and tell me what happened.",
        )
    )
    agent = GamingScriptAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_hooks(
                GamingHookGenerationRequest(
                    game="Minecraft",
                    title="Minecraft Myth Test",
                    topic="gaming myths",
                    angle="test one mechanic claim",
                    source_summary="supplied research summary",
                    platform="youtube_shorts",
                )
            )
        )


def test_unexpected_cta_output_type_is_rejected_safely() -> None:
    """The script agent should fail safely if CTA execution returns the wrong typed model."""

    spy_service = SpyExecutionService(
        YouTubeShortsScriptOutput(
            title="Minecraft Myth Test",
            hook="You probably still believe this Minecraft myth.",
            body="Players keep repeating this mechanic claim, but the supplied evidence suggests it needs a closer look.",
            ending="So before you trust the myth, test the mechanic yourself.",
            call_to_action="Which Minecraft myth should we check next?",
            estimated_duration_seconds=30,
            evidence_note="The script uses only the supplied research summary and treats uncertain claims cautiously.",
        )
    )
    agent = GamingScriptAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_cta(
                GamingCTAGenerationRequest(
                    game="Minecraft",
                    topic="gaming myths",
                    platform="youtube_shorts",
                    tone="natural",
                )
            )
        )


def test_generate_script_completes_fully_with_mock() -> None:
    """Full script generation should execute end-to-end through the real service path with the mock provider."""

    agent = GamingScriptAgent(build_mock_service(response_text=SCRIPT_RESPONSE))

    result = run_async(
        agent.generate_script(
            GamingScriptGenerationRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                hook_direction="challenge a common belief",
                platform="youtube_shorts",
                target_duration_seconds=30,
                source_summary="supplied research summary",
            )
        )
    )

    assert isinstance(result, YouTubeShortsScriptOutput)
    assert result.call_to_action == "Which Minecraft myth should we check next?"


def test_generate_hooks_completes_fully_with_mock() -> None:
    """Hook generation should execute end-to-end through the real service path with the mock provider."""

    agent = GamingScriptAgent(build_mock_service(response_text=HOOK_RESPONSE))

    result = run_async(
        agent.generate_hooks(
            GamingHookGenerationRequest(
                game="Minecraft",
                title="Minecraft Myth Test",
                topic="gaming myths",
                angle="test one mechanic claim",
                source_summary="supplied research summary",
                platform="youtube_shorts",
            )
        )
    )

    assert isinstance(result, GamingHookOutput)
    assert result.best_hook == "You probably still believe this Minecraft myth."


def test_generate_cta_completes_fully_with_mock() -> None:
    """CTA generation should execute end-to-end through the real service path with the mock provider."""

    agent = GamingScriptAgent(build_mock_service(response_text=CTA_RESPONSE))

    result = run_async(
        agent.generate_cta(
            GamingCTAGenerationRequest(
                game="Minecraft",
                topic="gaming myths",
                platform="youtube_shorts",
                tone="natural",
            )
        )
    )

    assert isinstance(result, GamingCTAOutput)
    assert result.alternative == "Try this yourself and tell me what happened."


def test_script_agent_supports_fake_openai_through_real_service_path() -> None:
    """The script agent should work unchanged with the fake OpenAI provider path."""

    fake_responses = FakeResponsesClient(response=build_openai_response())
    provider_registry = create_provider_registry()
    provider_registry.register(
        OpenAILLMProvider(
            client=FakeOpenAIClient(fake_responses),
            timeout_seconds=30.0,
            max_retries=0,
        )
    )
    service = create_llm_execution_service(
        prompt_registry=create_builtin_prompt_registry(),
        provider_registry=provider_registry,
        settings=build_settings(default_llm_provider="mock", default_llm_model=DEFAULT_OPENAI_MODEL),
    )
    agent = GamingScriptAgent(service)

    result = run_async(
        agent.generate_script(
            GamingScriptGenerationRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                hook_direction="challenge a common belief",
                platform="youtube_shorts",
                target_duration_seconds=30,
                source_summary="supplied research summary",
            ),
            execution_options=ResearchExecutionOptions(
                provider_name="openai",
                model=DEFAULT_OPENAI_MODEL,
            ),
        )
    )

    assert isinstance(result, YouTubeShortsScriptOutput)
    assert result.title == "Minecraft Myth Test"
    assert fake_responses.calls[0]["model"] == DEFAULT_OPENAI_MODEL


def test_service_errors_propagate_safely() -> None:
    """Service and provider errors should propagate without agent-level secret leakage."""

    class ExplodingService(LLMExecutionService):
        async def execute(self, request: LLMExecutionRequest) -> LLMExecutionResult[CreatorOSModel]:
            del request
            raise ProviderAuthenticationError("safe provider failure")

    service = ExplodingService(
        create_builtin_prompt_registry(),
        create_llm_execution_service(settings=build_settings()).parser_registry,
        create_provider_registry(),
        build_settings(),
    )
    agent = GamingScriptAgent(service)

    with pytest.raises(ProviderAuthenticationError, match="safe provider failure"):
        run_async(
            agent.generate_script(
                GamingScriptGenerationRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    topic="gaming myths",
                    angle="test one mechanic claim",
                    hook_direction="challenge a common belief",
                    platform="youtube_shorts",
                    target_duration_seconds=30,
                    source_summary="supplied research summary",
                )
            )
        )


def test_script_agent_module_avoids_direct_provider_parser_and_prompt_path_coupling() -> None:
    """The script agent module should depend on the execution service boundary, not lower-level internals."""

    module_source = Path("creatoros/agents/script.py").read_text(encoding="utf-8")

    assert "openai" not in module_source.casefold()
    assert "parse_youtube_shorts_script" not in module_source
    assert "parse_gaming_hook" not in module_source
    assert "parse_gaming_cta" not in module_source
    assert "PromptRegistry" not in module_source
    assert "PromptRenderer" not in module_source
    assert "provider.generate" not in module_source
    assert "prompts/" not in module_source
    assert "WorkflowRuntime" not in module_source
    assert "Publishing" not in module_source
    assert "sqlalchemy" not in module_source.casefold()
    assert "retry" not in module_source.casefold()
