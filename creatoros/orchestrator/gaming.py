"""Deterministic gaming workflow orchestrator for the first executable demo."""

from __future__ import annotations

from creatoros.core import CreatorOSError, WorkflowError
from creatoros.domain import ContentJob, PublishingPackage
from creatoros.engines.demo import (
    DemoAssetEngine,
    DemoPublishingEngine,
    DemoResearchEngine,
    DemoScriptEngine,
    DemoScriptEngineInput,
    DemoStoryboardEngine,
    build_demo_content_brief,
)
from creatoros.engines.models import EngineExecutionContext
from creatoros.observability import get_logger
from creatoros.orchestrator.models import GamingWorkflowInput, GamingWorkflowResult
from creatoros.providers import ProviderRegistry
from creatoros.providers.mock import create_mock_provider_registry
from creatoros.workflows import WorkflowExecution, WorkflowExecutionStatus, WorkflowRuntime

WORKFLOW_NAME = "demo_gaming_workflow"
WORKFLOW_VERSION = 1
STEP_RESEARCH = "research"
STEP_SCRIPT = "script"
STEP_STORYBOARD = "storyboard"
STEP_ASSET = "asset"
STEP_PUBLISHING_APPROVAL = "publishing_approval"
STEP_PUBLISH = "publish"


class GamingWorkflowOrchestrator:
    """Coordinate the deterministic demo gaming workflow across focused engines."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.provider_registry = provider_registry or create_mock_provider_registry()
        self.logger = get_logger("orchestrator.gaming")
        self.research_engine = DemoResearchEngine(provider_registry=self.provider_registry)
        self.script_engine = DemoScriptEngine(provider_registry=self.provider_registry)
        self.storyboard_engine = DemoStoryboardEngine(provider_registry=self.provider_registry)
        self.asset_engine = DemoAssetEngine(provider_registry=self.provider_registry)
        self.publishing_engine = DemoPublishingEngine(provider_registry=self.provider_registry)

    async def run(
        self,
        workflow_input: GamingWorkflowInput,
    ) -> GamingWorkflowResult:
        """Execute the deterministic demo workflow and return a structured result."""

        job = ContentJob(
            workflow_name=WORKFLOW_NAME,
            platform=workflow_input.platform,
            metadata={"demo": True, **dict(workflow_input.metadata)},
        )
        execution = WorkflowExecution(
            workflow_id=WORKFLOW_NAME,
            workflow_version=WORKFLOW_VERSION,
            job_id=job.id,
            metadata={"demo": True},
        )
        runtime = WorkflowRuntime(execution)
        runtime.start()

        active_step_id: str | None = None

        try:
            active_step_id = STEP_RESEARCH
            runtime.record_step_started(active_step_id)
            opportunity = (
                await self.research_engine.run(
                    workflow_input,
                    context=self._build_engine_context(job_id=job.id, step_id=active_step_id),
                )
            ).data
            runtime.record_step_completed(active_step_id)

            active_step_id = STEP_SCRIPT
            runtime.record_step_started(active_step_id)
            script_input = DemoScriptEngineInput(
                opportunity=opportunity,
                platform=workflow_input.platform,
            )
            script = (
                await self.script_engine.run(
                    script_input,
                    context=self._build_engine_context(job_id=job.id, step_id=active_step_id),
                )
            ).data
            runtime.record_step_completed(active_step_id)

            active_step_id = STEP_STORYBOARD
            runtime.record_step_started(active_step_id)
            storyboard = (
                await self.storyboard_engine.run(
                    script,
                    context=self._build_engine_context(job_id=job.id, step_id=active_step_id),
                )
            ).data
            runtime.record_step_completed(active_step_id)

            active_step_id = STEP_ASSET
            runtime.record_step_started(active_step_id)
            asset_bundle = (
                await self.asset_engine.run(
                    storyboard,
                    context=self._build_engine_context(job_id=job.id, step_id=active_step_id),
                )
            ).data
            runtime.record_step_completed(active_step_id)

            brief = build_demo_content_brief(
                opportunity,
                platform=workflow_input.platform,
            )
            generated_assets = [asset_bundle.video, asset_bundle.thumbnail]
            publishing_package = PublishingPackage(
                platform=workflow_input.platform,
                title=script.title,
                description=f"Deterministic demo package for {workflow_input.game} about {workflow_input.topic}.",
                asset_ids=[asset.id for asset in generated_assets],
                metadata={
                    "demo": True,
                    "storyboard_id": storyboard.id,
                    "narration_id": asset_bundle.narration.id,
                },
            )

            approval_request = runtime.request_approval(
                step_id=STEP_PUBLISHING_APPROVAL,
                message="Awaiting local publishing approval for deterministic demo workflow.",
            )

            if not workflow_input.approve_publish:
                return GamingWorkflowResult(
                    execution=runtime.execution,
                    opportunity=opportunity,
                    brief=brief,
                    script=script,
                    storyboard=storyboard,
                    generated_assets=generated_assets,
                    narration=asset_bundle.narration,
                    publishing_package=publishing_package,
                    approval_request=approval_request,
                    events=runtime.events,
                    metadata={"demo": True},
                )

            runtime.approve(approval_request, decided_by="cli_user")

            active_step_id = STEP_PUBLISH
            runtime.record_step_started(active_step_id)
            published_post = (
                await self.publishing_engine.run(
                    publishing_package,
                    context=self._build_engine_context(job_id=job.id, step_id=active_step_id),
                )
            ).data
            runtime.record_step_completed(active_step_id)
            runtime.complete(message="Deterministic demo workflow completed.")

            return GamingWorkflowResult(
                execution=runtime.execution,
                opportunity=opportunity,
                brief=brief,
                script=script,
                storyboard=storyboard,
                generated_assets=generated_assets,
                narration=asset_bundle.narration,
                publishing_package=publishing_package,
                published_post=published_post,
                approval_request=approval_request,
                events=runtime.events,
                metadata={"demo": True},
            )
        except CreatorOSError:
            if active_step_id is not None and runtime.status is WorkflowExecutionStatus.RUNNING:
                runtime.record_step_failed(active_step_id)
            if runtime.status in {
                WorkflowExecutionStatus.RUNNING,
                WorkflowExecutionStatus.AWAITING_APPROVAL,
                WorkflowExecutionStatus.PAUSED,
            }:
                runtime.fail(message="Deterministic demo workflow failed.", step_id=active_step_id)
            raise
        except Exception as error:
            if active_step_id is not None and runtime.status is WorkflowExecutionStatus.RUNNING:
                runtime.record_step_failed(active_step_id)
            if runtime.status in {
                WorkflowExecutionStatus.RUNNING,
                WorkflowExecutionStatus.AWAITING_APPROVAL,
                WorkflowExecutionStatus.PAUSED,
            }:
                runtime.fail(message="Deterministic demo workflow failed.", step_id=active_step_id)
            raise WorkflowError(
                "deterministic demo gaming workflow failed",
                code="workflow_demo_failed",
                details={"step_id": active_step_id},
            ) from error

    def _build_engine_context(
        self,
        *,
        job_id: str,
        step_id: str,
    ) -> EngineExecutionContext:
        """Build a shared engine execution context for a workflow step."""

        return EngineExecutionContext(
            job_id=job_id,
            step_id=step_id,
            workflow_name=WORKFLOW_NAME,
            metadata={"demo": True},
        )


async def run_demo_gaming_workflow(
    workflow_input: GamingWorkflowInput,
    *,
    provider_registry: ProviderRegistry | None = None,
) -> GamingWorkflowResult:
    """Run the deterministic demo gaming workflow with the supplied registry."""

    orchestrator = GamingWorkflowOrchestrator(provider_registry=provider_registry)
    return await orchestrator.run(workflow_input)


__all__ = [
    "GamingWorkflowOrchestrator",
    "run_demo_gaming_workflow",
]
