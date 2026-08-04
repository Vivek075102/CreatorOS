"""Unit tests for deterministic demo agents."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from creatoros.agents import AgentExecutionContext
from creatoros.agents.demo import (
    DemoAssetAgent,
    DemoPublishingAgent,
    DemoResearchAgent,
    DemoScriptAgent,
    DemoStoryboardAgent,
)
from creatoros.core import CreatorOSValidationError
from creatoros.domain import (
    ContentBrief,
    ContentPlatform,
    PublishingPackage,
    Scene,
    Script,
    Storyboard,
)
from creatoros.orchestrator import GamingWorkflowInput
from creatoros.providers.mock import MockTrendProvider, create_mock_provider_registry
from creatoros.providers.registry import create_provider_registry


def build_context() -> AgentExecutionContext:
    """Return a reusable deterministic agent execution context."""

    return AgentExecutionContext(
        job_id="job_demo",
        step_id="step_demo",
        workflow_name="demo_gaming_workflow",
        engine_name="demo_engine",
    )


def test_research_agent_returns_content_opportunity() -> None:
    """The research agent should normalize mock trend data into a domain model."""

    agent = DemoResearchAgent(provider_registry=create_mock_provider_registry())

    result = asyncio.run(agent.run(GamingWorkflowInput(), context=build_context()))

    assert result.agent_name == "demo_research_agent"
    assert result.data.title == "Minecraft: Gaming Facts"
    assert result.data.game == "Minecraft"
    assert result.data.topic == "gaming facts"
    assert not isinstance(result.data, dict)


def test_research_agent_reflects_explicit_game_and_topic_inputs() -> None:
    """The research agent should build the opportunity from requested workflow input."""

    agent = DemoResearchAgent(provider_registry=create_mock_provider_registry())

    result = asyncio.run(
        agent.run(
            GamingWorkflowInput(game="Roblox", topic="funny myths"),
            context=build_context(),
        )
    )

    assert result.data.title == "Roblox: Funny Myths"
    assert result.data.game == "Roblox"
    assert result.data.topic == "funny myths"


def test_research_agent_raises_when_no_trend_records_are_returned() -> None:
    """Empty mock trend results should be rejected."""

    registry = create_provider_registry()
    registry.register(MockTrendProvider(results=[]))
    agent = DemoResearchAgent(provider_registry=registry)

    with pytest.raises(CreatorOSValidationError, match="no trend records"):
        asyncio.run(agent.run(GamingWorkflowInput(), context=build_context()))


def test_script_agent_returns_script() -> None:
    """The script agent should produce a deterministic script contract."""

    agent = DemoScriptAgent(provider_registry=create_mock_provider_registry())
    brief = ContentBrief(
        title="Minecraft hidden fact",
        audience="Minecraft players",
        platform="youtube_shorts",
        objective="Explain a quick hidden fact.",
        tone="energetic",
        hook_direction="Start with surprise",
        constraints=["Keep it short."],
        notes="Demo note.",
    )

    result = asyncio.run(agent.run(brief, context=build_context()))

    assert isinstance(result.data, Script)
    assert result.data.version == 1
    assert result.data.estimated_duration_seconds > 0


def test_script_agent_title_can_reflect_normalized_opportunity_title() -> None:
    """Script titles should preserve the normalized opportunity title."""

    agent = DemoScriptAgent(provider_registry=create_mock_provider_registry())
    brief = ContentBrief(
        title="Roblox: Funny Myths",
        audience="Roblox players",
        platform="youtube_shorts",
        objective="Explain a quick funny myth.",
        tone="energetic",
        hook_direction="Start with surprise",
        constraints=["Keep it short."],
        notes="Demo note.",
    )

    result = asyncio.run(agent.run(brief, context=build_context()))

    assert result.data.title == "Roblox: Funny Myths"


def test_storyboard_agent_creates_ordered_scenes() -> None:
    """The storyboard agent should create at least three sequential scenes."""

    agent = DemoStoryboardAgent(provider_registry=create_mock_provider_registry())
    script = Script(
        title="Speedrun myth",
        hook="Hook",
        body="Body",
        ending="Ending",
        call_to_action="CTA",
        estimated_duration_seconds=30,
        version=1,
    )

    result = asyncio.run(agent.run(script, context=build_context()))

    assert isinstance(result.data, Storyboard)
    assert len(result.data.scenes) >= 3
    assert [scene.scene_number for scene in result.data.scenes] == [1, 2, 3]


def test_asset_agent_returns_video_thumbnail_and_narration_contracts() -> None:
    """The asset agent should normalize all generated asset outputs."""

    agent = DemoAssetAgent(provider_registry=create_mock_provider_registry())
    storyboard = Storyboard(
        title="Demo storyboard",
        scenes=[
            Scene(
                scene_number=1,
                duration_seconds=10,
                narration="Hook scene",
                visual_description="Visual hook",
            )
        ],
        notes="Demo notes",
    )

    result = asyncio.run(agent.run(storyboard, context=build_context()))

    assert result.data.video.uri.startswith("mock://")
    assert result.data.thumbnail.asset_type.value == "thumbnail"
    assert result.data.narration.uri.startswith("mock://")


def test_publishing_agent_returns_published_post() -> None:
    """The publishing agent should publish through the mock provider contract."""

    agent = DemoPublishingAgent(provider_registry=create_mock_provider_registry())
    package = PublishingPackage(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        title="Demo publish",
        description="Deterministic demo package.",
        asset_ids=["asset_video", "asset_thumbnail"],
    )

    result = asyncio.run(agent.run(package, context=build_context()))

    assert result.data.external_id.startswith("mock_post_")
    assert result.data.url.startswith("mock://published/")


def test_agents_use_the_supplied_registry() -> None:
    """Agents should keep the explicitly supplied registry instead of global state."""

    registry = create_mock_provider_registry()
    agent = DemoResearchAgent(provider_registry=registry)

    assert agent.provider_registry is registry


def test_demo_agents_module_does_not_import_engines() -> None:
    """The demo agents module should not depend on engine modules."""

    module_source = Path("creatoros/agents/demo.py").read_text(encoding="utf-8")

    assert "creatoros.engines" not in module_source
