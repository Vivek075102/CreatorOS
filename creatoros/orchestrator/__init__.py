"""Workflow orchestration exports for CreatorOS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from creatoros.orchestrator.models import (
    ApprovedMediaExecutionRequest,
    DemoAssetBundle,
    GamingContentMediaPlanSet,
    GamingContentPipelineRequest,
    GamingContentPipelineResult,
    GamingContentReviewSet,
    GamingWorkflowInput,
    GamingWorkflowResult,
    HumanApproval,
    MediaExecutionResult,
)

if TYPE_CHECKING:
    from creatoros.orchestrator.gaming import GamingWorkflowOrchestrator


def __getattr__(name: str) -> Any:
    """Lazily expose orchestrator runtime objects without import cycles."""

    if name in {
        "GamingContentPipeline",
        "MediaExecutionPipeline",
        "GamingWorkflowOrchestrator",
        "build_gaming_content_pipeline",
        "create_media_execution_pipeline",
        "run_demo_gaming_workflow",
    }:
        from creatoros.orchestrator.content_pipeline import (
            GamingContentPipeline,
            build_gaming_content_pipeline,
        )
        from creatoros.orchestrator.gaming import (
            GamingWorkflowOrchestrator,
            run_demo_gaming_workflow,
        )
        from creatoros.orchestrator.media_pipeline import (
            MediaExecutionPipeline,
            create_media_execution_pipeline,
        )

        exports = {
            "GamingContentPipeline": GamingContentPipeline,
            "MediaExecutionPipeline": MediaExecutionPipeline,
            "GamingWorkflowOrchestrator": GamingWorkflowOrchestrator,
            "build_gaming_content_pipeline": build_gaming_content_pipeline,
            "create_media_execution_pipeline": create_media_execution_pipeline,
            "run_demo_gaming_workflow": run_demo_gaming_workflow,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ApprovedMediaExecutionRequest",
    "DemoAssetBundle",
    "GamingContentMediaPlanSet",
    "GamingContentPipeline",
    "GamingContentPipelineRequest",
    "GamingContentPipelineResult",
    "GamingContentReviewSet",
    "GamingWorkflowInput",
    "GamingWorkflowOrchestrator",
    "GamingWorkflowResult",
    "HumanApproval",
    "MediaExecutionPipeline",
    "MediaExecutionResult",
    "build_gaming_content_pipeline",
    "create_media_execution_pipeline",
    "run_demo_gaming_workflow",
]
