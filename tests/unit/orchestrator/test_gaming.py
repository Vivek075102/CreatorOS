"""Unit tests for the deterministic gaming workflow orchestrator."""

from __future__ import annotations

import asyncio

import pytest

from creatoros.core import CreatorOSValidationError, WorkflowError
from creatoros.domain import ContentPlatform
from creatoros.orchestrator import GamingWorkflowInput
from creatoros.orchestrator.gaming import (
    STEP_ASSET,
    STEP_PUBLISH,
    STEP_PUBLISHING_APPROVAL,
    STEP_RESEARCH,
    STEP_SCRIPT,
    STEP_STORYBOARD,
    GamingWorkflowOrchestrator,
)
from creatoros.providers import get_provider_registry
from creatoros.providers.mock import create_mock_provider_registry
from creatoros.workflows import WorkflowEventType, WorkflowExecutionStatus


@pytest.fixture(autouse=True)
def clear_registry_cache() -> None:
    """Reset the cached application registry between tests."""

    get_provider_registry.cache_clear()


def test_full_non_approved_execution_reaches_awaiting_approval() -> None:
    """The non-approved demo workflow should stop at the approval gate."""

    result = asyncio.run(
        GamingWorkflowOrchestrator().run(
            GamingWorkflowInput(
                game="Minecraft",
                topic="hidden facts",
                platform=ContentPlatform.YOUTUBE_SHORTS,
            )
        )
    )

    assert result.execution.status is WorkflowExecutionStatus.AWAITING_APPROVAL
    assert result.approval_request is not None
    assert result.published_post is None
    assert result.narration is not None
    assert len(result.generated_assets) == 2
    assert result.opportunity.title == "Minecraft: Hidden Facts"
    assert result.script.title == "Minecraft: Hidden Facts"


def test_approved_execution_reaches_completed_and_returns_published_post() -> None:
    """Approved demo execution should publish through the mock provider."""

    result = asyncio.run(
        GamingWorkflowOrchestrator().run(
            GamingWorkflowInput(approve_publish=True)
        )
    )

    assert result.execution.status is WorkflowExecutionStatus.COMPLETED
    assert result.published_post is not None
    assert result.published_post.url.startswith("mock://published/")


def test_explicit_roblox_input_flows_through_opportunity_and_script_title() -> None:
    """Explicit workflow input should drive the opportunity and script title."""

    result = asyncio.run(
        GamingWorkflowOrchestrator().run(
            GamingWorkflowInput(
                game="Roblox",
                topic="funny myths",
                approve_publish=True,
            )
        )
    )

    assert result.opportunity.title == "Roblox: Funny Myths"
    assert result.opportunity.game == "Roblox"
    assert result.opportunity.topic == "funny myths"
    assert result.script.title == "Roblox: Funny Myths"


def test_all_expected_workflow_steps_create_events_in_order() -> None:
    """The workflow runtime should preserve ordered events for every step."""

    result = asyncio.run(GamingWorkflowOrchestrator().run(GamingWorkflowInput(approve_publish=True)))
    step_events = [
        (event.event_type, event.step_id)
        for event in result.events
        if event.step_id is not None
    ]

    assert (WorkflowEventType.STEP_STARTED, STEP_RESEARCH) in step_events
    assert (WorkflowEventType.STEP_COMPLETED, STEP_RESEARCH) in step_events
    assert (WorkflowEventType.STEP_STARTED, STEP_SCRIPT) in step_events
    assert (WorkflowEventType.STEP_COMPLETED, STEP_SCRIPT) in step_events
    assert (WorkflowEventType.STEP_STARTED, STEP_STORYBOARD) in step_events
    assert (WorkflowEventType.STEP_COMPLETED, STEP_STORYBOARD) in step_events
    assert (WorkflowEventType.STEP_STARTED, STEP_ASSET) in step_events
    assert (WorkflowEventType.STEP_COMPLETED, STEP_ASSET) in step_events
    assert (WorkflowEventType.APPROVAL_REQUESTED, STEP_PUBLISHING_APPROVAL) in step_events
    assert (WorkflowEventType.STEP_STARTED, STEP_PUBLISH) in step_events
    assert (WorkflowEventType.STEP_COMPLETED, STEP_PUBLISH) in step_events


def test_same_provider_registry_is_shared_across_engines() -> None:
    """The orchestrator should inject one shared registry into all engines."""

    registry = create_mock_provider_registry()
    orchestrator = GamingWorkflowOrchestrator(provider_registry=registry)

    assert orchestrator.research_engine.provider_registry is registry
    assert orchestrator.script_engine.provider_registry is registry
    assert orchestrator.storyboard_engine.provider_registry is registry
    assert orchestrator.asset_engine.provider_registry is registry
    assert orchestrator.publishing_engine.provider_registry is registry


def test_publishing_package_contains_expected_asset_ids() -> None:
    """The publishing package should reference the generated video and thumbnail."""

    result = asyncio.run(GamingWorkflowOrchestrator().run(GamingWorkflowInput()))

    assert result.publishing_package is not None
    assert result.publishing_package.asset_ids == [asset.id for asset in result.generated_assets]


def test_creatoros_errors_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expected CreatorOS errors should be re-raised unchanged."""

    orchestrator = GamingWorkflowOrchestrator(provider_registry=create_mock_provider_registry())

    async def fail_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise CreatorOSValidationError("demo failure")

    monkeypatch.setattr(orchestrator.research_engine, "run", fail_run)

    with pytest.raises(CreatorOSValidationError, match="demo failure"):
        asyncio.run(orchestrator.run(GamingWorkflowInput()))


def test_unexpected_errors_are_wrapped_and_preserve_the_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected exceptions should be wrapped as WorkflowError with chained cause."""

    orchestrator = GamingWorkflowOrchestrator(provider_registry=create_mock_provider_registry())

    async def fail_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr(orchestrator.asset_engine, "run", fail_run)

    with pytest.raises(WorkflowError, match="deterministic demo gaming workflow failed") as exc_info:
        asyncio.run(orchestrator.run(GamingWorkflowInput()))

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_cached_application_registry_is_not_mutated() -> None:
    """Creating a default orchestrator should not populate the cached global registry."""

    cached_registry = get_provider_registry()

    assert cached_registry.list_providers() == ()

    asyncio.run(GamingWorkflowOrchestrator().run(GamingWorkflowInput()))

    assert cached_registry.list_providers() == ()
