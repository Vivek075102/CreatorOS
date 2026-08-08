"""Unit tests for the provider-independent gaming research agent."""

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
    GamingKeywordExpansionRequest,
    GamingOpportunityEvaluationRequest,
    GamingResearchAgent,
    GamingTrendDiscoveryRequest,
    ResearchExecutionOptions,
)
from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderAuthenticationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingKeywordExpansionOutput,
    GamingOpportunityEvaluationOutput,
    GamingTrendDiscoveryOutput,
)
from creatoros.prompts import (
    GAMING_DISCOVER_TRENDS,
    GAMING_EVALUATE_OPPORTUNITY,
    GAMING_EXPAND_KEYWORDS,
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

TREND_DISCOVERY_RESPONSE = (
    "TITLE:\nMinecraft Myth Test\n"
    "GAME:\nMinecraft\n"
    "TOPIC:\ngaming myths\n"
    "ANGLE:\ntest one commonly repeated mechanic claim\n"
    "WHY_NOW:\nThe supplied research signals show recurring discussion.\n"
    "SOURCE_SUMMARY:\nThe supplied signals describe repeated player discussion of the same mechanic claim.\n"
    "CONFIDENCE:\nmedium"
)

OPPORTUNITY_EVALUATION_RESPONSE = (
    "DECISION:\naccept\n"
    "SCORE:\n82\n"
    "STRENGTHS:\nClear curiosity and short-form fit.\n"
    "RISKS:\nEvidence remains limited to supplied signals.\n"
    "RECOMMENDED_ANGLE:\nTest one commonly repeated mechanic claim carefully.\n"
    "HOOK_DIRECTION:\nChallenge the viewer's assumption immediately.\n"
    "REASON:\nThe topic is focused enough for a cautious short."
)

KEYWORD_EXPANSION_RESPONSE = (
    "PRIMARY:\n- minecraft myths\n- minecraft mechanics\n"
    "RELATED:\n- redstone myths\n"
    "QUESTIONS:\n- does this mechanic actually work?\n"
    "ENTITIES:\n- redstone"
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
    """Injected fake OpenAI client for provider-independent tests."""

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
    text: str = TREND_DISCOVERY_RESPONSE,
    model: str = DEFAULT_OPENAI_MODEL,
) -> Response:
    """Create a deterministic fake SDK response for the OpenAI agent test."""

    response = Response.model_construct(
        id="resp_openai_research",
        created_at=0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        model=model,
        object="response",
        output=[
            ResponseOutputMessage.model_construct(
                id="msg_openai_research",
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
    response._request_id = "req_openai_research"
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


def test_research_agent_accepts_llm_execution_service() -> None:
    """The research agent should accept a real LLMExecutionService dependency."""

    agent = GamingResearchAgent(build_mock_service(response_text=TREND_DISCOVERY_RESPONSE))

    assert isinstance(agent.llm_execution_service, LLMExecutionService)


def test_research_agent_requires_valid_service_dependency() -> None:
    """Invalid dependencies should be rejected safely."""

    with pytest.raises(CreatorOSValidationError, match="llm_execution_service must be an LLMExecutionService"):
        GamingResearchAgent(object())  # type: ignore[arg-type]


def test_trend_discovery_request_rejects_blank_inputs() -> None:
    """Trend discovery inputs should reject blank required strings."""

    with pytest.raises(ValueError, match="game must not be blank"):
        GamingTrendDiscoveryRequest(
            game="   ",
            topic="gaming myths",
            research_signals="Supplied signals.",
            platform="youtube_shorts",
            target_duration_seconds=30,
        )


def test_target_duration_rejects_non_positive_values() -> None:
    """Positive durations are required for research prompts that use a target duration."""

    with pytest.raises(ValueError):
        GamingOpportunityEvaluationRequest(
            game="Minecraft",
            title="Minecraft Myth Test",
            topic="gaming myths",
            angle="Test one mechanic claim",
            source_summary="Supplied source summary.",
            platform="youtube_shorts",
            target_duration_seconds=0,
        )


def test_discover_trends_uses_expected_prompt_and_variables() -> None:
    """Trend discovery should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingTrendDiscoveryOutput(
            title="Minecraft Myth Test",
            game="Minecraft",
            topic="gaming myths",
            angle="test one commonly repeated mechanic claim",
            why_now="The supplied research signals show recurring discussion.",
            source_summary="The supplied signals describe repeated player discussion.",
            confidence="medium",
        )
    )
    agent = GamingResearchAgent(spy_service)

    result = run_async(
        agent.discover_trends(
            GamingTrendDiscoveryRequest(
                game="Minecraft",
                topic="gaming myths",
                research_signals="Players keep repeating the same myth.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.title == "Minecraft Myth Test"
    assert recorded_request.prompt_name == GAMING_DISCOVER_TRENDS
    assert recorded_request.variables == {
        "game": "Minecraft",
        "topic": "gaming myths",
        "research_signals": "Players keep repeating the same myth.",
        "platform": "youtube_shorts",
        "target_duration_seconds": 30,
    }


def test_evaluate_opportunity_uses_expected_prompt_and_variables() -> None:
    """Opportunity evaluation should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingOpportunityEvaluationOutput(
            decision="accept",
            score=82,
            strengths="Clear curiosity and short-form fit.",
            risks="Evidence remains limited to supplied signals.",
            recommended_angle="Test one commonly repeated mechanic claim carefully.",
            hook_direction="Challenge the viewer's assumption immediately.",
            reason="The topic is focused enough for a cautious short.",
        )
    )
    agent = GamingResearchAgent(spy_service)

    result = run_async(
        agent.evaluate_opportunity(
            GamingOpportunityEvaluationRequest(
                game="Minecraft",
                title="Minecraft Myth Test",
                topic="gaming myths",
                angle="test one commonly repeated mechanic claim",
                source_summary="The supplied signals describe repeated player discussion.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.decision == "accept"
    assert recorded_request.prompt_name == GAMING_EVALUATE_OPPORTUNITY
    assert recorded_request.variables == {
        "game": "Minecraft",
        "title": "Minecraft Myth Test",
        "topic": "gaming myths",
        "angle": "test one commonly repeated mechanic claim",
        "source_summary": "The supplied signals describe repeated player discussion.",
        "platform": "youtube_shorts",
        "target_duration_seconds": 30,
    }


def test_expand_keywords_uses_expected_prompt_and_variables() -> None:
    """Keyword expansion should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingKeywordExpansionOutput(
            primary=("minecraft myths",),
            related=("redstone myths",),
            questions=("does this mechanic actually work?",),
            entities=("redstone",),
        )
    )
    agent = GamingResearchAgent(spy_service)

    result = run_async(
        agent.expand_keywords(
            GamingKeywordExpansionRequest(
                game="Minecraft",
                topic="gaming myths",
                seed_keywords="minecraft myths, redstone myths",
                platform="youtube_shorts",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.primary == ("minecraft myths",)
    assert recorded_request.prompt_name == GAMING_EXPAND_KEYWORDS
    assert recorded_request.variables == {
        "game": "Minecraft",
        "topic": "gaming myths",
        "seed_keywords": "minecraft myths, redstone myths",
        "platform": "youtube_shorts",
    }


def test_execution_options_remain_at_application_boundary() -> None:
    """Provider-neutral execution overrides should be optional and separate from research inputs."""

    spy_service = SpyExecutionService(
        GamingTrendDiscoveryOutput(
            title="Minecraft Myth Test",
            game="Minecraft",
            topic="gaming myths",
            angle="test one commonly repeated mechanic claim",
            why_now="The supplied research signals show recurring discussion.",
            source_summary="The supplied signals describe repeated player discussion.",
            confidence="medium",
        )
    )
    agent = GamingResearchAgent(spy_service)

    run_async(
        agent.discover_trends(
            GamingTrendDiscoveryRequest(
                game="Minecraft",
                topic="gaming myths",
                research_signals="Players keep repeating the same myth.",
                platform="youtube_shorts",
                target_duration_seconds=30,
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


def test_unexpected_output_model_is_rejected_safely() -> None:
    """The research agent should fail safely if the execution service returns the wrong typed model."""

    spy_service = SpyExecutionService(
        GamingOpportunityEvaluationOutput(
            decision="accept",
            score=82,
            strengths="Clear curiosity and short-form fit.",
            risks="Evidence remains limited to supplied signals.",
            recommended_angle="Test one commonly repeated mechanic claim carefully.",
            hook_direction="Challenge the viewer's assumption immediately.",
            reason="The topic is focused enough for a cautious short.",
        )
    )
    agent = GamingResearchAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.discover_trends(
                GamingTrendDiscoveryRequest(
                    game="Minecraft",
                    topic="gaming myths",
                    research_signals="Players keep repeating the same myth.",
                    platform="youtube_shorts",
                    target_duration_seconds=30,
                )
            )
        )


def test_discover_trends_completes_fully_with_mock() -> None:
    """Trend discovery should execute end-to-end through the real service path with the mock provider."""

    agent = GamingResearchAgent(build_mock_service(response_text=TREND_DISCOVERY_RESPONSE))

    result = run_async(
        agent.discover_trends(
            GamingTrendDiscoveryRequest(
                game="Minecraft",
                topic="gaming myths",
                research_signals="Players keep repeating the same myth.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    assert isinstance(result, GamingTrendDiscoveryOutput)
    assert result.title == "Minecraft Myth Test"


def test_evaluate_opportunity_completes_fully_with_mock() -> None:
    """Opportunity evaluation should execute end-to-end through the real service path with the mock provider."""

    agent = GamingResearchAgent(build_mock_service(response_text=OPPORTUNITY_EVALUATION_RESPONSE))

    result = run_async(
        agent.evaluate_opportunity(
            GamingOpportunityEvaluationRequest(
                game="Minecraft",
                title="Minecraft Myth Test",
                topic="gaming myths",
                angle="test one commonly repeated mechanic claim",
                source_summary="The supplied signals describe repeated player discussion.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    assert isinstance(result, GamingOpportunityEvaluationOutput)
    assert result.score == 82


def test_expand_keywords_completes_fully_with_mock() -> None:
    """Keyword expansion should execute end-to-end through the real service path with the mock provider."""

    agent = GamingResearchAgent(build_mock_service(response_text=KEYWORD_EXPANSION_RESPONSE))

    result = run_async(
        agent.expand_keywords(
            GamingKeywordExpansionRequest(
                game="Minecraft",
                topic="gaming myths",
                seed_keywords="minecraft myths, redstone myths",
                platform="youtube_shorts",
            )
        )
    )

    assert isinstance(result, GamingKeywordExpansionOutput)
    assert result.primary == ("minecraft myths", "minecraft mechanics")


def test_research_agent_supports_fake_openai_through_real_service_path() -> None:
    """The research agent should work unchanged with the fake OpenAI provider path."""

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
    agent = GamingResearchAgent(service)

    result = run_async(
        agent.discover_trends(
            GamingTrendDiscoveryRequest(
                game="Minecraft",
                topic="gaming myths",
                research_signals="Players keep repeating the same myth.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            ),
            execution_options=ResearchExecutionOptions(
                provider_name="openai",
                model=DEFAULT_OPENAI_MODEL,
            ),
        )
    )

    assert isinstance(result, GamingTrendDiscoveryOutput)
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
    agent = GamingResearchAgent(service)

    with pytest.raises(ProviderAuthenticationError, match="safe provider failure"):
        run_async(
            agent.discover_trends(
                GamingTrendDiscoveryRequest(
                    game="Minecraft",
                    topic="gaming myths",
                    research_signals="Players keep repeating the same myth.",
                    platform="youtube_shorts",
                    target_duration_seconds=30,
                )
            )
        )


def test_research_agent_module_avoids_direct_provider_parser_and_prompt_path_coupling() -> None:
    """The research agent module should depend on the execution service boundary, not lower-level internals."""

    module_source = Path("creatoros/agents/research.py").read_text(encoding="utf-8")

    assert "openai" not in module_source.casefold()
    assert "parse_gaming_" not in module_source
    assert "PromptRegistry" not in module_source
    assert "provider.generate" not in module_source
    assert "prompts/" not in module_source
    assert "WorkflowRuntime" not in module_source
    assert "Publishing" not in module_source
    assert "sqlalchemy" not in module_source.casefold()
    assert "retry" not in module_source.casefold()
