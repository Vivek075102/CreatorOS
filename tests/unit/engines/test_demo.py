"""Unit tests for deterministic demo engines."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from creatoros.core import AgentError
from creatoros.domain import ContentPlatform, PublishingPackage, Scene, Script, Storyboard
from creatoros.engines.demo import (
    DemoAssetEngine,
    DemoPublishingEngine,
    DemoResearchEngine,
    DemoScriptEngine,
    DemoScriptEngineInput,
    DemoStoryboardEngine,
)
from creatoros.engines.models import EngineExecutionContext
from creatoros.orchestrator import GamingWorkflowInput
from creatoros.providers.mock import create_mock_provider_registry


def build_context(step_id: str) -> EngineExecutionContext:
    """Return a deterministic engine execution context."""

    return EngineExecutionContext(
        job_id="job_demo",
        step_id=step_id,
        workflow_name="demo_gaming_workflow",
    )


def test_research_engine_returns_content_opportunity() -> None:
    """The research engine should return a normalized content opportunity."""

    engine = DemoResearchEngine(provider_registry=create_mock_provider_registry())

    result = asyncio.run(engine.run(GamingWorkflowInput(), context=build_context("research")))

    assert result.engine_name == "demo_research_engine"
    assert result.data.title == "Minecraft: Gaming Facts"


def test_script_engine_returns_script() -> None:
    """The script engine should create a brief and return a script."""

    registry = create_mock_provider_registry()
    opportunity = asyncio.run(
        DemoResearchEngine(provider_registry=registry).run(
            GamingWorkflowInput(),
            context=build_context("research"),
        )
    ).data
    engine = DemoScriptEngine(provider_registry=registry)

    result = asyncio.run(
        engine.run(
            DemoScriptEngineInput(
                opportunity=opportunity,
                platform=ContentPlatform.YOUTUBE_SHORTS,
            ),
            context=build_context("script"),
        )
    )

    assert result.data.title == opportunity.title


def test_storyboard_engine_returns_storyboard() -> None:
    """The storyboard engine should return a storyboard model."""

    engine = DemoStoryboardEngine(provider_registry=create_mock_provider_registry())
    script = Script(
        title="Myth",
        hook="Hook",
        body="Body",
        ending="Ending",
        call_to_action="CTA",
        estimated_duration_seconds=30,
        version=1,
    )

    result = asyncio.run(engine.run(script, context=build_context("storyboard")))

    assert len(result.data.scenes) >= 3


def test_asset_engine_returns_demo_asset_bundle() -> None:
    """The asset engine should return normalized asset contracts."""

    engine = DemoAssetEngine(provider_registry=create_mock_provider_registry())
    storyboard = Storyboard(
        title="Storyboard",
        scenes=[
            Scene(
                scene_number=1,
                duration_seconds=10,
                narration="Narration",
                visual_description="Visual",
            )
        ],
        notes="Notes",
    )

    result = asyncio.run(engine.run(storyboard, context=build_context("asset")))

    assert result.data.video.uri.startswith("mock://")
    assert result.data.thumbnail.uri.startswith("mock://")


def test_publishing_engine_returns_published_post() -> None:
    """The publishing engine should return a published post contract."""

    engine = DemoPublishingEngine(provider_registry=create_mock_provider_registry())
    package = PublishingPackage(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        title="Publish demo",
        description="Description",
        asset_ids=["asset_video", "asset_thumbnail"],
    )

    result = asyncio.run(engine.run(package, context=build_context("publish")))

    assert result.data.url.startswith("mock://published/")


def test_engines_use_the_supplied_shared_registry() -> None:
    """Every demo engine should preserve the injected shared registry."""

    registry = create_mock_provider_registry()

    engines = [
        DemoResearchEngine(provider_registry=registry),
        DemoScriptEngine(provider_registry=registry),
        DemoStoryboardEngine(provider_registry=registry),
        DemoAssetEngine(provider_registry=registry),
        DemoPublishingEngine(provider_registry=registry),
    ]

    assert all(engine.provider_registry is registry for engine in engines)


def test_engine_passes_context_to_its_agent() -> None:
    """Engine-derived agent context should preserve identifiers and engine name."""

    engine = DemoResearchEngine(provider_registry=create_mock_provider_registry())
    agent_context = engine._build_agent_context(build_context("research"))

    assert agent_context.job_id == "job_demo"
    assert agent_context.step_id == "research"
    assert agent_context.workflow_name == "demo_gaming_workflow"
    assert agent_context.engine_name == engine.name


def test_provider_or_agent_failures_preserve_creatoros_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent lifecycle failures should surface as typed CreatorOS errors."""

    engine = DemoResearchEngine(provider_registry=create_mock_provider_registry())

    async def fail_execute(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(engine.agent, "execute", fail_execute)

    with pytest.raises(AgentError, match="demo_research_agent agent execution failed"):
        asyncio.run(engine.run(GamingWorkflowInput(), context=build_context("research")))


def test_demo_engines_module_does_not_coordinate_other_engines() -> None:
    """The demo engines module should not construct cross-engine calls."""

    module_source = Path("creatoros/engines/demo.py").read_text(encoding="utf-8")

    assert ".run(" not in module_source.split("class DemoResearchEngine", 1)[0]
