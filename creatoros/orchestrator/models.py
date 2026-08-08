"""Typed input and result models for the demo CreatorOS gaming workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from creatoros.domain import (
    ContentBrief,
    ContentOpportunity,
    ContentPlatform,
    CreatorOSModel,
    GeneratedAsset,
    NarrationTrack,
    PublishedPost,
    PublishingPackage,
    Script,
    Storyboard,
)
from creatoros.parsing import (
    GamingEvidenceConsistencyReviewOutput,
    GamingNarrationDirectionOutput,
    GamingOpportunityEvaluationOutput,
    GamingPublicationReadinessReviewOutput,
    GamingSceneMotionOutput,
    GamingSceneVisualOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingThumbnailConceptOutput,
    GamingTrendDiscoveryOutput,
    StoryboardSceneBreakdownOutput,
    YouTubeShortsScriptOutput,
)
from creatoros.workflows import (
    ApprovalRequest,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowExecutionStatus,
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class GamingWorkflowInput(CreatorOSModel):
    """User-facing input contract for the deterministic demo gaming workflow."""

    game: str = "Minecraft"
    topic: str = "gaming facts"
    platform: ContentPlatform = ContentPlatform.YOUTUBE_SHORTS
    approve_publish: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("game", "topic")
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        """Trim and reject blank textual workflow inputs."""

        return _validate_non_blank(value, field_name=info.field_name)


class DemoAssetBundle(CreatorOSModel):
    """Normalized asset bundle produced by the demo asset agent and engine."""

    video: GeneratedAsset
    thumbnail: GeneratedAsset
    narration: NarrationTrack


class GamingContentPipelineRequest(CreatorOSModel):
    """Provider-independent input contract for the first integrated AI content pipeline."""

    game: str
    topic: str
    research_signals: tuple[str, ...]
    platform: ContentPlatform = ContentPlatform.YOUTUBE_SHORTS
    target_duration_seconds: int = Field(gt=0)
    tone: str = "clear and engaging"

    @field_validator("game", "topic", "tone")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank textual inputs."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("research_signals", mode="before")
    @classmethod
    def copy_research_signals(cls, value: object) -> tuple[str, ...]:
        """Copy mutable research-signal inputs defensively."""

        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if not isinstance(value, list | tuple):
            raise TypeError("research_signals must be a string, list, or tuple")
        return tuple(value)

    @field_validator("research_signals")
    @classmethod
    def validate_research_signals(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Trim research signals, reject blanks, and require at least one item."""

        normalized_items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise TypeError("research_signals must contain only strings")
            normalized_items.append(_validate_non_blank(item, field_name="research_signals"))
        if not normalized_items:
            raise ValueError("research_signals must contain at least one item")
        return tuple(normalized_items)


class GamingContentMediaPlanSet(CreatorOSModel):
    """Typed pre-production media-planning outputs for the integrated content pipeline."""

    thumbnail_concept: GamingThumbnailConceptOutput
    narration_direction: GamingNarrationDirectionOutput
    scene_visuals: tuple[GamingSceneVisualOutput, ...] = Field(default_factory=tuple)
    scene_motions: tuple[GamingSceneMotionOutput, ...] = Field(default_factory=tuple)


class GamingContentReviewSet(CreatorOSModel):
    """Typed advisory review outputs for the integrated content pipeline."""

    script_quality: GamingScriptQualityReviewOutput
    evidence_consistency: GamingEvidenceConsistencyReviewOutput
    storyboard_quality: GamingStoryboardQualityReviewOutput


class GamingContentPipelineResult(CreatorOSModel):
    """Serializable pre-publication aggregate output for the integrated AI content pipeline."""

    pipeline_name: str = "gaming_content_pipeline"
    final_stage: Literal["publication_readiness_review"] = "publication_readiness_review"
    trend_discovery: GamingTrendDiscoveryOutput
    opportunity_evaluation: GamingOpportunityEvaluationOutput
    opportunity: ContentOpportunity
    script: YouTubeShortsScriptOutput
    storyboard: StoryboardSceneBreakdownOutput
    media_plans: GamingContentMediaPlanSet
    review_results: GamingContentReviewSet
    publication_readiness: GamingPublicationReadinessReviewOutput


class GamingWorkflowResult(CreatorOSModel):
    """Serializable result contract for the deterministic demo gaming workflow."""

    execution: WorkflowExecution
    opportunity: ContentOpportunity
    brief: ContentBrief
    script: Script
    storyboard: Storyboard
    generated_assets: list[GeneratedAsset] = Field(default_factory=list)
    narration: NarrationTrack | None = None
    publishing_package: PublishingPackage | None = None
    published_post: PublishedPost | None = None
    approval_request: ApprovalRequest | None = None
    events: tuple[WorkflowEvent, ...]
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_status_dependent_fields(self) -> GamingWorkflowResult:
        """Enforce status-dependent result invariants for the demo workflow."""

        if self.execution.status is WorkflowExecutionStatus.COMPLETED and self.published_post is None:
            raise ValueError("published_post must be present when execution status is completed")

        if (
            self.execution.status is WorkflowExecutionStatus.AWAITING_APPROVAL
            and self.approval_request is None
        ):
            raise ValueError("approval_request must be present when execution status is awaiting_approval")

        if (
            self.execution.status is WorkflowExecutionStatus.AWAITING_APPROVAL
            and self.published_post is not None
        ):
            raise ValueError("published_post must be absent when execution status is awaiting_approval")

        return self


__all__ = [
    "DemoAssetBundle",
    "GamingContentMediaPlanSet",
    "GamingContentPipelineRequest",
    "GamingContentPipelineResult",
    "GamingContentReviewSet",
    "GamingWorkflowInput",
    "GamingWorkflowResult",
]
