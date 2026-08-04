"""Workflow orchestration exports for CreatorOS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from creatoros.orchestrator.models import DemoAssetBundle, GamingWorkflowInput, GamingWorkflowResult

if TYPE_CHECKING:
    from creatoros.orchestrator.gaming import GamingWorkflowOrchestrator


def __getattr__(name: str) -> Any:
    """Lazily expose orchestrator runtime objects without import cycles."""

    if name in {"GamingWorkflowOrchestrator", "run_demo_gaming_workflow"}:
        from creatoros.orchestrator.gaming import (
            GamingWorkflowOrchestrator,
            run_demo_gaming_workflow,
        )

        exports = {
            "GamingWorkflowOrchestrator": GamingWorkflowOrchestrator,
            "run_demo_gaming_workflow": run_demo_gaming_workflow,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DemoAssetBundle",
    "GamingWorkflowInput",
    "GamingWorkflowOrchestrator",
    "GamingWorkflowResult",
    "run_demo_gaming_workflow",
]
