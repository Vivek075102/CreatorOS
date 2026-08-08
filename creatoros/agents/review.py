"""Provider-independent review agent integrations for CreatorOS."""

from __future__ import annotations

from typing import TypeVar

from pydantic import Field, field_validator

from creatoros.agents.research import ResearchExecutionOptions
from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingEvidenceConsistencyReviewOutput,
    GamingNarrationDirectionOutput,
    GamingPublicationReadinessReviewOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingThumbnailConceptOutput,
    StoryboardSceneBreakdownOutput,
    StoryboardScenePlan,
    YouTubeShortsScriptOutput,
)
from creatoros.prompts import (
    GAMING_EVIDENCE_CONSISTENCY_REVIEW,
    GAMING_PUBLICATION_READINESS_REVIEW,
    GAMING_SCRIPT_QUALITY_REVIEW,
    GAMING_STORYBOARD_QUALITY_REVIEW,
)
from creatoros.services import LLMExecutionRequest, LLMExecutionService

TReviewOutput = TypeVar(
    "TReviewOutput",
    GamingScriptQualityReviewOutput,
    GamingEvidenceConsistencyReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingPublicationReadinessReviewOutput,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank string values for review-agent inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _build_script_text(script_output: YouTubeShortsScriptOutput) -> str:
    """Combine one typed script output into one stable review string."""

    return (
        f"{script_output.hook} "
        f"{script_output.body} "
        f"{script_output.ending} "
        f"{script_output.call_to_action}"
    )


def _build_storyboard_scene_summary(scene_plan: StoryboardScenePlan) -> str:
    """Convert one typed storyboard scene into a compact serialized summary line."""

    return (
        f"Scene {scene_plan.scene_number}: "
        f"Purpose: {scene_plan.purpose}. "
        f"Script beat: {scene_plan.script_beat}. "
        f"Visual: {scene_plan.visual}. "
        f"On-screen text: {scene_plan.on_screen_text}. "
        f"Duration: {scene_plan.duration_seconds} seconds."
    )


def _build_storyboard_text(storyboard_output: StoryboardSceneBreakdownOutput) -> str:
    """Convert typed storyboard output into one stable review string."""

    scene_summaries = " ".join(
        _build_storyboard_scene_summary(scene_plan)
        for scene_plan in storyboard_output.scenes
    )
    return (
        f"Storyboard title: {storyboard_output.storyboard_title}. "
        f"{scene_summaries} "
        f"Final scene count: {storyboard_output.final_scene_count}. "
        f"Total estimated duration: {storyboard_output.total_estimated_duration_seconds} seconds."
    )


def _build_thumbnail_summary(thumbnail_output: GamingThumbnailConceptOutput) -> str:
    """Convert typed thumbnail-planning output into one stable review string."""

    return (
        f"Concept: {thumbnail_output.concept}. "
        f"Focal subject: {thumbnail_output.focal_subject}. "
        f"Background: {thumbnail_output.background}. "
        f"Composition: {thumbnail_output.composition}. "
        f"On-image text: {thumbnail_output.on_image_text}. "
        f"Style direction: {thumbnail_output.style_direction}. "
        f"Avoid: {thumbnail_output.avoid}."
    )


def _build_narration_summary(narration_output: GamingNarrationDirectionOutput) -> str:
    """Convert typed narration-direction output into one stable review string."""

    return (
        f"Tone: {narration_output.tone}. "
        f"Pace: {narration_output.pace}. "
        f"Emphasis: {narration_output.emphasis}. "
        f"Pause guidance: {narration_output.pause_guidance}. "
        f"Pronunciation notes: {narration_output.pronunciation_notes}. "
        f"Target duration: {narration_output.target_duration_seconds} seconds."
    )


def _build_evidence_review_summary(
    evidence_review: GamingEvidenceConsistencyReviewOutput,
) -> str:
    """Convert typed evidence-review output into one stable review string."""

    return (
        f"Decision: {evidence_review.decision}. "
        f"Summary: {evidence_review.summary}. "
        f"Supported claims: {evidence_review.supported_claims}. "
        f"Unsupported claims: {evidence_review.unsupported_claims}. "
        f"Contradictions: {evidence_review.contradictions}. "
        f"Uncertainties: {evidence_review.uncertainties}. "
        f"Overstatements: {evidence_review.overstatements}. "
        f"Recommendations: {evidence_review.recommendations}."
    )


class GamingScriptQualityReviewRequest(CreatorOSModel):
    """Normalized application input for script-quality review."""

    title: str
    game: str
    topic: str
    angle: str
    source_summary: str
    script_text: str
    platform: str
    target_duration_seconds: int = Field(gt=0)

    @field_validator(
        "title",
        "game",
        "topic",
        "angle",
        "source_summary",
        "script_text",
        "platform",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_script(
        cls,
        script_output: YouTubeShortsScriptOutput,
        *,
        game: str,
        topic: str,
        angle: str,
        source_summary: str,
        platform: str,
    ) -> GamingScriptQualityReviewRequest:
        """Build a script-quality review request from one typed script output."""

        return cls(
            title=script_output.title,
            game=game,
            topic=topic,
            angle=angle,
            source_summary=source_summary,
            script_text=_build_script_text(script_output),
            platform=platform,
            target_duration_seconds=script_output.estimated_duration_seconds,
        )


class GamingEvidenceConsistencyReviewRequest(CreatorOSModel):
    """Normalized application input for evidence-consistency review."""

    game: str
    source_summary: str
    research_notes: str
    content_text: str
    content_stage: str

    @field_validator("game", "source_summary", "research_notes", "content_text", "content_stage")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_script(
        cls,
        script_output: YouTubeShortsScriptOutput,
        *,
        game: str,
        source_summary: str,
        research_notes: str,
        content_stage: str,
    ) -> GamingEvidenceConsistencyReviewRequest:
        """Build an evidence-consistency request from one typed script output."""

        return cls(
            game=game,
            source_summary=source_summary,
            research_notes=research_notes,
            content_text=_build_script_text(script_output),
            content_stage=content_stage,
        )


class GamingStoryboardQualityReviewRequest(CreatorOSModel):
    """Normalized application input for storyboard-quality review."""

    title: str
    game: str
    script_text: str
    storyboard_text: str
    platform: str
    target_duration_seconds: int = Field(gt=0)

    @field_validator("title", "game", "script_text", "storyboard_text", "platform")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_storyboard(
        cls,
        storyboard_output: StoryboardSceneBreakdownOutput,
        *,
        title: str,
        game: str,
        script_text: str,
        platform: str,
        target_duration_seconds: int,
    ) -> GamingStoryboardQualityReviewRequest:
        """Build a storyboard-quality review request from typed storyboard output."""

        return cls(
            title=title,
            game=game,
            script_text=script_text,
            storyboard_text=_build_storyboard_text(storyboard_output),
            platform=platform,
            target_duration_seconds=target_duration_seconds,
        )

    @classmethod
    def from_script_and_storyboard(
        cls,
        storyboard_output: StoryboardSceneBreakdownOutput,
        script_output: YouTubeShortsScriptOutput,
        *,
        game: str,
        platform: str,
    ) -> GamingStoryboardQualityReviewRequest:
        """Build a storyboard-quality request from typed script and storyboard outputs."""

        return cls(
            title=script_output.title,
            game=game,
            script_text=_build_script_text(script_output),
            storyboard_text=_build_storyboard_text(storyboard_output),
            platform=platform,
            target_duration_seconds=script_output.estimated_duration_seconds,
        )


class GamingPublicationReadinessReviewRequest(CreatorOSModel):
    """Normalized application input for publication-readiness review."""

    title: str
    game: str
    script_text: str
    storyboard_summary: str
    thumbnail_summary: str
    narration_summary: str
    evidence_review: str
    platform: str

    @field_validator(
        "title",
        "game",
        "script_text",
        "storyboard_summary",
        "thumbnail_summary",
        "narration_summary",
        "evidence_review",
        "platform",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @classmethod
    def from_review_inputs(
        cls,
        *,
        title: str,
        game: str,
        script_output: YouTubeShortsScriptOutput,
        storyboard_output: StoryboardSceneBreakdownOutput,
        thumbnail_output: GamingThumbnailConceptOutput,
        narration_output: GamingNarrationDirectionOutput,
        evidence_review_output: GamingEvidenceConsistencyReviewOutput,
        platform: str,
    ) -> GamingPublicationReadinessReviewRequest:
        """Build a publication-readiness request from typed upstream outputs."""

        return cls(
            title=title,
            game=game,
            script_text=_build_script_text(script_output),
            storyboard_summary=_build_storyboard_text(storyboard_output),
            thumbnail_summary=_build_thumbnail_summary(thumbnail_output),
            narration_summary=_build_narration_summary(narration_output),
            evidence_review=_build_evidence_review_summary(evidence_review_output),
            platform=platform,
        )


class GamingReviewAgent:
    """Application review agent that executes builtin review prompts through LLMExecutionService."""

    def __init__(self, llm_execution_service: LLMExecutionService) -> None:
        if not isinstance(llm_execution_service, LLMExecutionService):
            raise CreatorOSValidationError(
                "llm_execution_service must be an LLMExecutionService",
                code="agent_invalid_dependency",
                details={"dependency": "llm_execution_service"},
            )
        self.llm_execution_service = llm_execution_service

    async def review_script_quality(
        self,
        request: GamingScriptQualityReviewRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingScriptQualityReviewOutput:
        """Execute the builtin script-quality review prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_SCRIPT_QUALITY_REVIEW,
            variables={
                "title": request.title,
                "game": request.game,
                "topic": request.topic,
                "angle": request.angle,
                "source_summary": request.source_summary,
                "script_text": request.script_text,
                "platform": request.platform,
                "target_duration_seconds": request.target_duration_seconds,
            },
            output_model_type=GamingScriptQualityReviewOutput,
            execution_options=execution_options,
        )

    async def review_evidence_consistency(
        self,
        request: GamingEvidenceConsistencyReviewRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingEvidenceConsistencyReviewOutput:
        """Execute the builtin evidence-consistency review prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_EVIDENCE_CONSISTENCY_REVIEW,
            variables={
                "game": request.game,
                "source_summary": request.source_summary,
                "research_notes": request.research_notes,
                "content_text": request.content_text,
                "content_stage": request.content_stage,
            },
            output_model_type=GamingEvidenceConsistencyReviewOutput,
            execution_options=execution_options,
        )

    async def review_storyboard_quality(
        self,
        request: GamingStoryboardQualityReviewRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingStoryboardQualityReviewOutput:
        """Execute the builtin storyboard-quality review prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_STORYBOARD_QUALITY_REVIEW,
            variables={
                "title": request.title,
                "game": request.game,
                "script_text": request.script_text,
                "storyboard_text": request.storyboard_text,
                "platform": request.platform,
                "target_duration_seconds": request.target_duration_seconds,
            },
            output_model_type=GamingStoryboardQualityReviewOutput,
            execution_options=execution_options,
        )

    async def review_publication_readiness(
        self,
        request: GamingPublicationReadinessReviewRequest,
        *,
        execution_options: ResearchExecutionOptions | None = None,
    ) -> GamingPublicationReadinessReviewOutput:
        """Execute the builtin publication-readiness review prompt and return the typed parsed output."""

        return await self._execute_typed(
            prompt_name=GAMING_PUBLICATION_READINESS_REVIEW,
            variables={
                "title": request.title,
                "game": request.game,
                "script_text": request.script_text,
                "storyboard_summary": request.storyboard_summary,
                "thumbnail_summary": request.thumbnail_summary,
                "narration_summary": request.narration_summary,
                "evidence_review": request.evidence_review,
                "platform": request.platform,
            },
            output_model_type=GamingPublicationReadinessReviewOutput,
            execution_options=execution_options,
        )

    async def _execute_typed(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
        output_model_type: type[TReviewOutput],
        execution_options: ResearchExecutionOptions | None,
    ) -> TReviewOutput:
        """Execute one review prompt and require the expected typed parser output."""

        request = LLMExecutionRequest(
            prompt_name=prompt_name,
            variables=variables,
            provider_name=None if execution_options is None else execution_options.provider_name,
            model=None if execution_options is None else execution_options.model,
            temperature=None if execution_options is None else execution_options.temperature,
            max_output_tokens=None if execution_options is None else execution_options.max_output_tokens,
            timeout_seconds=None if execution_options is None else execution_options.timeout_seconds,
        )
        result = await self.llm_execution_service.execute(request)
        if not isinstance(result.output, output_model_type):
            raise CreatorOSValidationError(
                "review agent received an unexpected typed output model",
                code="agent_unexpected_output_model",
                details={
                    "prompt_name": prompt_name,
                    "expected_output_model": output_model_type.__name__,
                    "actual_output_model": type(result.output).__name__,
                },
            )
        return result.output


__all__ = [
    "GamingEvidenceConsistencyReviewRequest",
    "GamingPublicationReadinessReviewRequest",
    "GamingReviewAgent",
    "GamingScriptQualityReviewRequest",
    "GamingStoryboardQualityReviewRequest",
]
