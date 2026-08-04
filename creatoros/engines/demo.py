"""Demo engines for the first executable CreatorOS gaming workflow."""

from __future__ import annotations

from creatoros.agents import AgentExecutionContext
from creatoros.agents.demo import (
    DemoAssetAgent,
    DemoPublishingAgent,
    DemoResearchAgent,
    DemoScriptAgent,
    DemoStoryboardAgent,
)
from creatoros.domain import (
    ContentBrief,
    ContentOpportunity,
    ContentPlatform,
    CreatorOSModel,
    PublishedPost,
    PublishingPackage,
    Script,
    Storyboard,
)
from creatoros.engines import BaseEngine, EngineExecutionContext
from creatoros.orchestrator.models import DemoAssetBundle, GamingWorkflowInput
from creatoros.providers import ProviderRegistry


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value

class DemoScriptEngineInput(CreatorOSModel):
    """Typed input for the demo script engine."""

    opportunity: ContentOpportunity
    platform: ContentPlatform


def build_demo_content_brief(
    opportunity: ContentOpportunity,
    *,
    platform: ContentPlatform,
) -> ContentBrief:
    """Build the deterministic content brief for the demo script workflow."""

    return ContentBrief(
        title=opportunity.title,
        audience=f"{opportunity.game} players",
        platform=platform,
        objective=f"Explain a fast, clear insight about {opportunity.topic}.",
        tone="clear and energetic",
        hook_direction=f"Start with a surprising {opportunity.game} fact",
        constraints=[
            "Keep the script concise.",
            f"Target {platform.value}.",
        ],
        notes=opportunity.reasoning,
    )


class DemoResearchEngine(BaseEngine[GamingWorkflowInput, ContentOpportunity]):
    """Run demo trend research through a focused research agent."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        super().__init__(provider_registry=provider_registry)
        self.agent = DemoResearchAgent(provider_registry=self.provider_registry)

    @property
    def name(self) -> str:
        return "demo_research_engine"

    async def execute(
        self,
        input_data: GamingWorkflowInput,
        *,
        context: EngineExecutionContext,
    ) -> ContentOpportunity:
        agent_result = await self.agent.run(
            input_data,
            context=self._build_agent_context(context),
        )
        return agent_result.data

    def _build_agent_context(self, context: EngineExecutionContext) -> AgentExecutionContext:
        """Create the derived agent execution context for this engine run."""

        return AgentExecutionContext(
            job_id=context.job_id,
            step_id=context.step_id,
            workflow_name=context.workflow_name,
            engine_name=self.name,
            metadata=dict(context.metadata),
        )


class DemoScriptEngine(BaseEngine[DemoScriptEngineInput, Script]):
    """Build a content brief and generate a deterministic demo script."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        super().__init__(provider_registry=provider_registry)
        self.agent = DemoScriptAgent(provider_registry=self.provider_registry)

    @property
    def name(self) -> str:
        return "demo_script_engine"

    async def execute(
        self,
        input_data: DemoScriptEngineInput,
        *,
        context: EngineExecutionContext,
    ) -> Script:
        brief = build_demo_content_brief(
            input_data.opportunity,
            platform=input_data.platform,
        )
        agent_result = await self.agent.run(
            brief,
            context=self._build_agent_context(context),
        )
        return agent_result.data

    def _build_agent_context(self, context: EngineExecutionContext) -> AgentExecutionContext:
        """Create the derived agent execution context for this engine run."""

        return AgentExecutionContext(
            job_id=context.job_id,
            step_id=context.step_id,
            workflow_name=context.workflow_name,
            engine_name=self.name,
            metadata=dict(context.metadata),
        )


class DemoStoryboardEngine(BaseEngine[Script, Storyboard]):
    """Convert a script into a deterministic storyboard."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        super().__init__(provider_registry=provider_registry)
        self.agent = DemoStoryboardAgent(provider_registry=self.provider_registry)

    @property
    def name(self) -> str:
        return "demo_storyboard_engine"

    async def execute(
        self,
        input_data: Script,
        *,
        context: EngineExecutionContext,
    ) -> Storyboard:
        agent_result = await self.agent.run(
            input_data,
            context=self._build_agent_context(context),
        )
        return agent_result.data

    def _build_agent_context(self, context: EngineExecutionContext) -> AgentExecutionContext:
        """Create the derived agent execution context for this engine run."""

        return AgentExecutionContext(
            job_id=context.job_id,
            step_id=context.step_id,
            workflow_name=context.workflow_name,
            engine_name=self.name,
            metadata=dict(context.metadata),
        )


class DemoAssetEngine(BaseEngine[Storyboard, DemoAssetBundle]):
    """Generate a deterministic mock asset bundle from a storyboard."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        super().__init__(provider_registry=provider_registry)
        self.agent = DemoAssetAgent(provider_registry=self.provider_registry)

    @property
    def name(self) -> str:
        return "demo_asset_engine"

    async def execute(
        self,
        input_data: Storyboard,
        *,
        context: EngineExecutionContext,
    ) -> DemoAssetBundle:
        agent_result = await self.agent.run(
            input_data,
            context=self._build_agent_context(context),
        )
        return agent_result.data

    def _build_agent_context(self, context: EngineExecutionContext) -> AgentExecutionContext:
        """Create the derived agent execution context for this engine run."""

        return AgentExecutionContext(
            job_id=context.job_id,
            step_id=context.step_id,
            workflow_name=context.workflow_name,
            engine_name=self.name,
            metadata=dict(context.metadata),
        )


class DemoPublishingEngine(BaseEngine[PublishingPackage, PublishedPost]):
    """Publish a deterministic mock package through the demo publishing agent."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        super().__init__(provider_registry=provider_registry)
        self.agent = DemoPublishingAgent(provider_registry=self.provider_registry)

    @property
    def name(self) -> str:
        return "demo_publishing_engine"

    async def execute(
        self,
        input_data: PublishingPackage,
        *,
        context: EngineExecutionContext,
    ) -> PublishedPost:
        agent_result = await self.agent.run(
            input_data,
            context=self._build_agent_context(context),
        )
        return agent_result.data

    def _build_agent_context(self, context: EngineExecutionContext) -> AgentExecutionContext:
        """Create the derived agent execution context for this engine run."""

        return AgentExecutionContext(
            job_id=context.job_id,
            step_id=context.step_id,
            workflow_name=context.workflow_name,
            engine_name=self.name,
            metadata=dict(context.metadata),
        )


__all__ = [
    "DemoAssetEngine",
    "DemoPublishingEngine",
    "DemoResearchEngine",
    "DemoScriptEngine",
    "DemoScriptEngineInput",
    "DemoStoryboardEngine",
    "build_demo_content_brief",
]
