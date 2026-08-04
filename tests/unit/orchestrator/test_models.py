"""Unit tests for deterministic gaming workflow orchestration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from creatoros.domain import (
    AssetType,
    ContentBrief,
    ContentOpportunity,
    ContentPlatform,
    GeneratedAsset,
    NarrationTrack,
    PublishedPost,
    PublishingPackage,
    Scene,
    Script,
    Storyboard,
)
from creatoros.orchestrator import DemoAssetBundle, GamingWorkflowInput, GamingWorkflowResult
from creatoros.workflows import (
    ApprovalRequest,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowExecution,
    WorkflowExecutionStatus,
)


def build_opportunity() -> ContentOpportunity:
    """Return a deterministic content opportunity fixture."""

    return ContentOpportunity(
        title="Demo opportunity",
        game="Minecraft",
        topic="gaming facts",
        source="mock_trends",
        opportunity_score=80,
        reasoning="Demo reasoning",
        estimated_duration_seconds=30,
        references=["mock://trend"],
    )


def build_brief() -> ContentBrief:
    """Return a deterministic content brief fixture."""

    return ContentBrief(
        title="Demo opportunity",
        audience="Minecraft players",
        platform="youtube_shorts",
        objective="Explain one interesting fact.",
        tone="clear",
        hook_direction="Lead with surprise",
        constraints=["Keep it short."],
        notes="Demo notes",
    )


def build_script() -> Script:
    """Return a deterministic script fixture."""

    return Script(
        title="Demo opportunity",
        hook="Hook",
        body="Body",
        ending="Ending",
        call_to_action="CTA",
        estimated_duration_seconds=30,
        version=1,
    )


def build_storyboard() -> Storyboard:
    """Return a deterministic storyboard fixture."""

    return Storyboard(
        title="Demo storyboard",
        scenes=[
            Scene(
                scene_number=1,
                duration_seconds=10,
                narration="Hook",
                visual_description="Visual",
            )
        ],
        notes="Notes",
    )


def build_execution(status: WorkflowExecutionStatus) -> WorkflowExecution:
    """Return a deterministic workflow execution fixture."""

    return WorkflowExecution(
        workflow_id="demo_gaming_workflow",
        workflow_version=1,
        job_id="job_demo",
        status=status,
    )


def build_events() -> tuple[WorkflowEvent, ...]:
    """Return a minimal workflow event history."""

    return (
        WorkflowEvent(
            execution_id="workflow_execution_demo",
            event_type=WorkflowEventType.EXECUTION_CREATED,
        ),
    )


def test_gaming_workflow_input_trims_and_validates_strings() -> None:
    """Workflow input should trim meaningful strings and reject blanks."""

    workflow_input = GamingWorkflowInput(game="  Roblox  ", topic="  myths  ")

    assert workflow_input.game == "Roblox"
    assert workflow_input.topic == "myths"

    with pytest.raises(ValidationError):
        GamingWorkflowInput(game="   ")


def test_gaming_workflow_input_metadata_defaults_are_isolated() -> None:
    """Mutable metadata defaults should not be shared between input instances."""

    first = GamingWorkflowInput()
    second = GamingWorkflowInput()

    first.metadata["demo"] = True

    assert "demo" not in second.metadata


def test_gaming_workflow_result_validates_awaiting_approval_results() -> None:
    """Awaiting-approval results should require an approval request."""

    result = GamingWorkflowResult(
        execution=build_execution(WorkflowExecutionStatus.AWAITING_APPROVAL),
        opportunity=build_opportunity(),
        brief=build_brief(),
        script=build_script(),
        storyboard=build_storyboard(),
        generated_assets=[],
        narration=None,
        publishing_package=PublishingPackage(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            title="Demo package",
            description="Demo description",
            asset_ids=["asset_1"],
        ),
        approval_request=ApprovalRequest(
            execution_id="workflow_execution_demo",
            step_id="publishing_approval",
            requested_by="workflow_runtime",
        ),
        events=build_events(),
    )

    assert result.execution.status is WorkflowExecutionStatus.AWAITING_APPROVAL


def test_gaming_workflow_result_validates_completed_results() -> None:
    """Completed results should require a published post."""

    result = GamingWorkflowResult(
        execution=build_execution(WorkflowExecutionStatus.COMPLETED),
        opportunity=build_opportunity(),
        brief=build_brief(),
        script=build_script(),
        storyboard=build_storyboard(),
        generated_assets=[
            GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://assets/video.mp4"),
        ],
        narration=NarrationTrack(uri="mock://assets/narration.wav", duration_seconds=6.0),
        publishing_package=PublishingPackage(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            title="Demo package",
            description="Demo description",
            asset_ids=["asset_1"],
        ),
        published_post=PublishedPost(
            platform=ContentPlatform.YOUTUBE_SHORTS,
            external_id="mock_post_demo",
            url="mock://published/mock_post_demo",
        ),
        events=build_events(),
    )

    assert result.published_post is not None


def test_invalid_result_status_combinations_are_rejected() -> None:
    """Invalid status-dependent result combinations should fail validation."""

    with pytest.raises(ValidationError):
        GamingWorkflowResult(
            execution=build_execution(WorkflowExecutionStatus.COMPLETED),
            opportunity=build_opportunity(),
            brief=build_brief(),
            script=build_script(),
            storyboard=build_storyboard(),
            events=build_events(),
        )

    with pytest.raises(ValidationError):
        GamingWorkflowResult(
            execution=build_execution(WorkflowExecutionStatus.AWAITING_APPROVAL),
            opportunity=build_opportunity(),
            brief=build_brief(),
            script=build_script(),
            storyboard=build_storyboard(),
            published_post=PublishedPost(
                platform=ContentPlatform.YOUTUBE_SHORTS,
                external_id="mock_post_demo",
                url="mock://published/mock_post_demo",
            ),
            events=build_events(),
        )


def test_models_serialize_and_restore_predictably() -> None:
    """Workflow orchestration models should serialize and restore cleanly."""

    bundle = DemoAssetBundle(
        video=GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://assets/video.mp4"),
        thumbnail=GeneratedAsset(asset_type=AssetType.THUMBNAIL, uri="mock://assets/thumbnail.png"),
        narration=NarrationTrack(uri="mock://assets/narration.wav", duration_seconds=6.0),
    )
    payload = bundle.model_dump()
    restored = DemoAssetBundle.model_validate(payload)

    assert restored == bundle
