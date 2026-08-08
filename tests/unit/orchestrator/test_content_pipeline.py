"""Unit tests for the integrated AI content pipeline orchestrator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from creatoros.agents import (
    GamingMediaAgent,
    GamingResearchAgent,
    GamingReviewAgent,
    GamingScriptAgent,
    GamingStoryboardAgent,
    ResearchExecutionOptions,
)
from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError
from creatoros.orchestrator import (
    GamingContentPipeline,
    GamingContentPipelineRequest,
    GamingContentPipelineResult,
    build_gaming_content_pipeline,
)
from creatoros.orchestrator.content_pipeline import (
    PIPELINE_NAME,
    STAGE_EVIDENCE_CONSISTENCY_REVIEW,
    STAGE_NARRATION_DIRECTION,
    STAGE_OPPORTUNITY_EVALUATION,
    STAGE_PUBLICATION_READINESS_REVIEW,
    STAGE_SCRIPT_GENERATION,
    STAGE_SCRIPT_QUALITY_REVIEW,
    STAGE_STORYBOARD_QUALITY_REVIEW,
    STAGE_STORYBOARD_SCENE_BREAKDOWN,
    STAGE_THUMBNAIL_CONCEPT,
    STAGE_TREND_DISCOVERY,
)
from creatoros.parsing import (
    GamingEvidenceConsistencyReviewOutput,
    GamingNarrationDirectionOutput,
    GamingOpportunityEvaluationOutput,
    GamingPublicationReadinessReviewOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingThumbnailConceptOutput,
    GamingTrendDiscoveryOutput,
    StoryboardSceneBreakdownOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.prompts import create_builtin_prompt_registry
from creatoros.providers import create_provider_registry
from creatoros.providers.mock import MockLLMProvider
from creatoros.services import create_llm_execution_service

TREND_DISCOVERY_RESPONSE = (
    "TITLE:\nRoblox: Funny Myths\n"
    "GAME:\nRoblox\n"
    "TOPIC:\nfunny myths\n"
    "ANGLE:\nTest the funniest myth claims players keep repeating.\n"
    "WHY_NOW:\nPlayers are actively sharing funny myth claims again.\n"
    "SOURCE_SUMMARY:\nSupplied player discussions highlight repeated myth claims.\n"
    "CONFIDENCE:\nhigh"
)

OPPORTUNITY_EVALUATION_RESPONSE = (
    "DECISION:\naccept\n"
    "SCORE:\n86\n"
    "STRENGTHS:\nThe topic is curiosity-driven and easy to explain quickly.\n"
    "RISKS:\nClaims must stay tied to supplied evidence.\n"
    "RECOMMENDED_ANGLE:\nTest the most repeated funny myth claims with supplied evidence only.\n"
    "HOOK_DIRECTION:\nChallenge a common Roblox belief immediately.\n"
    "REASON:\nThe opportunity fits short-form myth-check content well."
)

SCRIPT_RESPONSE = (
    "TITLE:\nRoblox: Funny Myths\n"
    "HOOK:\nYou probably still believe this Roblox myth.\n"
    "BODY:\nPlayers keep repeating one funny Roblox myth, but the supplied evidence says otherwise.\n"
    "ENDING:\nThat is why this funny myth does not hold up.\n"
    "CALL_TO_ACTION:\nWhich Roblox myth should we check next?\n"
    "ESTIMATED_DURATION_SECONDS:\n30\n"
    "EVIDENCE_NOTE:\nUse supplied evidence only."
)

STORYBOARD_RESPONSE = (
    "STORYBOARD_TITLE:\nRoblox: Funny Myths\n"
    "SCENE_1:\n"
    "PURPOSE:\nOpen with the myth hook.\n"
    "SCRIPT_BEAT:\nYou probably still believe this Roblox myth.\n"
    "VISUAL:\nFast Roblox gameplay clip showing the myth setup.\n"
    "ON_SCREEN_TEXT:\nRoblox myth?\n"
    "DURATION_SECONDS:\n10\n"
    "SCENE_2:\n"
    "PURPOSE:\nExplain what the supplied evidence supports.\n"
    "SCRIPT_BEAT:\nPlayers keep repeating one funny Roblox myth, but the supplied evidence says otherwise.\n"
    "VISUAL:\nSimple comparison shot between myth claim and evidence-backed outcome.\n"
    "ON_SCREEN_TEXT:\nWhat the evidence says\n"
    "DURATION_SECONDS:\n20\n"
    "FINAL_SCENE_COUNT:\n2\n"
    "TOTAL_ESTIMATED_DURATION_SECONDS:\n30"
)

THUMBNAIL_RESPONSE = (
    "CONCEPT:\nShow the myth claim versus reality.\n"
    "FOCAL_SUBJECT:\nA Roblox avatar reacting to the myth result.\n"
    "BACKGROUND:\nRecognizable Roblox environment with motion blur.\n"
    "COMPOSITION:\nLarge subject with bold side-by-side contrast.\n"
    "EXPRESSION_OR_ACTION:\nSurprised reaction at the myth result.\n"
    "ON_IMAGE_TEXT:\nMyth?\n"
    "STYLE_DIRECTION:\nClean readable contrast with playful energy.\n"
    "AVOID:\nClutter and unsupported visual claims.\n"
    "EVIDENCE_NOTE:\nDerived from supplied evidence only."
)

NARRATION_RESPONSE = (
    "NARRATION_TEXT:\nYou probably still believe this Roblox myth.\n"
    "TONE:\nClear and engaging.\n"
    "PACE:\nBrisk but easy to follow.\n"
    "EMPHASIS:\nStress the myth claim and the correction.\n"
    "PAUSE_GUIDANCE:\nPause briefly before the correction.\n"
    "PRONUNCIATION_NOTES:\nSay Roblox clearly.\n"
    "TARGET_DURATION_SECONDS:\n30"
)

SCRIPT_REVIEW_RESPONSE = (
    "DECISION:\naccept\n"
    "SUMMARY:\nThe script is clear and focused.\n"
    "HOOK_REVIEW:\nThe hook creates immediate curiosity.\n"
    "CLARITY_REVIEW:\nThe script is easy to follow aloud.\n"
    "STRUCTURE_REVIEW:\nThe idea stays focused.\n"
    "FACTUAL_RESTRAINT:\nThe claims remain cautious.\n"
    "PACING_REVIEW:\nThe pacing fits the target.\n"
    "ENDING_REVIEW:\nThe ending closes cleanly.\n"
    "ISSUES:\nNone.\n"
    "RECOMMENDATIONS:\nKeep the phrasing concise."
)

EVIDENCE_REVIEW_RESPONSE = (
    "DECISION:\nconsistent\n"
    "SUMMARY:\nThe claims align with supplied evidence.\n"
    "SUPPORTED_CLAIMS:\nThe main correction is supported.\n"
    "UNSUPPORTED_CLAIMS:\nNone.\n"
    "CONTRADICTIONS:\nNone.\n"
    "UNCERTAINTIES:\nMinor uncertainty remains at the edge cases.\n"
    "OVERSTATEMENTS:\nNone.\n"
    "RECOMMENDATIONS:\nKeep cautious wording."
)

STORYBOARD_REVIEW_RESPONSE = (
    "DECISION:\naccept\n"
    "SUMMARY:\nThe storyboard supports the script well.\n"
    "SCRIPT_FIDELITY:\nThe scenes match the script.\n"
    "HOOK_SCENE:\nThe first scene supports the hook.\n"
    "SCENE_SEQUENCE:\nThe scene order is clear.\n"
    "VISUAL_CLARITY:\nThe visuals are understandable.\n"
    "PACING:\nThe pacing is balanced.\n"
    "ENDING_SCENE:\nThe closing scene lands clearly.\n"
    "UNSUPPORTED_VISUALS:\nNone.\n"
    "ISSUES:\nNone.\n"
    "RECOMMENDATIONS:\nPreserve the current structure."
)

PUBLICATION_REVIEW_RESPONSE = (
    "DECISION:\nready_for_human_review\n"
    "SUMMARY:\nThe package is aligned for human review.\n"
    "ARTIFACT_ALIGNMENT:\nThe title, script, storyboard, and plans are aligned.\n"
    "EVIDENCE_STATUS:\nThe evidence review does not show unresolved contradictions.\n"
    "MISSING_OR_INCOMPLETE:\nNone.\n"
    "BLOCKERS:\nNone.\n"
    "NON_BLOCKING_IMPROVEMENTS:\nThumbnail text could be even shorter.\n"
    "HUMAN_REVIEW_FOCUS:\nCheck final tone and branding."
)


def run_async(coro):
    """Execute async pipeline calls in synchronous tests."""

    return asyncio.run(coro)


def build_request() -> GamingContentPipelineRequest:
    """Create one reusable integrated-pipeline request."""

    return GamingContentPipelineRequest(
        game="  Roblox  ",
        topic="  funny myths  ",
        research_signals=[
            " Players keep sharing the same funny myth. ",
            " Community comments repeat the same claim. ",
        ],
        platform="youtube_shorts",
        target_duration_seconds=30,
        tone="  clear and engaging  ",
    )


def build_trend_output() -> GamingTrendDiscoveryOutput:
    """Create one reusable trend-discovery output."""

    return GamingTrendDiscoveryOutput(
        title="Roblox: Funny Myths",
        game="Roblox",
        topic="funny myths",
        angle="Test the funniest myth claims players keep repeating.",
        why_now="Players are actively sharing funny myth claims again.",
        source_summary="Supplied player discussions highlight repeated myth claims.",
        confidence="high",
    )


def build_opportunity_output() -> GamingOpportunityEvaluationOutput:
    """Create one reusable opportunity-evaluation output."""

    return GamingOpportunityEvaluationOutput(
        decision="accept",
        score=86,
        strengths="The topic is curiosity-driven and easy to explain quickly.",
        risks="Claims must stay tied to supplied evidence.",
        recommended_angle="Test the most repeated funny myth claims with supplied evidence only.",
        hook_direction="Challenge a common Roblox belief immediately.",
        reason="The opportunity fits short-form myth-check content well.",
    )


def build_script_output() -> YouTubeShortsScriptOutput:
    """Create one reusable script output."""

    return YouTubeShortsScriptOutput(
        title="Roblox: Funny Myths",
        hook="You probably still believe this Roblox myth.",
        body="Players keep repeating one funny Roblox myth, but the supplied evidence says otherwise.",
        ending="That is why this funny myth does not hold up.",
        call_to_action="Which Roblox myth should we check next?",
        estimated_duration_seconds=30,
        evidence_note="Use supplied evidence only.",
    )


def build_storyboard_output() -> StoryboardSceneBreakdownOutput:
    """Create one reusable storyboard output."""

    return StoryboardSceneBreakdownOutput.model_validate(
        {
            "storyboard_title": "Roblox: Funny Myths",
            "scenes": [
                {
                    "scene_number": 1,
                    "purpose": "Open with the myth hook.",
                    "script_beat": "You probably still believe this Roblox myth.",
                    "visual": "Fast Roblox gameplay clip showing the myth setup.",
                    "on_screen_text": "Roblox myth?",
                    "duration_seconds": 10.0,
                },
                {
                    "scene_number": 2,
                    "purpose": "Explain what the supplied evidence supports.",
                    "script_beat": "Players keep repeating one funny Roblox myth, but the supplied evidence says otherwise.",
                    "visual": "Simple comparison shot between myth claim and evidence-backed outcome.",
                    "on_screen_text": "What the evidence says",
                    "duration_seconds": 20.0,
                },
            ],
            "final_scene_count": 2,
            "total_estimated_duration_seconds": 30.0,
        }
    )


def build_thumbnail_output() -> GamingThumbnailConceptOutput:
    """Create one reusable thumbnail output."""

    return GamingThumbnailConceptOutput(
        concept="Show the myth claim versus reality.",
        focal_subject="A Roblox avatar reacting to the myth result.",
        background="Recognizable Roblox environment with motion blur.",
        composition="Large subject with bold side-by-side contrast.",
        expression_or_action="Surprised reaction at the myth result.",
        on_image_text="Myth?",
        style_direction="Clean readable contrast with playful energy.",
        avoid="Clutter and unsupported visual claims.",
        evidence_note="Derived from supplied evidence only.",
    )


def build_narration_output() -> GamingNarrationDirectionOutput:
    """Create one reusable narration output."""

    return GamingNarrationDirectionOutput(
        narration_text="You probably still believe this Roblox myth.",
        tone="Clear and engaging.",
        pace="Brisk but easy to follow.",
        emphasis="Stress the myth claim and the correction.",
        pause_guidance="Pause briefly before the correction.",
        pronunciation_notes="Say Roblox clearly.",
        target_duration_seconds=30,
    )


def build_script_review_output() -> GamingScriptQualityReviewOutput:
    """Create one reusable script-review output."""

    return GamingScriptQualityReviewOutput(
        decision="accept",
        summary="The script is clear and focused.",
        hook_review="The hook creates immediate curiosity.",
        clarity_review="The script is easy to follow aloud.",
        structure_review="The idea stays focused.",
        factual_restraint="The claims remain cautious.",
        pacing_review="The pacing fits the target.",
        ending_review="The ending closes cleanly.",
        issues="None.",
        recommendations="Keep the phrasing concise.",
    )


def build_evidence_review_output() -> GamingEvidenceConsistencyReviewOutput:
    """Create one reusable evidence-review output."""

    return GamingEvidenceConsistencyReviewOutput(
        decision="consistent",
        summary="The claims align with supplied evidence.",
        supported_claims="The main correction is supported.",
        unsupported_claims="None.",
        contradictions="None.",
        uncertainties="Minor uncertainty remains at the edge cases.",
        overstatements="None.",
        recommendations="Keep cautious wording.",
    )


def build_storyboard_review_output() -> GamingStoryboardQualityReviewOutput:
    """Create one reusable storyboard-review output."""

    return GamingStoryboardQualityReviewOutput(
        decision="accept",
        summary="The storyboard supports the script well.",
        script_fidelity="The scenes match the script.",
        hook_scene="The first scene supports the hook.",
        scene_sequence="The scene order is clear.",
        visual_clarity="The visuals are understandable.",
        pacing="The pacing is balanced.",
        ending_scene="The closing scene lands clearly.",
        unsupported_visuals="None.",
        issues="None.",
        recommendations="Preserve the current structure.",
    )


def build_publication_review_output() -> GamingPublicationReadinessReviewOutput:
    """Create one reusable publication-readiness output."""

    return GamingPublicationReadinessReviewOutput(
        decision="ready_for_human_review",
        summary="The package is aligned for human review.",
        artifact_alignment="The title, script, storyboard, and plans are aligned.",
        evidence_status="The evidence review does not show unresolved contradictions.",
        missing_or_incomplete="None.",
        blockers="None.",
        non_blocking_improvements="Thumbnail text could be even shorter.",
        human_review_focus="Check final tone and branding.",
    )


class SpyResearchAgent(GamingResearchAgent):
    """Record research-agent pipeline interactions without real LLM execution."""

    def __init__(
        self,
        call_log: list[str],
        *,
        trend_output: GamingTrendDiscoveryOutput | None = None,
        opportunity_output: GamingOpportunityEvaluationOutput | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.llm_execution_service = None
        self.call_log = call_log
        self.trend_output = build_trend_output() if trend_output is None else trend_output
        self.opportunity_output = (
            build_opportunity_output() if opportunity_output is None else opportunity_output
        )
        self.fail_on = fail_on
        self.discover_requests: list[object] = []
        self.evaluate_requests: list[object] = []
        self.expand_calls = 0

    async def discover_trends(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_TREND_DISCOVERY)
        self.discover_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_TREND_DISCOVERY:
            raise CreatorOSValidationError("research failed")
        return self.trend_output.model_copy(deep=True)

    async def evaluate_opportunity(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_OPPORTUNITY_EVALUATION)
        self.evaluate_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_OPPORTUNITY_EVALUATION:
            raise CreatorOSValidationError("opportunity failed")
        return self.opportunity_output.model_copy(deep=True)

    async def expand_keywords(self, request, *, execution_options=None):  # type: ignore[override]
        del request, execution_options
        self.expand_calls += 1
        raise AssertionError("expand_keywords should not be called by the integrated pipeline")


class SpyScriptAgent(GamingScriptAgent):
    """Record script-agent pipeline interactions without real LLM execution."""

    def __init__(
        self,
        call_log: list[str],
        *,
        script_output: YouTubeShortsScriptOutput | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.llm_execution_service = None
        self.call_log = call_log
        self.script_output = build_script_output() if script_output is None else script_output
        self.fail_on = fail_on
        self.script_requests: list[object] = []
        self.hook_calls = 0
        self.cta_calls = 0

    async def generate_script(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_SCRIPT_GENERATION)
        self.script_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_SCRIPT_GENERATION:
            raise CreatorOSValidationError("script failed")
        return self.script_output.model_copy(deep=True)

    async def generate_hooks(self, request, *, execution_options=None):  # type: ignore[override]
        del request, execution_options
        self.hook_calls += 1
        raise AssertionError("generate_hooks should not be called by the integrated pipeline")

    async def generate_cta(self, request, *, execution_options=None):  # type: ignore[override]
        del request, execution_options
        self.cta_calls += 1
        raise AssertionError("generate_cta should not be called by the integrated pipeline")


class SpyStoryboardAgent(GamingStoryboardAgent):
    """Record storyboard-agent pipeline interactions without real LLM execution."""

    def __init__(
        self,
        call_log: list[str],
        *,
        storyboard_output: StoryboardSceneBreakdownOutput | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.llm_execution_service = None
        self.call_log = call_log
        self.storyboard_output = (
            build_storyboard_output() if storyboard_output is None else storyboard_output
        )
        self.fail_on = fail_on
        self.breakdown_requests: list[object] = []
        self.timing_calls = 0
        self.visual_direction_calls = 0

    async def break_down_scenes(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_STORYBOARD_SCENE_BREAKDOWN)
        self.breakdown_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_STORYBOARD_SCENE_BREAKDOWN:
            raise CreatorOSValidationError("storyboard failed")
        return self.storyboard_output.model_copy(deep=True)

    async def review_timing(self, request, *, execution_options=None):  # type: ignore[override]
        del request, execution_options
        self.timing_calls += 1
        raise AssertionError("review_timing should not be called by the integrated pipeline")

    async def generate_visual_direction(self, request, *, execution_options=None):  # type: ignore[override]
        del request, execution_options
        self.visual_direction_calls += 1
        raise AssertionError("generate_visual_direction should not be called by the integrated pipeline")


class SpyMediaAgent(GamingMediaAgent):
    """Record media-agent pipeline interactions without real LLM execution."""

    def __init__(
        self,
        call_log: list[str],
        *,
        thumbnail_output: GamingThumbnailConceptOutput | None = None,
        narration_output: GamingNarrationDirectionOutput | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.llm_execution_service = None
        self.call_log = call_log
        self.thumbnail_output = build_thumbnail_output() if thumbnail_output is None else thumbnail_output
        self.narration_output = build_narration_output() if narration_output is None else narration_output
        self.fail_on = fail_on
        self.thumbnail_requests: list[object] = []
        self.narration_requests: list[object] = []
        self.scene_visual_calls = 0
        self.scene_motion_calls = 0

    async def generate_thumbnail_concept(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_THUMBNAIL_CONCEPT)
        self.thumbnail_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_THUMBNAIL_CONCEPT:
            raise CreatorOSValidationError("thumbnail failed")
        return self.thumbnail_output.model_copy(deep=True)

    async def generate_narration_direction(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_NARRATION_DIRECTION)
        self.narration_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_NARRATION_DIRECTION:
            raise CreatorOSValidationError("narration failed")
        return self.narration_output.model_copy(deep=True)

    async def generate_scene_visual(self, request, *, execution_options=None):  # type: ignore[override]
        del request, execution_options
        self.scene_visual_calls += 1
        raise AssertionError("generate_scene_visual should not be called by the integrated pipeline")

    async def generate_scene_motion(self, request, *, execution_options=None):  # type: ignore[override]
        del request, execution_options
        self.scene_motion_calls += 1
        raise AssertionError("generate_scene_motion should not be called by the integrated pipeline")


class SpyReviewAgent(GamingReviewAgent):
    """Record review-agent pipeline interactions without real LLM execution."""

    def __init__(
        self,
        call_log: list[str],
        *,
        script_review: GamingScriptQualityReviewOutput | None = None,
        evidence_review: GamingEvidenceConsistencyReviewOutput | None = None,
        storyboard_review: GamingStoryboardQualityReviewOutput | None = None,
        publication_review: GamingPublicationReadinessReviewOutput | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.llm_execution_service = None
        self.call_log = call_log
        self.script_review = build_script_review_output() if script_review is None else script_review
        self.evidence_review = build_evidence_review_output() if evidence_review is None else evidence_review
        self.storyboard_review = (
            build_storyboard_review_output() if storyboard_review is None else storyboard_review
        )
        self.publication_review = (
            build_publication_review_output() if publication_review is None else publication_review
        )
        self.fail_on = fail_on
        self.script_requests: list[object] = []
        self.evidence_requests: list[object] = []
        self.storyboard_requests: list[object] = []
        self.publication_requests: list[object] = []

    async def review_script_quality(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_SCRIPT_QUALITY_REVIEW)
        self.script_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_SCRIPT_QUALITY_REVIEW:
            raise CreatorOSValidationError("script review failed")
        return self.script_review.model_copy(deep=True)

    async def review_evidence_consistency(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_EVIDENCE_CONSISTENCY_REVIEW)
        self.evidence_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_EVIDENCE_CONSISTENCY_REVIEW:
            raise CreatorOSValidationError("evidence review failed")
        return self.evidence_review.model_copy(deep=True)

    async def review_storyboard_quality(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_STORYBOARD_QUALITY_REVIEW)
        self.storyboard_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_STORYBOARD_QUALITY_REVIEW:
            raise CreatorOSValidationError("storyboard review failed")
        return self.storyboard_review.model_copy(deep=True)

    async def review_publication_readiness(self, request, *, execution_options=None):  # type: ignore[override]
        self.call_log.append(STAGE_PUBLICATION_READINESS_REVIEW)
        self.publication_requests.append((request.model_copy(deep=True), execution_options))
        if self.fail_on == STAGE_PUBLICATION_READINESS_REVIEW:
            raise CreatorOSValidationError("publication review failed")
        return self.publication_review.model_copy(deep=True)


def build_spy_pipeline(
    *,
    call_log: list[str] | None = None,
    research_fail_on: str | None = None,
    script_fail_on: str | None = None,
    storyboard_fail_on: str | None = None,
    media_fail_on: str | None = None,
    review_fail_on: str | None = None,
):
    """Build one pipeline wired to spy agents for orchestration testing."""

    resolved_call_log = [] if call_log is None else call_log
    research_agent = SpyResearchAgent(resolved_call_log, fail_on=research_fail_on)
    script_agent = SpyScriptAgent(resolved_call_log, fail_on=script_fail_on)
    storyboard_agent = SpyStoryboardAgent(resolved_call_log, fail_on=storyboard_fail_on)
    media_agent = SpyMediaAgent(resolved_call_log, fail_on=media_fail_on)
    review_agent = SpyReviewAgent(resolved_call_log, fail_on=review_fail_on)
    pipeline = GamingContentPipeline(
        research_agent=research_agent,
        script_agent=script_agent,
        storyboard_agent=storyboard_agent,
        media_agent=media_agent,
        review_agent=review_agent,
    )
    return pipeline, research_agent, script_agent, storyboard_agent, media_agent, review_agent


class SequencedMockLLMProvider(MockLLMProvider):
    """Deterministic mock LLM provider that returns a fixed response sequence."""

    def __init__(self, responses: list[str] | tuple[str, ...]) -> None:
        response_list = list(responses)
        super().__init__(response_text=response_list[0])
        self._responses = response_list
        self.calls = 0

    async def generate(self, request, *, context=None):  # type: ignore[override]
        if self.calls >= len(self._responses):
            raise AssertionError("No mock LLM response was configured for this pipeline call")
        self._response_text = self._responses[self.calls]
        self.calls += 1
        return await super().generate(request, context=context)


def build_settings() -> Settings:
    """Create isolated settings for the real offline pipeline test."""

    project_root = Path("C:/GamingAIFactory")
    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider="mock",
        default_llm_model="mock-model",
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


def test_pipeline_accepts_required_agent_dependencies() -> None:
    """The content pipeline should accept the five required application agents."""

    pipeline, *_ = build_spy_pipeline()

    assert isinstance(pipeline.research_agent, GamingResearchAgent)
    assert isinstance(pipeline.script_agent, GamingScriptAgent)
    assert isinstance(pipeline.storyboard_agent, GamingStoryboardAgent)
    assert isinstance(pipeline.media_agent, GamingMediaAgent)
    assert isinstance(pipeline.review_agent, GamingReviewAgent)


@pytest.mark.parametrize(
    ("dependency_name", "kwargs"),
    [
        ("research_agent", {"research_agent": object()}),
        ("script_agent", {"script_agent": object()}),
        ("storyboard_agent", {"storyboard_agent": object()}),
        ("media_agent", {"media_agent": object()}),
        ("review_agent", {"review_agent": object()}),
    ],
)
def test_pipeline_rejects_invalid_dependencies(
    dependency_name: str,
    kwargs: dict[str, object],
) -> None:
    """Invalid pipeline dependencies should fail safely."""

    _, research_agent, script_agent, storyboard_agent, media_agent, review_agent = build_spy_pipeline()
    dependencies: dict[str, object] = {
        "research_agent": research_agent,
        "script_agent": script_agent,
        "storyboard_agent": storyboard_agent,
        "media_agent": media_agent,
        "review_agent": review_agent,
    }
    dependencies.update(kwargs)

    with pytest.raises(CreatorOSValidationError, match=dependency_name):
        GamingContentPipeline(**dependencies)  # type: ignore[arg-type]


def test_pipeline_request_normalizes_strings_and_defensively_copies_signals() -> None:
    """Pipeline requests should trim strings and isolate mutable research-signal inputs."""

    original_signals = ["  first signal  ", "  second signal  "]
    request = GamingContentPipelineRequest(
        game="  Roblox  ",
        topic="  funny myths  ",
        research_signals=original_signals,
        target_duration_seconds=30,
        tone="  clear and engaging  ",
    )
    original_signals.append("later mutation")

    assert request.game == "Roblox"
    assert request.topic == "funny myths"
    assert request.research_signals == ("first signal", "second signal")
    assert request.tone == "clear and engaging"


def test_pipeline_request_rejects_blank_values_and_non_positive_duration() -> None:
    """Pipeline requests should reject blank required fields and invalid durations."""

    with pytest.raises(ValueError, match="game must not be blank"):
        GamingContentPipelineRequest(
            game="   ",
            topic="funny myths",
            research_signals=["signal"],
            target_duration_seconds=30,
        )

    with pytest.raises(ValueError):
        GamingContentPipelineRequest(
            game="Roblox",
            topic="funny myths",
            research_signals=["signal"],
            target_duration_seconds=0,
        )


def test_pipeline_runs_in_deterministic_bounded_order_without_unnecessary_calls() -> None:
    """The first integrated pipeline should use one fixed bounded happy path."""

    call_log: list[str] = []
    pipeline, research_agent, script_agent, storyboard_agent, media_agent, review_agent = build_spy_pipeline(
        call_log=call_log
    )

    result = run_async(pipeline.run(build_request()))

    assert call_log == [
        STAGE_TREND_DISCOVERY,
        STAGE_OPPORTUNITY_EVALUATION,
        STAGE_SCRIPT_GENERATION,
        STAGE_STORYBOARD_SCENE_BREAKDOWN,
        STAGE_THUMBNAIL_CONCEPT,
        STAGE_NARRATION_DIRECTION,
        STAGE_SCRIPT_QUALITY_REVIEW,
        STAGE_EVIDENCE_CONSISTENCY_REVIEW,
        STAGE_STORYBOARD_QUALITY_REVIEW,
        STAGE_PUBLICATION_READINESS_REVIEW,
    ]
    assert len(call_log) == 10
    assert research_agent.expand_calls == 0
    assert script_agent.hook_calls == 0
    assert script_agent.cta_calls == 0
    assert storyboard_agent.timing_calls == 0
    assert storyboard_agent.visual_direction_calls == 0
    assert media_agent.scene_visual_calls == 0
    assert media_agent.scene_motion_calls == 0
    assert result.final_stage == STAGE_PUBLICATION_READINESS_REVIEW
    assert result.pipeline_name == PIPELINE_NAME
    assert review_agent.publication_requests


def test_pipeline_flows_data_between_agent_boundaries_correctly() -> None:
    """Typed outputs should be converted cleanly between pipeline stages."""

    pipeline, research_agent, script_agent, storyboard_agent, media_agent, review_agent = build_spy_pipeline()

    result = run_async(pipeline.run(build_request()))

    discover_request, discover_options = research_agent.discover_requests[0]
    assert discover_request.game == "Roblox"
    assert discover_request.topic == "funny myths"
    assert discover_request.research_signals == "- Players keep sharing the same funny myth.\n- Community comments repeat the same claim."
    assert discover_options is None

    evaluate_request, _ = research_agent.evaluate_requests[0]
    assert evaluate_request.title == "Roblox: Funny Myths"
    assert evaluate_request.angle == "Test the funniest myth claims players keep repeating."

    script_request, _ = script_agent.script_requests[0]
    assert script_request.title == "Roblox: Funny Myths"
    assert script_request.angle == "Test the most repeated funny myth claims with supplied evidence only."
    assert script_request.hook_direction == "Challenge a common Roblox belief immediately."
    assert script_request.source_summary == "Supplied player discussions highlight repeated myth claims."

    storyboard_request, _ = storyboard_agent.breakdown_requests[0]
    assert storyboard_request.title == "Roblox: Funny Myths"
    assert storyboard_request.hook == "You probably still believe this Roblox myth."
    assert storyboard_request.call_to_action == "Which Roblox myth should we check next?"

    thumbnail_request, _ = media_agent.thumbnail_requests[0]
    assert thumbnail_request.title == "Roblox: Funny Myths"
    assert thumbnail_request.game == "Roblox"
    assert thumbnail_request.topic == "funny myths"
    assert "Storyboard title: Roblox: Funny Myths." in thumbnail_request.visual_context

    narration_request, _ = media_agent.narration_requests[0]
    assert narration_request.title == "Roblox: Funny Myths"
    assert narration_request.tone == "clear and engaging"
    assert "You probably still believe this Roblox myth." in narration_request.script_text

    script_review_request, _ = review_agent.script_requests[0]
    assert script_review_request.title == "Roblox: Funny Myths"
    assert script_review_request.topic == "funny myths"
    assert script_review_request.angle == "Test the most repeated funny myth claims with supplied evidence only."

    evidence_request, _ = review_agent.evidence_requests[0]
    assert evidence_request.game == "Roblox"
    assert evidence_request.source_summary == "Supplied player discussions highlight repeated myth claims."
    assert evidence_request.research_notes == "- Players keep sharing the same funny myth.\n- Community comments repeat the same claim."
    assert evidence_request.content_stage == "script_draft"
    assert "Which Roblox myth should we check next?" in evidence_request.content_text

    storyboard_review_request, _ = review_agent.storyboard_requests[0]
    assert storyboard_review_request.title == "Roblox: Funny Myths"
    assert storyboard_review_request.game == "Roblox"
    assert "Storyboard title: Roblox: Funny Myths." in storyboard_review_request.storyboard_text

    publication_request, _ = review_agent.publication_requests[0]
    assert publication_request.title == "Roblox: Funny Myths"
    assert publication_request.game == "Roblox"
    assert "Decision: consistent." in publication_request.evidence_review
    assert "Concept: Show the myth claim versus reality." in publication_request.thumbnail_summary
    assert result.opportunity.title == "Roblox: Funny Myths"


def test_pipeline_returns_typed_pre_publication_aggregate_result() -> None:
    """The pipeline result should preserve typed major outputs without raw provider data."""

    pipeline, *_ = build_spy_pipeline()

    result = run_async(pipeline.run(build_request()))
    dumped = result.model_dump()

    assert isinstance(result, GamingContentPipelineResult)
    assert result.opportunity.title == "Roblox: Funny Myths"
    assert result.script.title == "Roblox: Funny Myths"
    assert result.storyboard.storyboard_title == "Roblox: Funny Myths"
    assert result.media_plans.thumbnail_concept.concept == "Show the myth claim versus reality."
    assert result.media_plans.narration_direction.tone == "Clear and engaging."
    assert result.review_results.script_quality.decision == "accept"
    assert result.review_results.evidence_consistency.decision == "consistent"
    assert result.review_results.storyboard_quality.decision == "accept"
    assert result.publication_readiness.decision == "ready_for_human_review"
    assert result.media_plans.scene_visuals == ()
    assert result.media_plans.scene_motions == ()
    assert "raw_response" not in dumped
    assert "api_key" not in str(dumped)
    assert "approval_request" not in dumped
    assert "published_post" not in dumped


def test_positive_readiness_does_not_publish_or_approve() -> None:
    """Publication readiness must remain separate from approval and publishing."""

    pipeline, *_ = build_spy_pipeline()

    result = run_async(pipeline.run(build_request()))

    assert result.publication_readiness.decision == "ready_for_human_review"
    assert result.final_stage == STAGE_PUBLICATION_READINESS_REVIEW
    assert not hasattr(result, "published_post")
    assert not hasattr(result, "approval_request")
    assert "publish" not in result.model_dump()


@pytest.mark.parametrize(
    ("failure_kwargs", "expected_calls"),
    [
        ({"research_fail_on": STAGE_TREND_DISCOVERY}, [STAGE_TREND_DISCOVERY]),
        (
            {"script_fail_on": STAGE_SCRIPT_GENERATION},
            [
                STAGE_TREND_DISCOVERY,
                STAGE_OPPORTUNITY_EVALUATION,
                STAGE_SCRIPT_GENERATION,
            ],
        ),
        (
            {"storyboard_fail_on": STAGE_STORYBOARD_SCENE_BREAKDOWN},
            [
                STAGE_TREND_DISCOVERY,
                STAGE_OPPORTUNITY_EVALUATION,
                STAGE_SCRIPT_GENERATION,
                STAGE_STORYBOARD_SCENE_BREAKDOWN,
            ],
        ),
        (
            {"media_fail_on": STAGE_THUMBNAIL_CONCEPT},
            [
                STAGE_TREND_DISCOVERY,
                STAGE_OPPORTUNITY_EVALUATION,
                STAGE_SCRIPT_GENERATION,
                STAGE_STORYBOARD_SCENE_BREAKDOWN,
                STAGE_THUMBNAIL_CONCEPT,
            ],
        ),
        (
            {"review_fail_on": STAGE_SCRIPT_QUALITY_REVIEW},
            [
                STAGE_TREND_DISCOVERY,
                STAGE_OPPORTUNITY_EVALUATION,
                STAGE_SCRIPT_GENERATION,
                STAGE_STORYBOARD_SCENE_BREAKDOWN,
                STAGE_THUMBNAIL_CONCEPT,
                STAGE_NARRATION_DIRECTION,
                STAGE_SCRIPT_QUALITY_REVIEW,
            ],
        ),
    ],
)
def test_pipeline_fails_fast_and_stops_downstream_calls(
    failure_kwargs: dict[str, str],
    expected_calls: list[str],
) -> None:
    """Any required-stage failure should stop later pipeline work immediately."""

    call_log: list[str] = []
    pipeline, *_ = build_spy_pipeline(call_log=call_log, **failure_kwargs)

    with pytest.raises(CreatorOSValidationError):
        run_async(pipeline.run(build_request()))

    assert call_log == expected_calls


def test_pipeline_forwards_shared_execution_options_to_every_agent_call() -> None:
    """One shared provider-neutral execution-options model should flow through the whole pipeline."""

    pipeline, research_agent, script_agent, storyboard_agent, media_agent, review_agent = build_spy_pipeline()
    options = ResearchExecutionOptions(
        provider_name="openai",
        model="gpt-5-mini",
        temperature=0.3,
        max_output_tokens=120,
        timeout_seconds=9.0,
    )

    run_async(pipeline.run(build_request(), execution_options=options))

    recorded_options = [
        research_agent.discover_requests[0][1],
        research_agent.evaluate_requests[0][1],
        script_agent.script_requests[0][1],
        storyboard_agent.breakdown_requests[0][1],
        media_agent.thumbnail_requests[0][1],
        media_agent.narration_requests[0][1],
        review_agent.script_requests[0][1],
        review_agent.evidence_requests[0][1],
        review_agent.storyboard_requests[0][1],
        review_agent.publication_requests[0][1],
    ]

    assert all(option == options for option in recorded_options)


def test_pipeline_factory_builds_all_agents_from_one_service() -> None:
    """The optional pipeline factory should compose all five application agents from one service."""

    service = create_llm_execution_service(settings=build_settings())

    pipeline = build_gaming_content_pipeline(service)

    assert isinstance(pipeline.research_agent, GamingResearchAgent)
    assert isinstance(pipeline.script_agent, GamingScriptAgent)
    assert isinstance(pipeline.storyboard_agent, GamingStoryboardAgent)
    assert isinstance(pipeline.media_agent, GamingMediaAgent)
    assert isinstance(pipeline.review_agent, GamingReviewAgent)


def test_pipeline_module_avoids_direct_provider_parser_prompt_and_publishing_coupling() -> None:
    """The pipeline should orchestrate through agents only and stop before publishing."""

    module_source = Path("creatoros/orchestrator/content_pipeline.py").read_text(encoding="utf-8")

    assert "openai" not in module_source.casefold()
    assert "OpenAILLMProvider" not in module_source
    assert "MockLLMProvider" not in module_source
    assert "ParserRegistry" not in module_source
    assert "PromptRegistry" not in module_source
    assert "PromptRenderer" not in module_source
    assert "provider.generate" not in module_source
    assert "publish(" not in module_source
    assert "request_approval" not in module_source
    assert "approve(" not in module_source
    assert "generate_scene_visual" not in module_source
    assert "generate_scene_motion" not in module_source


def test_full_pipeline_completes_offline_with_real_agents_and_mock_provider() -> None:
    """The integrated pipeline should execute fully offline through the real agent and service path."""

    provider_registry = create_provider_registry()
    provider = SequencedMockLLMProvider(
        [
            TREND_DISCOVERY_RESPONSE,
            OPPORTUNITY_EVALUATION_RESPONSE,
            SCRIPT_RESPONSE,
            STORYBOARD_RESPONSE,
            THUMBNAIL_RESPONSE,
            NARRATION_RESPONSE,
            SCRIPT_REVIEW_RESPONSE,
            EVIDENCE_REVIEW_RESPONSE,
            STORYBOARD_REVIEW_RESPONSE,
            PUBLICATION_REVIEW_RESPONSE,
        ]
    )
    provider_registry.register(provider)
    service = create_llm_execution_service(
        prompt_registry=create_builtin_prompt_registry(),
        provider_registry=provider_registry,
        settings=build_settings(),
    )
    pipeline = build_gaming_content_pipeline(service)

    result = run_async(
        pipeline.run(
            GamingContentPipelineRequest(
                game="Roblox",
                topic="funny myths",
                research_signals=[
                    "Players keep sharing the same funny myth.",
                    "Community comments repeat the same claim.",
                ],
                platform="youtube_shorts",
                target_duration_seconds=30,
                tone="clear and engaging",
            )
        )
    )

    assert isinstance(result.trend_discovery, GamingTrendDiscoveryOutput)
    assert isinstance(result.opportunity_evaluation, GamingOpportunityEvaluationOutput)
    assert isinstance(result.script, YouTubeShortsScriptOutput)
    assert isinstance(result.storyboard, StoryboardSceneBreakdownOutput)
    assert isinstance(result.media_plans.thumbnail_concept, GamingThumbnailConceptOutput)
    assert isinstance(result.media_plans.narration_direction, GamingNarrationDirectionOutput)
    assert isinstance(result.review_results.script_quality, GamingScriptQualityReviewOutput)
    assert isinstance(result.review_results.evidence_consistency, GamingEvidenceConsistencyReviewOutput)
    assert isinstance(result.review_results.storyboard_quality, GamingStoryboardQualityReviewOutput)
    assert isinstance(result.publication_readiness, GamingPublicationReadinessReviewOutput)
    assert result.publication_readiness.decision == "ready_for_human_review"
    assert result.final_stage == STAGE_PUBLICATION_READINESS_REVIEW
    assert provider.calls == 10
