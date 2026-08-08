"""Unit tests for the provider-independent gaming review agent."""

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
    GamingEvidenceConsistencyReviewRequest,
    GamingPublicationReadinessReviewRequest,
    GamingReviewAgent,
    GamingScriptQualityReviewRequest,
    GamingStoryboardQualityReviewRequest,
    ResearchExecutionOptions,
)
from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderAuthenticationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingEvidenceConsistencyReviewOutput,
    GamingNarrationDirectionOutput,
    GamingPublicationReadinessReviewOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingThumbnailConceptOutput,
    StoryboardSceneBreakdownOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.prompts import (
    GAMING_EVIDENCE_CONSISTENCY_REVIEW,
    GAMING_PUBLICATION_READINESS_REVIEW,
    GAMING_SCRIPT_QUALITY_REVIEW,
    GAMING_STORYBOARD_QUALITY_REVIEW,
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
from creatoros.workflows import ApprovalDecisionType, WorkflowExecutionStatus

SCRIPT_QUALITY_RESPONSE = (
    "DECISION:\naccept\n"
    "SUMMARY:\nThe script is clear and focused.\n"
    "HOOK_REVIEW:\nThe hook creates immediate curiosity.\n"
    "CLARITY_REVIEW:\nThe lines are easy to follow aloud.\n"
    "STRUCTURE_REVIEW:\nThe script maintains one main idea.\n"
    "FACTUAL_RESTRAINT:\nClaims stay cautious relative to the evidence.\n"
    "PACING_REVIEW:\nThe pacing fits the short target.\n"
    "ENDING_REVIEW:\nThe ending resolves the promise naturally.\n"
    "ISSUES:\nNone.\n"
    "RECOMMENDATIONS:\nKeep the phrasing concise."
)

EVIDENCE_REVIEW_RESPONSE = (
    "DECISION:\nconsistent\n"
    "SUMMARY:\nThe claims align with supplied evidence.\n"
    "SUPPORTED_CLAIMS:\nThe core mechanic claim is supported.\n"
    "UNSUPPORTED_CLAIMS:\nNone.\n"
    "CONTRADICTIONS:\nNone.\n"
    "UNCERTAINTIES:\nMinor uncertainty remains around edge cases.\n"
    "OVERSTATEMENTS:\nNone.\n"
    "RECOMMENDATIONS:\nKeep cautious wording."
)

STORYBOARD_REVIEW_RESPONSE = (
    "DECISION:\nrevise\n"
    "SUMMARY:\nThe storyboard mostly works but needs one fix.\n"
    "SCRIPT_FIDELITY:\nMost scenes match the script.\n"
    "HOOK_SCENE:\nThe opening scene supports the hook.\n"
    "SCENE_SEQUENCE:\nThe order is mostly clear.\n"
    "VISUAL_CLARITY:\nThe visual instructions are readable.\n"
    "PACING:\nThe middle scene runs slightly long.\n"
    "ENDING_SCENE:\nThe final scene supports the ending.\n"
    "UNSUPPORTED_VISUALS:\nOne visual claim needs caution.\n"
    "ISSUES:\nScene two should be tighter.\n"
    "RECOMMENDATIONS:\nTrim the middle scene and simplify one shot."
)

PUBLICATION_REVIEW_RESPONSE = (
    "DECISION:\nready_for_human_review\n"
    "SUMMARY:\nThe artifacts are aligned enough for human review.\n"
    "ARTIFACT_ALIGNMENT:\nTitle, script, and storyboard are aligned.\n"
    "EVIDENCE_STATUS:\nThe evidence review does not show unresolved contradictions.\n"
    "MISSING_OR_INCOMPLETE:\nNone.\n"
    "BLOCKERS:\nNone.\n"
    "NON_BLOCKING_IMPROVEMENTS:\nThumbnail text could be shorter.\n"
    "HUMAN_REVIEW_FOCUS:\nCheck branding tone and final phrasing."
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
    """Injected fake OpenAI client for provider-independent review-agent tests."""

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
    text: str = SCRIPT_QUALITY_RESPONSE,
    model: str = DEFAULT_OPENAI_MODEL,
) -> Response:
    """Create a deterministic fake SDK response for the OpenAI review-agent test."""

    response = Response.model_construct(
        id="resp_openai_review",
        created_at=0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        model=model,
        object="response",
        output=[
            ResponseOutputMessage.model_construct(
                id="msg_openai_review",
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
    response._request_id = "req_openai_review"
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


def build_storyboard_output() -> StoryboardSceneBreakdownOutput:
    """Create one reusable typed storyboard scene-breakdown output."""

    return StoryboardSceneBreakdownOutput.model_validate(
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


def build_thumbnail_output() -> GamingThumbnailConceptOutput:
    """Create one reusable typed thumbnail-concept output."""

    return GamingThumbnailConceptOutput(
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


def build_narration_output() -> GamingNarrationDirectionOutput:
    """Create one reusable typed narration-direction output."""

    return GamingNarrationDirectionOutput(
        narration_text="You probably still believe this myth.",
        tone="Calm and curious.",
        pace="Brisk but clear.",
        emphasis="Stress the claim and the correction.",
        pause_guidance="Pause briefly before the resolution line.",
        pronunciation_notes="Say the game term carefully.",
        target_duration_seconds=30,
    )


def build_evidence_review_output() -> GamingEvidenceConsistencyReviewOutput:
    """Create one reusable typed evidence-consistency review output."""

    return GamingEvidenceConsistencyReviewOutput(
        decision="consistent",
        summary="The claims align with supplied evidence.",
        supported_claims="The core mechanic claim is supported.",
        unsupported_claims="None.",
        contradictions="None.",
        uncertainties="Minor uncertainty remains around edge cases.",
        overstatements="None.",
        recommendations="Keep cautious wording.",
    )


def test_review_agent_accepts_llm_execution_service() -> None:
    """The review agent should accept a real LLMExecutionService dependency."""

    agent = GamingReviewAgent(build_mock_service(response_text=SCRIPT_QUALITY_RESPONSE))

    assert isinstance(agent.llm_execution_service, LLMExecutionService)


def test_review_agent_requires_valid_service_dependency() -> None:
    """Invalid dependencies should be rejected safely."""

    with pytest.raises(CreatorOSValidationError, match="llm_execution_service must be an LLMExecutionService"):
        GamingReviewAgent(object())  # type: ignore[arg-type]


def test_script_quality_request_normalizes_strings() -> None:
    """Review request inputs should trim surrounding whitespace."""

    request = GamingScriptQualityReviewRequest(
        title="  Minecraft Myth Test  ",
        game="  Minecraft  ",
        topic="  gaming myths  ",
        angle="  test one mechanic claim  ",
        source_summary="  supplied summary  ",
        script_text="  hook body ending  ",
        platform="  youtube_shorts  ",
        target_duration_seconds=30,
    )

    assert request.title == "Minecraft Myth Test"
    assert request.game == "Minecraft"
    assert request.topic == "gaming myths"
    assert request.angle == "test one mechanic claim"
    assert request.source_summary == "supplied summary"
    assert request.script_text == "hook body ending"
    assert request.platform == "youtube_shorts"


def test_review_requests_reject_blank_required_fields() -> None:
    """Review request models should reject blank required strings."""

    with pytest.raises(ValueError, match="content_text must not be blank"):
        GamingEvidenceConsistencyReviewRequest(
            game="Minecraft",
            source_summary="Summary.",
            research_notes="Notes.",
            content_text="   ",
            content_stage="script_draft",
        )


def test_review_requests_enforce_positive_numeric_constraints() -> None:
    """Positive numeric fields should be enforced across review requests."""

    with pytest.raises(ValueError):
        GamingStoryboardQualityReviewRequest(
            title="Minecraft Myth Test",
            game="Minecraft",
            script_text="Script text.",
            storyboard_text="Storyboard text.",
            platform="youtube_shorts",
            target_duration_seconds=0,
        )


def test_script_quality_request_from_script_builds_cleanly() -> None:
    """Typed script output should map cleanly into a script-quality review request."""

    script_output = build_script_output()

    request = GamingScriptQualityReviewRequest.from_script(
        script_output,
        game="Minecraft",
        topic="gaming myths",
        angle="test one mechanic claim",
        source_summary="Supplied summary only.",
        platform="youtube_shorts",
    )

    assert request.title == "Minecraft Myth Test"
    assert request.target_duration_seconds == 30
    assert "You probably still believe this Minecraft myth." in request.script_text
    assert "Which Minecraft myth should we check next?" in request.script_text
    assert script_output.call_to_action == "Which Minecraft myth should we check next?"


def test_storyboard_quality_request_from_storyboard_builds_cleanly() -> None:
    """Typed storyboard output should map cleanly into a storyboard-quality review request."""

    storyboard_output = build_storyboard_output()

    request = GamingStoryboardQualityReviewRequest.from_storyboard(
        storyboard_output,
        title="Minecraft Myth Test",
        game="Minecraft",
        script_text="Hook. Body. Ending.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    assert request.title == "Minecraft Myth Test"
    assert "Storyboard title: Minecraft Myth Test." in request.storyboard_text
    assert "Scene 1: Purpose: Open with the hook." in request.storyboard_text
    assert request.target_duration_seconds == 30
    assert storyboard_output.storyboard_title == "Minecraft Myth Test"


def test_publication_readiness_request_from_review_inputs_builds_cleanly() -> None:
    """Typed upstream outputs should map cleanly into a publication-readiness review request."""

    script_output = build_script_output()
    storyboard_output = build_storyboard_output()
    thumbnail_output = build_thumbnail_output()
    narration_output = build_narration_output()
    evidence_output = build_evidence_review_output()

    request = GamingPublicationReadinessReviewRequest.from_review_inputs(
        title="Minecraft Myth Test",
        game="Minecraft",
        script_output=script_output,
        storyboard_output=storyboard_output,
        thumbnail_output=thumbnail_output,
        narration_output=narration_output,
        evidence_review_output=evidence_output,
        platform="youtube_shorts",
    )

    assert request.title == "Minecraft Myth Test"
    assert "You probably still believe this Minecraft myth." in request.script_text
    assert "Storyboard title: Minecraft Myth Test." in request.storyboard_summary
    assert "Concept: Show the hidden mechanic clearly." in request.thumbnail_summary
    assert "Tone: Calm and curious." in request.narration_summary
    assert "Decision: consistent." in request.evidence_review
    assert evidence_output.decision == "consistent"


def test_review_script_quality_uses_expected_prompt_and_variables() -> None:
    """Script-quality review should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingScriptQualityReviewOutput(
            decision="accept",
            summary="The script is clear and focused.",
            hook_review="The hook creates immediate curiosity.",
            clarity_review="The lines are easy to follow aloud.",
            structure_review="The script maintains one main idea.",
            factual_restraint="Claims stay cautious relative to the evidence.",
            pacing_review="The pacing fits the short target.",
            ending_review="The ending resolves the promise naturally.",
            issues="None.",
            recommendations="Keep the phrasing concise.",
        )
    )
    agent = GamingReviewAgent(spy_service)
    request = GamingScriptQualityReviewRequest(
        title="Minecraft Myth Test",
        game="Minecraft",
        topic="gaming myths",
        angle="test one mechanic claim",
        source_summary="Supplied summary only.",
        script_text="Hook. Body. Ending.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    result = run_async(agent.review_script_quality(request))

    recorded_request = spy_service.calls[0]
    assert result.decision == "accept"
    assert recorded_request.prompt_name == GAMING_SCRIPT_QUALITY_REVIEW
    assert recorded_request.provider_name is None
    assert recorded_request.model is None
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "game": "Minecraft",
        "topic": "gaming myths",
        "angle": "test one mechanic claim",
        "source_summary": "Supplied summary only.",
        "script_text": "Hook. Body. Ending.",
        "platform": "youtube_shorts",
        "target_duration_seconds": 30,
    }
    assert request.model_dump() == GamingScriptQualityReviewRequest(
        title="Minecraft Myth Test",
        game="Minecraft",
        topic="gaming myths",
        angle="test one mechanic claim",
        source_summary="Supplied summary only.",
        script_text="Hook. Body. Ending.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    ).model_dump()


def test_review_evidence_consistency_uses_expected_prompt_and_variables() -> None:
    """Evidence-consistency review should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(build_evidence_review_output())
    agent = GamingReviewAgent(spy_service)

    result = run_async(
        agent.review_evidence_consistency(
            GamingEvidenceConsistencyReviewRequest(
                game="Minecraft",
                source_summary="Supplied summary covers one specific gameplay claim.",
                research_notes="Research notes say the claim should be framed cautiously.",
                content_text="This claim is definitely true in every match.",
                content_stage="script_draft",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.decision == "consistent"
    assert recorded_request.prompt_name == GAMING_EVIDENCE_CONSISTENCY_REVIEW
    assert recorded_request.variables == {
        "game": "Minecraft",
        "source_summary": "Supplied summary covers one specific gameplay claim.",
        "research_notes": "Research notes say the claim should be framed cautiously.",
        "content_text": "This claim is definitely true in every match.",
        "content_stage": "script_draft",
    }


def test_review_storyboard_quality_uses_expected_prompt_and_variables() -> None:
    """Storyboard-quality review should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingStoryboardQualityReviewOutput(
            decision="revise",
            summary="The storyboard mostly works but needs one fix.",
            script_fidelity="Most scenes match the script.",
            hook_scene="The opening scene supports the hook.",
            scene_sequence="The order is mostly clear.",
            visual_clarity="The visual instructions are readable.",
            pacing="The middle scene runs slightly long.",
            ending_scene="The final scene supports the ending.",
            unsupported_visuals="One visual claim needs caution.",
            issues="Scene two should be tighter.",
            recommendations="Trim the middle scene and simplify one shot.",
        )
    )
    agent = GamingReviewAgent(spy_service)

    result = run_async(
        agent.review_storyboard_quality(
            GamingStoryboardQualityReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="Hook. Body. Ending.",
                storyboard_text="Scene 1 hooks. Scene 2 explains. Scene 3 closes.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.decision == "revise"
    assert recorded_request.prompt_name == GAMING_STORYBOARD_QUALITY_REVIEW
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "game": "Minecraft",
        "script_text": "Hook. Body. Ending.",
        "storyboard_text": "Scene 1 hooks. Scene 2 explains. Scene 3 closes.",
        "platform": "youtube_shorts",
        "target_duration_seconds": 30,
    }


def test_review_publication_readiness_uses_expected_prompt_and_variables() -> None:
    """Publication-readiness review should call the stable builtin prompt name with exact variables."""

    spy_service = SpyExecutionService(
        GamingPublicationReadinessReviewOutput(
            decision="ready_for_human_review",
            summary="The artifacts are aligned enough for human review.",
            artifact_alignment="Title, script, and storyboard are aligned.",
            evidence_status="The evidence review does not show unresolved contradictions.",
            missing_or_incomplete="None.",
            blockers="None.",
            non_blocking_improvements="Thumbnail text could be shorter.",
            human_review_focus="Check branding tone and final phrasing.",
        )
    )
    agent = GamingReviewAgent(spy_service)

    result = run_async(
        agent.review_publication_readiness(
            GamingPublicationReadinessReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="Hook. Body. Ending.",
                storyboard_summary="Storyboard summary.",
                thumbnail_summary="Thumbnail summary.",
                narration_summary="Narration summary.",
                evidence_review="Evidence review summary.",
                platform="youtube_shorts",
            )
        )
    )

    recorded_request = spy_service.calls[0]
    assert result.decision == "ready_for_human_review"
    assert recorded_request.prompt_name == GAMING_PUBLICATION_READINESS_REVIEW
    assert recorded_request.variables == {
        "title": "Minecraft Myth Test",
        "game": "Minecraft",
        "script_text": "Hook. Body. Ending.",
        "storyboard_summary": "Storyboard summary.",
        "thumbnail_summary": "Thumbnail summary.",
        "narration_summary": "Narration summary.",
        "evidence_review": "Evidence review summary.",
        "platform": "youtube_shorts",
    }


def test_review_agent_reuses_application_boundary_execution_options() -> None:
    """Provider-neutral execution overrides should reuse the shared application-level model."""

    spy_service = SpyExecutionService(
        GamingScriptQualityReviewOutput(
            decision="accept",
            summary="The script is clear and focused.",
            hook_review="The hook creates immediate curiosity.",
            clarity_review="The lines are easy to follow aloud.",
            structure_review="The script maintains one main idea.",
            factual_restraint="Claims stay cautious relative to the evidence.",
            pacing_review="The pacing fits the short target.",
            ending_review="The ending resolves the promise naturally.",
            issues="None.",
            recommendations="Keep the phrasing concise.",
        )
    )
    agent = GamingReviewAgent(spy_service)

    run_async(
        agent.review_script_quality(
            GamingScriptQualityReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                source_summary="Supplied summary only.",
                script_text="Hook. Body. Ending.",
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


def test_unexpected_script_review_output_type_is_rejected_safely() -> None:
    """Script-quality review should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(build_evidence_review_output())
    agent = GamingReviewAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.review_script_quality(
                GamingScriptQualityReviewRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    topic="gaming myths",
                    angle="test one mechanic claim",
                    source_summary="Supplied summary only.",
                    script_text="Hook. Body. Ending.",
                    platform="youtube_shorts",
                    target_duration_seconds=30,
                )
            )
        )


def test_unexpected_evidence_review_output_type_is_rejected_safely() -> None:
    """Evidence-consistency review should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(
        GamingStoryboardQualityReviewOutput(
            decision="revise",
            summary="The storyboard mostly works but needs one fix.",
            script_fidelity="Most scenes match the script.",
            hook_scene="The opening scene supports the hook.",
            scene_sequence="The order is mostly clear.",
            visual_clarity="The visual instructions are readable.",
            pacing="The middle scene runs slightly long.",
            ending_scene="The final scene supports the ending.",
            unsupported_visuals="One visual claim needs caution.",
            issues="Scene two should be tighter.",
            recommendations="Trim the middle scene and simplify one shot.",
        )
    )
    agent = GamingReviewAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.review_evidence_consistency(
                GamingEvidenceConsistencyReviewRequest(
                    game="Minecraft",
                    source_summary="Summary.",
                    research_notes="Notes.",
                    content_text="Content text.",
                    content_stage="script_draft",
                )
            )
        )


def test_unexpected_storyboard_review_output_type_is_rejected_safely() -> None:
    """Storyboard-quality review should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(
        GamingPublicationReadinessReviewOutput(
            decision="ready_for_human_review",
            summary="The artifacts are aligned enough for human review.",
            artifact_alignment="Title, script, and storyboard are aligned.",
            evidence_status="The evidence review does not show unresolved contradictions.",
            missing_or_incomplete="None.",
            blockers="None.",
            non_blocking_improvements="Thumbnail text could be shorter.",
            human_review_focus="Check branding tone and final phrasing.",
        )
    )
    agent = GamingReviewAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.review_storyboard_quality(
                GamingStoryboardQualityReviewRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    script_text="Hook. Body. Ending.",
                    storyboard_text="Storyboard text.",
                    platform="youtube_shorts",
                    target_duration_seconds=30,
                )
            )
        )


def test_unexpected_publication_review_output_type_is_rejected_safely() -> None:
    """Publication-readiness review should fail safely if the wrong typed model is returned."""

    spy_service = SpyExecutionService(
        GamingScriptQualityReviewOutput(
            decision="accept",
            summary="The script is clear and focused.",
            hook_review="The hook creates immediate curiosity.",
            clarity_review="The lines are easy to follow aloud.",
            structure_review="The script maintains one main idea.",
            factual_restraint="Claims stay cautious relative to the evidence.",
            pacing_review="The pacing fits the short target.",
            ending_review="The ending resolves the promise naturally.",
            issues="None.",
            recommendations="Keep the phrasing concise.",
        )
    )
    agent = GamingReviewAgent(spy_service)

    with pytest.raises(CreatorOSValidationError, match="unexpected typed output model"):
        run_async(
            agent.review_publication_readiness(
                GamingPublicationReadinessReviewRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    script_text="Hook. Body. Ending.",
                    storyboard_summary="Storyboard summary.",
                    thumbnail_summary="Thumbnail summary.",
                    narration_summary="Narration summary.",
                    evidence_review="Evidence review summary.",
                    platform="youtube_shorts",
                )
            )
        )


def test_review_script_quality_completes_fully_with_mock() -> None:
    """Script-quality review should execute end-to-end through the real service path with the mock provider."""

    agent = GamingReviewAgent(build_mock_service(response_text=SCRIPT_QUALITY_RESPONSE))

    result = run_async(
        agent.review_script_quality(
            GamingScriptQualityReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                source_summary="Supplied summary only.",
                script_text="Hook. Body. Ending.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    assert isinstance(result, GamingScriptQualityReviewOutput)
    assert result.decision == "accept"


def test_review_evidence_consistency_completes_fully_with_mock() -> None:
    """Evidence-consistency review should execute end-to-end through the real service path with the mock provider."""

    agent = GamingReviewAgent(build_mock_service(response_text=EVIDENCE_REVIEW_RESPONSE))

    result = run_async(
        agent.review_evidence_consistency(
            GamingEvidenceConsistencyReviewRequest(
                game="Minecraft",
                source_summary="Summary.",
                research_notes="Notes.",
                content_text="Content text.",
                content_stage="script_draft",
            )
        )
    )

    assert isinstance(result, GamingEvidenceConsistencyReviewOutput)
    assert result.decision == "consistent"


def test_review_storyboard_quality_completes_fully_with_mock() -> None:
    """Storyboard-quality review should execute end-to-end through the real service path with the mock provider."""

    agent = GamingReviewAgent(build_mock_service(response_text=STORYBOARD_REVIEW_RESPONSE))

    result = run_async(
        agent.review_storyboard_quality(
            GamingStoryboardQualityReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="Hook. Body. Ending.",
                storyboard_text="Storyboard text.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    assert isinstance(result, GamingStoryboardQualityReviewOutput)
    assert result.decision == "revise"


def test_review_publication_readiness_completes_fully_with_mock() -> None:
    """Publication-readiness review should execute end-to-end through the real service path with the mock provider."""

    agent = GamingReviewAgent(build_mock_service(response_text=PUBLICATION_REVIEW_RESPONSE))

    result = run_async(
        agent.review_publication_readiness(
            GamingPublicationReadinessReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="Hook. Body. Ending.",
                storyboard_summary="Storyboard summary.",
                thumbnail_summary="Thumbnail summary.",
                narration_summary="Narration summary.",
                evidence_review="Evidence review summary.",
                platform="youtube_shorts",
            )
        )
    )

    assert isinstance(result, GamingPublicationReadinessReviewOutput)
    assert result.decision == "ready_for_human_review"


def test_review_agent_supports_fake_openai_through_real_service_path() -> None:
    """The review agent should work unchanged with the fake OpenAI provider path."""

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
    agent = GamingReviewAgent(service)

    result = run_async(
        agent.review_script_quality(
            GamingScriptQualityReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                source_summary="Supplied summary only.",
                script_text="Hook. Body. Ending.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            ),
            execution_options=ResearchExecutionOptions(
                provider_name="openai",
                model=DEFAULT_OPENAI_MODEL,
            ),
        )
    )

    assert isinstance(result, GamingScriptQualityReviewOutput)
    assert result.decision == "accept"
    assert fake_responses.calls[0]["model"] == DEFAULT_OPENAI_MODEL


def test_positive_readiness_result_does_not_approve_workflow() -> None:
    """A positive review result must stay separate from workflow approval."""

    agent = GamingReviewAgent(build_mock_service(response_text=PUBLICATION_REVIEW_RESPONSE))

    result = run_async(
        agent.review_publication_readiness(
            GamingPublicationReadinessReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="Hook. Body. Ending.",
                storyboard_summary="Storyboard summary.",
                thumbnail_summary="Thumbnail summary.",
                narration_summary="Narration summary.",
                evidence_review="Evidence review summary.",
                platform="youtube_shorts",
            )
        )
    )

    assert result.decision == "ready_for_human_review"
    assert result.decision != ApprovalDecisionType.APPROVED.value
    assert result.decision != ApprovalDecisionType.REJECTED.value
    assert result.decision != WorkflowExecutionStatus.COMPLETED.value
    assert not hasattr(result, "approval_request")
    assert not hasattr(result, "published_post")


def test_negative_review_result_does_not_automatically_regenerate_content() -> None:
    """A revise result must be returned as advice only, without automatic revision."""

    agent = GamingReviewAgent(build_mock_service(response_text=STORYBOARD_REVIEW_RESPONSE))

    result = run_async(
        agent.review_storyboard_quality(
            GamingStoryboardQualityReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                script_text="Hook. Body. Ending.",
                storyboard_text="Storyboard text.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    assert result.decision == "revise"
    assert not hasattr(result, "regenerated_script")
    assert not hasattr(result, "regenerated_storyboard")


def test_review_methods_return_only_typed_review_results() -> None:
    """Review operations should return typed review outputs only."""

    agent = GamingReviewAgent(build_mock_service(response_text=SCRIPT_QUALITY_RESPONSE))

    result = run_async(
        agent.review_script_quality(
            GamingScriptQualityReviewRequest(
                title="Minecraft Myth Test",
                game="Minecraft",
                topic="gaming myths",
                angle="test one mechanic claim",
                source_summary="Supplied summary only.",
                script_text="Hook. Body. Ending.",
                platform="youtube_shorts",
                target_duration_seconds=30,
            )
        )
    )

    assert isinstance(result, GamingScriptQualityReviewOutput)
    assert not hasattr(result, "execution")
    assert not hasattr(result, "workflow_state")


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
    agent = GamingReviewAgent(service)

    with pytest.raises(ProviderAuthenticationError, match="safe provider failure"):
        run_async(
            agent.review_script_quality(
                GamingScriptQualityReviewRequest(
                    title="Minecraft Myth Test",
                    game="Minecraft",
                    topic="gaming myths",
                    angle="test one mechanic claim",
                    source_summary="Supplied summary only.",
                    script_text="Hook. Body. Ending.",
                    platform="youtube_shorts",
                    target_duration_seconds=30,
                )
            )
        )


def test_review_agent_module_avoids_direct_provider_parser_prompt_workflow_and_publishing_coupling() -> None:
    """The review agent module should depend on the execution service boundary, not lower-level internals."""

    module_source = Path("creatoros/agents/review.py").read_text(encoding="utf-8")

    assert "openai" not in module_source.casefold()
    assert "OpenAILLMProvider" not in module_source
    assert "ParserRegistry" not in module_source
    assert "PromptRegistry" not in module_source
    assert "PromptRenderer" not in module_source
    assert "parse_gaming_script_quality_review" not in module_source
    assert "parse_gaming_evidence_consistency_review" not in module_source
    assert "parse_gaming_storyboard_quality_review" not in module_source
    assert "parse_gaming_publication_readiness_review" not in module_source
    assert "provider.generate" not in module_source
    assert "prompts/" not in module_source
    assert "WorkflowRuntime" not in module_source
    assert "request_approval" not in module_source
    assert "approve(" not in module_source
    assert "reject(" not in module_source
    assert "publish(" not in module_source
    assert "generate_image" not in module_source
    assert "generate_video" not in module_source
    assert "generate_voice" not in module_source
    assert "sqlalchemy" not in module_source.casefold()
    assert "retry" not in module_source.casefold()
