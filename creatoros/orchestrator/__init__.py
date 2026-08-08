"""Workflow orchestration exports for CreatorOS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from creatoros.orchestrator.models import (
    DemoAssetBundle,
    GamingContentMediaPlanSet,
    GamingContentPipelineRequest,
    GamingContentPipelineResult,
    GamingContentReviewSet,
    GamingWorkflowInput,
    GamingWorkflowResult,
)

if TYPE_CHECKING:
    from creatoros.orchestrator.gaming import GamingWorkflowOrchestrator


def __getattr__(name: str) -> Any:
    """Lazily expose orchestrator runtime objects without import cycles."""

    if name in {
        "GamingContentPipeline",
        "GamingWorkflowOrchestrator",
        "build_gaming_content_pipeline",
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

        exports = {
            "GamingContentPipeline": GamingContentPipeline,
            "GamingWorkflowOrchestrator": GamingWorkflowOrchestrator,
            "build_gaming_content_pipeline": build_gaming_content_pipeline,
            "run_demo_gaming_workflow": run_demo_gaming_workflow,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DemoAssetBundle",
    "GamingContentMediaPlanSet",
    "GamingContentPipeline",
    "GamingContentPipelineRequest",
    "GamingContentPipelineResult",
    "GamingContentReviewSet",
    "GamingWorkflowInput",
    "GamingWorkflowOrchestrator",
    "GamingWorkflowResult",
    "build_gaming_content_pipeline",
    "run_demo_gaming_workflow",
]
