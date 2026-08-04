"""Typed input and result models for the demo CreatorOS gaming workflow."""

from __future__ import annotations

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
    "GamingWorkflowInput",
    "GamingWorkflowResult",
]
