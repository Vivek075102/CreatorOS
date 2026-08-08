"""Unit tests for the provider-independent gaming storyboard agent."""

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
    GamingStoryboardAgent,
    GamingStoryboardSceneBreakdownRequest,
    GamingStoryboardTimingReviewRequest,
    GamingStoryboardVisualDirectionRequest,
    ResearchExecutionOptions,
)
from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderAuthenticationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    StoryboardSceneBreakdownOutput,
    StoryboardTimingReviewOutput,
    StoryboardVisualDirectionOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.prompts import (
    STORYBOARD_SCENE_BREAKDOWN,
    STORYBOARD_TIMING_REVIEW,
    STORYBOARD_VISUAL_DIRECTION,
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

SCENE_BREAKDOWN_RESPONSE = (
    "STORYBOARD_TITLE:\nMinecraft Myth Test\n"
    "SCENE_1:\n"
    "PURPOSE:\nOpen with the hook.\n"
    "SCRIPT_BEAT:\nYou probably still believe this Minecraft myth.\n"
    "VISUAL:\nClose-up gameplay view of the mechanic in action.\n"
    "ON_SCREEN_TEXT:\nMinecraft myth?\n"
    "DURATION_SECONDS:\n8\n"
    "SCENE_2:\n"
    "PURPOSE:\nResolve the claim clearly.\n"
    "SCRIPT_BEAT:\nExplain what the supplied evidence actually supports.\n"
    "VISUAL:\nShow the mechanic outcome with simple comparison framing.\n"
    "ON_SCREEN_TEXT:\nWhat the evidence supports\n"
    "DURATION_SECONDS:\n22\n"
    "FINAL_SCENE_COUNT:\n2\n"
    "TOTAL_ESTIMATED_DURATION_SECONDS:\n30"
)

TIMING_REVIEW_RESPONSE = (
    "DECISION:\naccept\n"
    "TOTAL_DURATION_ASSESSMENT:\nThe total duration stays close to target.\n"
    "PACING:\nThe opening moves quickly enough for the hook.\n"
    "SCENE_ISSUES:\nNone.\n"
    "RECOMMENDATIONS:\nKeep scene transitions tight."
)

VISUAL_DIRECTION_RESPONSE = (
    "SCENE_NUMBER:\n2\n"
    "PRIMARY_VISUAL:\nMechanic close-up with clear focal framing.\n"
    "COMPOSITION:\nCenter-weighted framing with space for overlay text.\n"
    "MOTION:\nSmall forward push toward the mechanic.\n"
    "ON_SCREEN_TEXT:\nWhat really happens\n"
    "STYLE_NOTES:\nKeep the look crisp and readable.\n"
    "AVOID:\nOvercrowded HUD clutter."
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
    """Injected fake OpenAI client for provider-independent storyboard tests."""

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
    text: str = SCENE_BREAKDOWN_RESPONSE,
    model: str = DEFAULT_OPENAI_MODEL,
) -> Response:
    """Create a deterministic fake SDK response for the OpenAI storyboard-agent test."""

    response = Response.model_construct(
        id="resp_openai_storyboard",
        created_at=0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        model=model,
        object="response",
        output=[
            ResponseOutputMessage.model_construct(
                id="msg_openai_storyboard",
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
    response._request_id = "req_openai_storyboard"
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


def test_storyboard_agent_accepts_llm_execution_service() -> None:
    """The storyboard agent should accept a real LLMExecutionService dependency."""

    agent = GamingStoryboardAgent(build_mock_service(response_text=SCENE_BREAKDOWN_RESPONSE))

    assert isinstance(agent.llm_execution_service, LLMExecutionService)


def test_storyboard_agent_requires_valid_service_dependency() -> None:
    """Invalid dependencies should be rejected safely."""

    with pytest.raises(CreatorOSValidationError, match="llm_execution_service must be an LLMExecutionService"):
        GamingStoryboardAgent(object())  # type: ignore[arg-type]


def test_scene_breakdown_request_normalizes_strings() -> None:
    """Scene-breakdown inputs should trim surrounding whitespace."""

    request = GamingStoryboardSceneBreakdownRequest(
        title="  Minecraft Myth Test  ",
        game="  Minecraft  ",
        platform="  youtube_shorts  ",
        hook="  Hook  ",
        body="  Body  ",
        ending="  Ending  ",
        call_to_action="  CTA  ",
        target_duration_seconds=30,
    )

    assert request.title == "Minecraft Myth Test"
    assert request.game == "Minecraft"
    assert request.platform == "youtube_shorts"
    assert request.hook == "Hook"
    assert request.body == "Body"
    assert request.ending == "Ending"
    assert request.call_to_action == "CTA"


def test_storyboard_requests_reject_blank_required_fields() -> None:
    """Storyboard request models should reject blank required strings."""

    with pytest.raises(ValueError, match="title must not be blank"):
        GamingStoryboardTimingReviewRequest(
            title="   ",
            scene_summary="Scene summary.",
            target_duration_seconds=30,
            platform="youtube_shorts",
        )


def test_storyboard_requests_enforce_positive_numeric_constraints() -> None:
    """Positive numeric fields should be enforced across storyboard requests."""

    with pytest.raises(ValueError):
        GamingStoryboardVisualDirectionRequest(
            game="Minecraft",
            scene_number=0,
            scene_purpose="Open with the hook.",
            script_beat="Introduce the overlooked mechanic.",
            visual_summary="Gameplay footage with concise overlays.",
            platform="youtube_shorts",
            duration_seconds=8.0,
        )

    with pytest.raises(ValueError):
        GamingStoryboardVisualDirectionRequest(
            game="Minecraft",
            scene_number=1,
            scene_purpose="Open with the hook.",
            script_beat="Introduce the overlooked mechanic.",
            visual_summary="Gameplay footage with concise overlays.",
            platform="youtube_shorts",
            duration_seconds=0.0,
        )


def test_from_script_factory_builds_scene_breakdown_request() -> None:
    """A typed script output should map cleanly into a storyboard scene-breakdown request."""

    script_output = YouTubeShortsScriptOutput(
        title="Minecraft Myth Test",
        hook="You probably still believe this Minecraft myth.",
        body="Players keep repeating this mechanic claim.",
        ending="Test the mechanic yourself.",
        call_to_action="Which Minecraft myth should we check next?",
        estimated_duration_seconds=30,
        evidence_note="Supplied evidence only.",
    )

    request = GamingStoryboardSceneBreakdownRequest.from_script(
        script_output,
        game="Minecraft",
        platform="youtube_shorts",
    )

    assert request.title == "Minecraft Myth Test"
    assert request.hook == "You probably still believe this Minecraft myth."
    assert request.target_duration_seconds == 30


def test_break_down_scenes_uses_expected_prompt_and_variables() -> None:
    """Scene breakdown should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        StoryboardSceneBreakdownOutput.model_validate(
            {
                "storyboard_title": "Minecraft Myth Test",
                "scenes": [
                    {
                        "scene_number": 1,
                        "purpose": "Open with the hook.",
                        "script_beat": "You probably still believe this Minecraft myth.",
                        "visual": "Close-up gameplay view of the mechanic in action.",
                        "on_screen_text": "Minecraft myth?",
                        "duration_seconds": 8.0,
                    },
                    {
                        "scene_number": 2,
                        "purpose": "Resolve the claim clearly.",
                        "script_beat": "Explain what the supplied evidence actually supports.",
                        "visual": "Show the mechanic outcome with simple comparison framing.",
                        "on_screen_text": "What the evidence supports",
                        "duration_seconds": 22.0,
                    },
                ],
                "final_scene_count": 2,
                "total_estimated_duration_seconds": 30.0,
            }
        )
    )
    agent = GamingStoryboardAgent(spy_service)
    request = GamingStoryboardSceneBreakdownRequest(
        title="Minecraft Myth Test",
        game="Minecraft",
        platform="youtube_shorts",
        hook="You probably still believe this Minecraft myth.",
        body="Players keep repeating this mechanic claim.",
        ending="Test the mechanic yourself.",
        call_to_action="Which Minecraft myth should we check next?",
        target_duration_seconds=30,
    )

    result = run_async(agent.break_down_scenes(request))

    recorded_request = spy_service.calls[0]
    assert result.storyboard_title == "Minecraft Myth Test"
    assert tuple(scene.scene_number for scene in result.scenes) == (1, 2)
    assert tuple(scene.duration_seconds for scene in result.scenes) == (8.0, 22.0)
    assert recorded_request.prompt_name == STORYBOARD_SCENE_BREAKDOWN
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "game": "Minecraft",
        "platform": "youtube_shorts",
        "hook": "You probably still believe this Minecraft myth.",
        "body": "Players keep repeating this mechanic claim.",
        "ending": "Test the mechanic yourself.",
        "call_to_action": "Which Minecraft myth should we check next?",
        "target_duration_seconds": 30,
    }
    assert request.model_dump() == GamingStoryboardSceneBreakdownRequest(
        title="Minecraft Myth Test",
        game="Minecraft",
        platform="youtube_shorts",
        hook="You probably still believe this Minecraft myth.",
        body="Players keep repeating this mechanic claim.",
        ending="Test the mechanic yourself.",
        call_to_action="Which Minecraft myth should we check next?",
        target_duration_seconds=30,
    ).model_dump()


def test_review_timing_uses_expected_prompt_and_variables() -> None:
    """Timing review should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        StoryboardTimingReviewOutput(
            decision="accept",
            total_duration_assessment="The total duration stays close to target.",
            pacing="The opening moves quickly enough for the hook.",
            scene_issues="None.",
            recommendations="Keep scene transitions tight.",
        )
    )
    agent = GamingStoryboardAgent(spy_service)

    result = run_async(
        agent.review_timing(
            GamingStoryboardTimingReviewRequest(
                title="Minecraft Myth Test",
                scene_summary="Scene 1: 8 seconds. Scene 2: 22 seconds.",
                target_duration_seconds=30,
                platform="youtube_shorts",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.decision == "accept"
    assert recorded_request.prompt_name == STORYBOARD_TIMING_REVIEW
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "scene_summary": "Scene 1: 8 seconds. Scene 2: 22 seconds.",
        "target_duration_seconds": 30,
        "platform": "youtube_shorts",
    }


def test_generate_visual_direction_uses_expected_prompt_and_variables() -> None:
    """Visual direction should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        StoryboardVisualDirectionOutput(
            scene_number=2,
            primary_visual="Mechanic close-up with clear focal framing.",
            composition="Center-weighted framing with space for overlay text.",
            motion="Small forward push toward the mechanic.",
            on_screen_text="What really happens",
            style_notes="Keep the look crisp and readable.",
            avoid="Overcrowded HUD clutter.",
        )
    )
    agent = GamingStoryboardAgent(spy_service)

    result = run_async(
        agent.generate_visual_direction(
            GamingStoryboardVisualDirectionRequest(
                game="Minecraft",
                scene_number=2,
                scene_purpose="Resolve the claim clearly.",
                script_beat="Explain what the supplied evidence actually supports.",
                visual_summary="Show the mechanic outcome with simple comparison framing.",
                platform="youtube_shorts",
                duration_seconds=22.0,
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.scene_number == 2
    assert recorded_request.prompt_name == STORYBOARD_VISUAL_DIRECTION
    assert recorded_request.variables == {
        "game": "Minecraft",
        "scene_number": 2,
        "scene_purpose": "Resolve the claim clearly.",
        "script_beat": "Explain what the supplied evidence actually supports.",
        "visual_summary": "Show the mechanic outcome with simple comparison framing.",
        "platform": "youtube_shorts",
        "duration_seconds": 22.0,
    }


def test_storyboard_agent_reuses_application_boundary_execution_options() -> None:
    """Provider-neutral execution overrides should reuse the shared application-level model."""

    spy_service = SpyExecutionService(
        StoryboardTimingReviewOutput(
            decision="accept",
            total_duration_assessment="The total duration stays close to target.",
            pacing="The opening moves quickly enough for the hook.",
            scene_issues="None.",
            recommendations="Keep scene transitions tight.",
        )
    )
    agent = GamingStoryboardAgent(spy_service)

    run_async(
        agent.review_timing(
            GamingStoryboardTimingReviewRequest(
                title="Minecraft Myth Test",
                scene_summary="Scene 1: 8 seconds. Scene 2: 22 seconds.",
                target_duration_seconds=30,
                platform="youtube_shorts",
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


def test_unexpected_scene_breakdown_output_type_is_rejected_safely() -> None:
    """The storyboard agent should fail safely if scene breakdown returns the wrong typed model."""

    spy_service = SpyExecutionService(
        StoryboardTimingReviewOutput(
            decision="accept",
            total_duration_assessment="The total duration stays close to target.",
            pacing="The opening moves quickly enough for the hook.",
            scene_issues="None.",
            recommendations="Keep scene transitions tight.",
        )
    )
    agent = GamingStoryboardAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.break_down_scenes(
                GamingStoryboardSceneBreakdownRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    platform="youtube_shorts",
                    hook="Hook",
                    body="Body",
                    ending="Ending",
                    call_to_action="CTA",
                    target_duration_seconds=30,
                )
            )
        )


def test_unexpected_timing_output_type_is_rejected_safely() -> None:
    """The storyboard agent should fail safely if timing review returns the wrong typed model."""

    spy_service = SpyExecutionService(
        StoryboardVisualDirectionOutput(
            scene_number=2,
            primary_visual="Mechanic close-up with clear focal framing.",
            composition="Center-weighted framing with space for overlay text.",
            motion="Small forward push toward the mechanic.",
            on_screen_text="What really happens",
            style_notes="Keep the look crisp and readable.",
            avoid="Overcrowded HUD clutter.",
        )
    )
    agent = GamingStoryboardAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.review_timing(
                GamingStoryboardTimingReviewRequest(
                    title="Minecraft Myth Test",
                    scene_summary="Scene summary.",
                    target_duration_seconds=30,
                    platform="youtube_shorts",
                )
            )
        )


def test_unexpected_visual_direction_output_type_is_rejected_safely() -> None:
    """The storyboard agent should fail safely if visual direction returns the wrong typed model."""

    spy_service = SpyExecutionService(
        StoryboardSceneBreakdownOutput.model_validate(
            {
                "storyboard_title": "Minecraft Myth Test",
                "scenes": [
                    {
                        "scene_number": 1,
                        "purpose": "Open with the hook.",
                        "script_beat": "Beat one.",
                        "visual": "Visual one.",
                        "on_screen_text": "Text one.",
                        "duration_seconds": 10.0,
                    }
                ],
                "final_scene_count": 1,
                "total_estimated_duration_seconds": 10.0,
            }
        )
    )
    agent = GamingStoryboardAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_visual_direction(
                GamingStoryboardVisualDirectionRequest(
                    game="Minecraft",
                    scene_number=1,
                    scene_purpose="Open with the hook.",
                    script_beat="Beat one.",
                    visual_summary="Visual one.",
                    platform="youtube_shorts",
                    duration_seconds=10.0,
                )
            )
        )


def test_break_down_scenes_completes_fully_with_mock() -> None:
    """Scene breakdown should execute end-to-end through the real service path with the mock provider."""

    agent = GamingStoryboardAgent(build_mock_service(response_text=SCENE_BREAKDOWN_RESPONSE))

    result = run_async(
        agent.break_down_scenes(
            GamingStoryboardSceneBreakdownRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                platform="youtube_shorts",
                hook="You probably still believe this Minecraft myth.",
                body="Players keep repeating this mechanic claim.",
                ending="Test the mechanic yourself.",
                call_to_action="Which Minecraft myth should we check next?",
                target_duration_seconds=30,
            )
        )
    )

    assert isinstance(result, StoryboardSceneBreakdownOutput)
    assert result.final_scene_count == 2


def test_review_timing_completes_fully_with_mock() -> None:
    """Timing review should execute end-to-end through the real service path with the mock provider."""

    agent = GamingStoryboardAgent(build_mock_service(response_text=TIMING_REVIEW_RESPONSE))

    result = run_async(
        agent.review_timing(
            GamingStoryboardTimingReviewRequest(
                title="Minecraft Myth Test",
                scene_summary="Scene 1: 8 seconds. Scene 2: 22 seconds.",
                target_duration_seconds=30,
                platform="youtube_shorts",
            )
        )
    )

    assert isinstance(result, StoryboardTimingReviewOutput)
    assert result.decision == "accept"


def test_generate_visual_direction_completes_fully_with_mock() -> None:
    """Visual direction should execute end-to-end through the real service path with the mock provider."""

    agent = GamingStoryboardAgent(build_mock_service(response_text=VISUAL_DIRECTION_RESPONSE))

    result = run_async(
        agent.generate_visual_direction(
            GamingStoryboardVisualDirectionRequest(
                game="Minecraft",
                scene_number=2,
                scene_purpose="Resolve the claim clearly.",
                script_beat="Explain what the supplied evidence actually supports.",
                visual_summary="Show the mechanic outcome with simple comparison framing.",
                platform="youtube_shorts",
                duration_seconds=22.0,
            )
        )
    )

    assert isinstance(result, StoryboardVisualDirectionOutput)
    assert result.primary_visual == "Mechanic close-up with clear focal framing."


def test_storyboard_agent_supports_fake_openai_through_real_service_path() -> None:
    """The storyboard agent should work unchanged with the fake OpenAI provider path."""

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
    agent = GamingStoryboardAgent(service)

    result = run_async(
        agent.break_down_scenes(
            GamingStoryboardSceneBreakdownRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                platform="youtube_shorts",
                hook="You probably still believe this Minecraft myth.",
                body="Players keep repeating this mechanic claim.",
                ending="Test the mechanic yourself.",
                call_to_action="Which Minecraft myth should we check next?",
                target_duration_seconds=30,
            ),
            execution_options=ResearchExecutionOptions(
                provider_name="openai",
                model=DEFAULT_OPENAI_MODEL,
            ),
        )
    )

    assert isinstance(result, StoryboardSceneBreakdownOutput)
    assert result.storyboard_title == "Minecraft Myth Test"
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
    agent = GamingStoryboardAgent(service)

    with pytest.raises(ProviderAuthenticationError, match="safe provider failure"):
        run_async(
            agent.break_down_scenes(
                GamingStoryboardSceneBreakdownRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    platform="youtube_shorts",
                    hook="Hook",
                    body="Body",
                    ending="Ending",
                    call_to_action="CTA",
                    target_duration_seconds=30,
                )
            )
        )


def test_storyboard_agent_module_avoids_direct_provider_parser_and_prompt_path_coupling() -> None:
    """The storyboard agent module should depend on the execution service boundary, not lower-level internals."""

    module_source = Path("creatoros/agents/storyboard.py").read_text(encoding="utf-8")

    assert "openai" not in module_source.casefold()
    assert "OpenAILLMProvider" not in module_source
    assert "ParserRegistry" not in module_source
    assert "parse_storyboard_scene_breakdown" not in module_source
    assert "parse_storyboard_timing_review" not in module_source
    assert "parse_storyboard_visual_direction" not in module_source
    assert "PromptRegistry" not in module_source
    assert "PromptRenderer" not in module_source
    assert "provider.generate" not in module_source
    assert "prompts/" not in module_source
    assert "WorkflowRuntime" not in module_source
    assert "Publishing" not in module_source
    assert "sqlalchemy" not in module_source.casefold()
    assert "retry" not in module_source.casefold()
