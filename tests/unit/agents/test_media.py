"""Unit tests for the provider-independent gaming media-planning agent."""

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
    GamingMediaAgent,
    GamingNarrationDirectionRequest,
    GamingSceneMotionPromptRequest,
    GamingSceneVisualPromptRequest,
    GamingThumbnailConceptRequest,
    ResearchExecutionOptions,
)
from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderAuthenticationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingNarrationDirectionOutput,
    GamingSceneMotionOutput,
    GamingSceneVisualOutput,
    GamingThumbnailConceptOutput,
    StoryboardScenePlan,
    StoryboardVisualDirectionOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.prompts import (
    GAMING_NARRATION_DIRECTION,
    GAMING_SCENE_MOTION_PROMPT,
    GAMING_SCENE_VISUAL_PROMPT,
    GAMING_THUMBNAIL_CONCEPT,
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

THUMBNAIL_RESPONSE = (
    "CONCEPT:\nShow the hidden mechanic clearly.\n"
    "FOCAL_SUBJECT:\nThe mechanism in the center of the frame.\n"
    "BACKGROUND:\nBlurred in-game environment behind the mechanic.\n"
    "COMPOSITION:\nLarge focal subject with short top-text space.\n"
    "EXPRESSION_OR_ACTION:\nA clear activation moment.\n"
    "ON_IMAGE_TEXT:\nHidden?\n"
    "STYLE_DIRECTION:\nBold contrast with clean readability.\n"
    "AVOID:\nClutter and unsupported extra elements.\n"
    "EVIDENCE_NOTE:\nBased on the supplied mechanic discussion only."
)

SCENE_VISUAL_RESPONSE = (
    "SCENE_NUMBER:\n1\n"
    "SUBJECT:\nA player-facing view of the mechanic.\n"
    "ENVIRONMENT:\nThe relevant in-game area.\n"
    "ACTION:\nThe mechanic activates visibly.\n"
    "COMPOSITION:\nTight framing around the mechanic.\n"
    "MOOD:\nCurious and focused.\n"
    "ON_SCREEN_TEXT:\nDoes this still work?\n"
    "STYLE_DIRECTION:\nReadable, crisp, and grounded.\n"
    "NEGATIVE_GUIDANCE:\nNo unsupported characters or logos."
)

SCENE_MOTION_RESPONSE = (
    "SCENE_NUMBER:\n2\n"
    "PRIMARY_MOTION:\nA short push toward the mechanic.\n"
    "SUBJECT_MOVEMENT:\nThe mechanism toggles once.\n"
    "CAMERA_DIRECTION:\nSlow forward move.\n"
    "TRANSITION_GUIDANCE:\nCut in quickly from the prior scene.\n"
    "PACING:\nFast but readable.\n"
    "DURATION_SECONDS:\n4.5\n"
    "AVOID:\nOverly complex motion paths."
)

NARRATION_RESPONSE = (
    "NARRATION_TEXT:\nYou probably still believe this myth.\n"
    "TONE:\nCalm and curious.\n"
    "PACE:\nBrisk but clear.\n"
    "EMPHASIS:\nStress the claim and the correction.\n"
    "PAUSE_GUIDANCE:\nPause briefly before the resolution line.\n"
    "PRONUNCIATION_NOTES:\nSay the game term carefully.\n"
    "TARGET_DURATION_SECONDS:\n30"
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
    """Injected fake OpenAI client for provider-independent media-agent tests."""

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
    text: str = THUMBNAIL_RESPONSE,
    model: str = DEFAULT_OPENAI_MODEL,
) -> Response:
    """Create a deterministic fake SDK response for the OpenAI media-agent test."""

    response = Response.model_construct(
        id="resp_openai_media",
        created_at=0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        model=model,
        object="response",
        output=[
            ResponseOutputMessage.model_construct(
                id="msg_openai_media",
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
    response._request_id = "req_openai_media"
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


def build_storyboard_scene_plan() -> StoryboardScenePlan:
    """Create one reusable typed storyboard scene plan."""

    return StoryboardScenePlan(
        scene_number=2,
        purpose="Resolve the claim clearly.",
        script_beat="Explain what the supplied evidence actually supports.",
        visual="Show the mechanic outcome with simple comparison framing.",
        on_screen_text="What the evidence supports",
        duration_seconds=22.0,
    )


def build_storyboard_visual_direction() -> StoryboardVisualDirectionOutput:
    """Create one reusable typed storyboard visual-direction output."""

    return StoryboardVisualDirectionOutput(
        scene_number=2,
        primary_visual="Mechanic close-up with clear focal framing.",
        composition="Center-weighted framing with space for overlay text.",
        motion="Small forward push toward the mechanic.",
        on_screen_text="What really happens",
        style_notes="Keep the look crisp and readable.",
        avoid="Overcrowded HUD clutter.",
    )


def build_script_output() -> YouTubeShortsScriptOutput:
    """Create one reusable typed script output."""

    return YouTubeShortsScriptOutput(
        title="Minecraft Myth Test",
        hook="You probably still believe this Minecraft myth.",
        body="Players keep repeating this mechanic claim.",
        ending="Test the mechanic yourself.",
        call_to_action="Which Minecraft myth should we check next?",
        estimated_duration_seconds=30,
        evidence_note="Supplied evidence only.",
    )


def test_media_agent_accepts_llm_execution_service() -> None:
    """The media agent should accept a real LLMExecutionService dependency."""

    agent = GamingMediaAgent(build_mock_service(response_text=THUMBNAIL_RESPONSE))

    assert isinstance(agent.llm_execution_service, LLMExecutionService)


def test_media_agent_requires_valid_service_dependency() -> None:
    """Invalid dependencies should be rejected safely."""

    with pytest.raises(CreatorOSValidationError, match="llm_execution_service must be an LLMExecutionService"):
        GamingMediaAgent(object())  # type: ignore[arg-type]


def test_thumbnail_request_normalizes_strings() -> None:
    """Thumbnail-planning inputs should trim surrounding whitespace."""

    request = GamingThumbnailConceptRequest(
        title="  Minecraft Myth Test  ",
        game="  Minecraft  ",
        topic="  gaming myths  ",
        angle="  test one mechanic claim  ",
        hook="  Hook line  ",
        platform="  youtube_shorts  ",
        visual_context="  crisp gameplay framing  ",
    )

    assert request.title == "Minecraft Myth Test"
    assert request.game == "Minecraft"
    assert request.topic == "gaming myths"
    assert request.angle == "test one mechanic claim"
    assert request.hook == "Hook line"
    assert request.platform == "youtube_shorts"
    assert request.visual_context == "crisp gameplay framing"


def test_media_requests_reject_blank_required_fields() -> None:
    """Media request models should reject blank required strings."""

    with pytest.raises(ValueError, match="script_text must not be blank"):
        GamingNarrationDirectionRequest(
            title="Minecraft Myth Test",
            game="Minecraft",
            script_text="   ",
            target_duration_seconds=30,
            tone="natural",
            platform="youtube_shorts",
        )


def test_media_requests_enforce_positive_numeric_constraints() -> None:
    """Positive numeric fields should be enforced across media requests."""

    with pytest.raises(ValueError):
        GamingSceneMotionPromptRequest(
            game="Minecraft",
            scene_number=0,
            scene_purpose="Resolve the claim clearly.",
            visual_summary="Show the mechanic outcome with simple comparison framing.",
            script_beat="Explain what the supplied evidence actually supports.",
            duration_seconds=22.0,
            platform="youtube_shorts",
        )

    with pytest.raises(ValueError):
        GamingNarrationDirectionRequest(
            title="Minecraft Myth Test",
            game="Minecraft",
            script_text="Narration text.",
            target_duration_seconds=0,
            tone="natural",
            platform="youtube_shorts",
        )


def test_scene_visual_request_from_storyboard_outputs_builds_cleanly() -> None:
    """Typed storyboard outputs should map cleanly into a scene-visual request."""

    scene_plan = build_storyboard_scene_plan()
    visual_direction = build_storyboard_visual_direction()

    request = GamingSceneVisualPromptRequest.from_storyboard_outputs(
        scene_plan,
        visual_direction,
        game="Minecraft",
        platform="youtube_shorts",
    )

    assert request.game == "Minecraft"
    assert request.scene_number == 2
    assert request.scene_purpose == "Resolve the claim clearly."
    assert request.on_screen_text == "What really happens"
    assert "Primary visual: Mechanic close-up with clear focal framing." in request.visual_direction
    assert scene_plan.visual == "Show the mechanic outcome with simple comparison framing."
    assert visual_direction.primary_visual == "Mechanic close-up with clear focal framing."


def test_scene_motion_request_from_storyboard_scene_builds_cleanly() -> None:
    """Typed storyboard scene plans should map cleanly into a scene-motion request."""

    scene_plan = build_storyboard_scene_plan()

    request = GamingSceneMotionPromptRequest.from_storyboard_scene(
        scene_plan,
        game="Minecraft",
        platform="youtube_shorts",
    )

    assert request.game == "Minecraft"
    assert request.scene_number == 2
    assert request.visual_summary == "Show the mechanic outcome with simple comparison framing."
    assert request.duration_seconds == 22.0
    assert scene_plan.duration_seconds == 22.0


def test_narration_request_from_script_builds_cleanly() -> None:
    """Typed script output should map cleanly into a narration-direction request."""

    script_output = build_script_output()

    request = GamingNarrationDirectionRequest.from_script(
        script_output,
        game="Minecraft",
        tone="natural and concise",
        platform="youtube_shorts",
    )

    assert request.title == "Minecraft Myth Test"
    assert request.target_duration_seconds == 30
    assert "You probably still believe this Minecraft myth." in request.script_text
    assert "Which Minecraft myth should we check next?" in request.script_text
    assert script_output.call_to_action == "Which Minecraft myth should we check next?"


def test_generate_thumbnail_concept_uses_expected_prompt_and_variables() -> None:
    """Thumbnail planning should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingThumbnailConceptOutput(
            concept="Show the hidden mechanic clearly.",
            focal_subject="The mechanism in the center of the frame.",
            background="Blurred in-game environment behind the mechanic.",
            composition="Large focal subject with short top-text space.",
            expression_or_action="A clear activation moment.",
            on_image_text="Hidden?",
            style_direction="Bold contrast with clean readability.",
            avoid="Clutter and unsupported extra elements.",
            evidence_note="Based on the supplied mechanic discussion only.",
        )
    )
    agent = GamingMediaAgent(spy_service)
    request = GamingThumbnailConceptRequest(
        title="Minecraft Myth Test",
        game="Minecraft",
        topic="gaming myths",
        angle="test one mechanic claim",
        hook="You probably still believe this Minecraft myth.",
        platform="youtube_shorts",
        visual_context="Clean gameplay-inspired context with one clear focal subject.",
    )

    result = run_async(agent.generate_thumbnail_concept(request))

    recorded_request = spy_service.calls[0]
    assert result.on_image_text == "Hidden?"
    assert recorded_request.prompt_name == GAMING_THUMBNAIL_CONCEPT
    assert recorded_request.provider_name is None
    assert recorded_request.model is None
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "game": "Minecraft",
        "topic": "gaming myths",
        "angle": "test one mechanic claim",
        "hook": "You probably still believe this Minecraft myth.",
        "platform": "youtube_shorts",
        "visual_context": "Clean gameplay-inspired context with one clear focal subject.",
    }
    assert request.model_dump() == GamingThumbnailConceptRequest(
        title="Minecraft Myth Test",
        game="Minecraft",
        topic="gaming myths",
        angle="test one mechanic claim",
        hook="You probably still believe this Minecraft myth.",
        platform="youtube_shorts",
        visual_context="Clean gameplay-inspired context with one clear focal subject.",
    ).model_dump()


def test_generate_scene_visual_uses_expected_prompt_and_variables() -> None:
    """Scene-visual planning should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingSceneVisualOutput(
            scene_number=1,
            subject="A player-facing view of the mechanic.",
            environment="The relevant in-game area.",
            action="The mechanic activates visibly.",
            composition="Tight framing around the mechanic.",
            mood="Curious and focused.",
            on_screen_text="Does this still work?",
            style_direction="Readable, crisp, and grounded.",
            negative_guidance="No unsupported characters or logos.",
        )
    )
    agent = GamingMediaAgent(spy_service)

    result = run_async(
        agent.generate_scene_visual(
            GamingSceneVisualPromptRequest(
                game="Minecraft",
                scene_number=1,
                scene_purpose="Open with the hook.",
                script_beat="You probably still believe this Minecraft myth.",
                visual_direction="Primary visual: mechanic close-up. Composition: centered framing.",
                on_screen_text="Does this still work?",
                platform="youtube_shorts",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.scene_number == 1
    assert recorded_request.prompt_name == GAMING_SCENE_VISUAL_PROMPT
    assert recorded_request.variables == {
        "game": "Minecraft",
        "scene_number": 1,
        "scene_purpose": "Open with the hook.",
        "script_beat": "You probably still believe this Minecraft myth.",
        "visual_direction": "Primary visual: mechanic close-up. Composition: centered framing.",
        "on_screen_text": "Does this still work?",
        "platform": "youtube_shorts",
    }


def test_generate_scene_motion_uses_expected_prompt_and_variables() -> None:
    """Scene-motion planning should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingSceneMotionOutput(
            scene_number=2,
            primary_motion="A short push toward the mechanic.",
            subject_movement="The mechanism toggles once.",
            camera_direction="Slow forward move.",
            transition_guidance="Cut in quickly from the prior scene.",
            pacing="Fast but readable.",
            duration_seconds=4.5,
            avoid="Overly complex motion paths.",
        )
    )
    agent = GamingMediaAgent(spy_service)

    result = run_async(
        agent.generate_scene_motion(
            GamingSceneMotionPromptRequest(
                game="Minecraft",
                scene_number=2,
                scene_purpose="Resolve the claim clearly.",
                visual_summary="Show the mechanic outcome with simple comparison framing.",
                script_beat="Explain what the supplied evidence actually supports.",
                duration_seconds=22.0,
                platform="youtube_shorts",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.primary_motion == "A short push toward the mechanic."
    assert recorded_request.prompt_name == GAMING_SCENE_MOTION_PROMPT
    assert recorded_request.variables == {
        "game": "Minecraft",
        "scene_number": 2,
        "scene_purpose": "Resolve the claim clearly.",
        "visual_summary": "Show the mechanic outcome with simple comparison framing.",
        "script_beat": "Explain what the supplied evidence actually supports.",
        "duration_seconds": 22.0,
        "platform": "youtube_shorts",
    }


def test_generate_narration_direction_uses_expected_prompt_and_variables() -> None:
    """Narration planning should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingNarrationDirectionOutput(
            narration_text="You probably still believe this myth.",
            tone="Calm and curious.",
            pace="Brisk but clear.",
            emphasis="Stress the claim and the correction.",
            pause_guidance="Pause briefly before the resolution line.",
            pronunciation_notes="Say the game term carefully.",
            target_duration_seconds=30,
        )
    )
    agent = GamingMediaAgent(spy_service)

    result = run_async(
        agent.generate_narration_direction(
            GamingNarrationDirectionRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="You probably still believe this myth. Here is the correction.",
                target_duration_seconds=30,
                tone="natural and concise",
                platform="youtube_shorts",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.target_duration_seconds == 30
    assert recorded_request.prompt_name == GAMING_NARRATION_DIRECTION
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "game": "Minecraft",
        "script_text": "You probably still believe this myth. Here is the correction.",
        "target_duration_seconds": 30,
        "tone": "natural and concise",
        "platform": "youtube_shorts",
    }


def test_media_agent_reuses_application_boundary_execution_options() -> None:
    """Provider-neutral execution overrides should reuse the shared application-level model."""

    spy_service = SpyExecutionService(
        GamingNarrationDirectionOutput(
            narration_text="You probably still believe this myth.",
            tone="Calm and curious.",
            pace="Brisk but clear.",
            emphasis="Stress the claim and the correction.",
            pause_guidance="Pause briefly before the resolution line.",
            pronunciation_notes="Say the game term carefully.",
            target_duration_seconds=30,
        )
    )
    agent = GamingMediaAgent(spy_service)

    run_async(
        agent.generate_narration_direction(
            GamingNarrationDirectionRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="You probably still believe this myth. Here is the correction.",
                target_duration_seconds=30,
                tone="natural and concise",
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


def test_unexpected_thumbnail_output_type_is_rejected_safely() -> None:
    """Thumbnail planning should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(
        GamingSceneVisualOutput(
            scene_number=1,
            subject="A player-facing view of the mechanic.",
            environment="The relevant in-game area.",
            action="The mechanic activates visibly.",
            composition="Tight framing around the mechanic.",
            mood="Curious and focused.",
            on_screen_text="Does this still work?",
            style_direction="Readable, crisp, and grounded.",
            negative_guidance="No unsupported characters or logos.",
        )
    )
    agent = GamingMediaAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_thumbnail_concept(
                GamingThumbnailConceptRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    topic="gaming myths",
                    angle="test one mechanic claim",
                    hook="Hook",
                    platform="youtube_shorts",
                    visual_context="Visual context.",
                )
            )
        )


def test_unexpected_scene_visual_output_type_is_rejected_safely() -> None:
    """Scene-visual planning should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(
        GamingSceneMotionOutput(
            scene_number=2,
            primary_motion="A short push toward the mechanic.",
            subject_movement="The mechanism toggles once.",
            camera_direction="Slow forward move.",
            transition_guidance="Cut in quickly from the prior scene.",
            pacing="Fast but readable.",
            duration_seconds=4.5,
            avoid="Overly complex motion paths.",
        )
    )
    agent = GamingMediaAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_scene_visual(
                GamingSceneVisualPromptRequest(
                    game="Minecraft",
                    scene_number=1,
                    scene_purpose="Open with the hook.",
                    script_beat="Beat one.",
                    visual_direction="Visual direction.",
                    on_screen_text="Text.",
                    platform="youtube_shorts",
                )
            )
        )


def test_unexpected_scene_motion_output_type_is_rejected_safely() -> None:
    """Scene-motion planning should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(
        GamingNarrationDirectionOutput(
            narration_text="You probably still believe this myth.",
            tone="Calm and curious.",
            pace="Brisk but clear.",
            emphasis="Stress the claim and the correction.",
            pause_guidance="Pause briefly before the resolution line.",
            pronunciation_notes="Say the game term carefully.",
            target_duration_seconds=30,
        )
    )
    agent = GamingMediaAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_scene_motion(
                GamingSceneMotionPromptRequest(
                    game="Minecraft",
                    scene_number=2,
                    scene_purpose="Resolve the claim clearly.",
                    visual_summary="Visual summary.",
                    script_beat="Beat two.",
                    duration_seconds=22.0,
                    platform="youtube_shorts",
                )
            )
        )


def test_unexpected_narration_output_type_is_rejected_safely() -> None:
    """Narration planning should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(
        GamingThumbnailConceptOutput(
            concept="Show the hidden mechanic clearly.",
            focal_subject="The mechanism in the center of the frame.",
            background="Blurred in-game environment behind the mechanic.",
            composition="Large focal subject with short top-text space.",
            expression_or_action="A clear activation moment.",
            on_image_text="Hidden?",
            style_direction="Bold contrast with clean readability.",
            avoid="Clutter and unsupported extra elements.",
            evidence_note="Based on the supplied mechanic discussion only.",
        )
    )
    agent = GamingMediaAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.generate_narration_direction(
                GamingNarrationDirectionRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    script_text="Narration text.",
                    target_duration_seconds=30,
                    tone="natural",
                    platform="youtube_shorts",
                )
            )
        )


def test_generate_thumbnail_concept_completes_fully_with_mock() -> None:
    """Thumbnail planning should execute end-to-end through the real service path with the mock provider."""

    agent = GamingMediaAgent(build_mock_service(response_text=THUMBNAIL_RESPONSE))

    result = run_async(
        agent.generate_thumbnail_concept(
            GamingThumbnailConceptRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                hook="You probably still believe this Minecraft myth.",
                platform="youtube_shorts",
                visual_context="Clean gameplay-inspired context with one clear focal subject.",
            )
        )
    )

    assert isinstance(result, GamingThumbnailConceptOutput)
    assert result.on_image_text == "Hidden?"


def test_generate_scene_visual_completes_fully_with_mock() -> None:
    """Scene-visual planning should execute end-to-end through the real service path with the mock provider."""

    agent = GamingMediaAgent(build_mock_service(response_text=SCENE_VISUAL_RESPONSE))

    result = run_async(
        agent.generate_scene_visual(
            GamingSceneVisualPromptRequest(
                game="Minecraft",
                scene_number=1,
                scene_purpose="Open with the hook.",
                script_beat="You probably still believe this Minecraft myth.",
                visual_direction="Primary visual: mechanic close-up. Composition: centered framing.",
                on_screen_text="Does this still work?",
                platform="youtube_shorts",
            )
        )
    )

    assert isinstance(result, GamingSceneVisualOutput)
    assert result.subject == "A player-facing view of the mechanic."


def test_generate_scene_motion_completes_fully_with_mock() -> None:
    """Scene-motion planning should execute end-to-end through the real service path with the mock provider."""

    agent = GamingMediaAgent(build_mock_service(response_text=SCENE_MOTION_RESPONSE))

    result = run_async(
        agent.generate_scene_motion(
            GamingSceneMotionPromptRequest(
                game="Minecraft",
                scene_number=2,
                scene_purpose="Resolve the claim clearly.",
                visual_summary="Show the mechanic outcome with simple comparison framing.",
                script_beat="Explain what the supplied evidence actually supports.",
                duration_seconds=22.0,
                platform="youtube_shorts",
            )
        )
    )

    assert isinstance(result, GamingSceneMotionOutput)
    assert result.duration_seconds == 4.5


def test_generate_narration_direction_completes_fully_with_mock() -> None:
    """Narration planning should execute end-to-end through the real service path with the mock provider."""

    agent = GamingMediaAgent(build_mock_service(response_text=NARRATION_RESPONSE))

    result = run_async(
        agent.generate_narration_direction(
            GamingNarrationDirectionRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="You probably still believe this myth. Here is the correction.",
                target_duration_seconds=30,
                tone="natural and concise",
                platform="youtube_shorts",
            )
        )
    )

    assert isinstance(result, GamingNarrationDirectionOutput)
    assert result.tone == "Calm and curious."


def test_media_agent_supports_fake_openai_through_real_service_path() -> None:
    """The media agent should work unchanged with the fake OpenAI provider path."""

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
    agent = GamingMediaAgent(service)

    result = run_async(
        agent.generate_thumbnail_concept(
            GamingThumbnailConceptRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                hook="You probably still believe this Minecraft myth.",
                platform="youtube_shorts",
                visual_context="Clean gameplay-inspired context with one clear focal subject.",
            ),
            execution_options=ResearchExecutionOptions(
                provider_name="openai",
                model=DEFAULT_OPENAI_MODEL,
            ),
        )
    )

    assert isinstance(result, GamingThumbnailConceptOutput)
    assert result.on_image_text == "Hidden?"
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
    agent = GamingMediaAgent(service)

    with pytest.raises(ProviderAuthenticationError, match="safe provider failure"):
        run_async(
            agent.generate_thumbnail_concept(
                GamingThumbnailConceptRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    topic="gaming myths",
                    angle="test one mechanic claim",
                    hook="Hook",
                    platform="youtube_shorts",
                    visual_context="Visual context.",
                )
            )
        )


def test_media_agent_module_avoids_direct_provider_parser_prompt_and_media_generation_coupling() -> None:
    """The media agent module should depend on the execution service boundary, not lower-level internals."""

    module_source = Path("creatoros/agents/media.py").read_text(encoding="utf-8")

    assert "openai" not in module_source.casefold()
    assert "OpenAILLMProvider" not in module_source
    assert "ParserRegistry" not in module_source
    assert "PromptRegistry" not in module_source
    assert "PromptRenderer" not in module_source
    assert "parse_gaming_thumbnail_concept" not in module_source
    assert "parse_gaming_scene_visual" not in module_source
    assert "parse_gaming_scene_motion" not in module_source
    assert "parse_gaming_narration_direction" not in module_source
    assert "ImageProvider" not in module_source
    assert "VideoProvider" not in module_source
    assert "VoiceProvider" not in module_source
    assert "generate_image" not in module_source
    assert "generate_video" not in module_source
    assert "generate_voice" not in module_source
    assert "ffmpeg" not in module_source.casefold()
    assert "StorageProvider" not in module_source
    assert "store(" not in module_source
    assert "Publishing" not in module_source
    assert "WorkflowRuntime" not in module_source
    assert "sqlalchemy" not in module_source.casefold()
    assert "retry" not in module_source.casefold()
