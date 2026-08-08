"""Tests for builtin review prompt rendering helpers."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.prompts import (
    create_builtin_prompt_registry,
    render_gaming_evidence_consistency_review,
    render_gaming_publication_readiness_review,
    render_gaming_script_quality_review,
    render_gaming_storyboard_quality_review,
)


def test_gaming_script_quality_review_renders_successfully() -> None:
    """The script quality review helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_script_quality_review(
        registry,
        title="Roblox: Funny Myths",
        game="Roblox",
        topic="funny myths",
        angle="Test three popular myths",
        source_summary="Supplied summary discusses recurring myths about Roblox game mechanics.",
        script_text="You probably still believe this Roblox myth, so let's check the claim carefully.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    assert rendered.prompt_name == "gaming_script_quality_review"
    assert "Roblox: Funny Myths" in rendered.text
    assert "30" in rendered.text


def test_gaming_evidence_consistency_review_renders_successfully() -> None:
    """The evidence consistency review helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_evidence_consistency_review(
        registry,
        game="Minecraft",
        source_summary="Supplied summary covers one specific gameplay claim.",
        research_notes="Research notes say the claim is repeated often but should be framed cautiously.",
        content_text="This claim is definitely true in every match.",
        content_stage="script_draft",
    )

    assert rendered.prompt_name == "gaming_evidence_consistency_review"
    assert "script_draft" in rendered.text
    assert "Minecraft" in rendered.text


def test_gaming_storyboard_quality_review_renders_successfully() -> None:
    """The storyboard quality review helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_storyboard_quality_review(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        script_text="Hook first, explanation next, conclusion last.",
        storyboard_text="Scene 1 hooks the viewer. Scene 2 explains the main point. Scene 3 closes clearly.",
        platform="youtube_shorts",
        target_duration_seconds=35,
    )

    assert rendered.prompt_name == "gaming_storyboard_quality_review"
    assert "35" in rendered.text


def test_gaming_publication_readiness_review_renders_successfully() -> None:
    """The publication-readiness review helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_publication_readiness_review(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        script_text="You probably missed this gaming detail.",
        storyboard_summary="Storyboard summary aligns to the script.",
        thumbnail_summary="Thumbnail summary focuses on one clear gameplay visual.",
        narration_summary="Narration summary keeps the delivery concise.",
        evidence_review="Evidence review says one claim should stay cautious.",
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_publication_readiness_review"
    assert "ready_for_human_review" in rendered.text


def test_review_helpers_resolve_latest_active_version() -> None:
    """Review helpers should resolve the latest active prompt version by name."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_script_quality_review(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        topic="gaming facts",
        angle="Explain one clear fact",
        source_summary="Supplied evidence summary only.",
        script_text="You probably missed this gaming detail.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    assert rendered.prompt_version == 1


def test_review_helpers_do_not_mutate_registry_definitions() -> None:
    """Review rendering helpers should not mutate stored prompt definitions."""

    registry = create_builtin_prompt_registry()
    before = registry.get("gaming_script_quality_review").model_dump(mode="python")

    render_gaming_script_quality_review(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        topic="gaming facts",
        angle="Explain one clear fact",
        source_summary="Supplied evidence summary only.",
        script_text="You probably missed this gaming detail.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    after = registry.get("gaming_script_quality_review").model_dump(mode="python")
    assert after == before


def test_review_helpers_do_not_mutate_registry_state() -> None:
    """Review helpers should not alter registry prompt listings."""

    registry = create_builtin_prompt_registry()
    before = registry.list_prompts()

    render_gaming_publication_readiness_review(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        script_text="You probably missed this gaming detail.",
        storyboard_summary="Storyboard summary aligns to the script.",
        thumbnail_summary="Thumbnail summary focuses on one clear gameplay visual.",
        narration_summary="Narration summary keeps the delivery concise.",
        evidence_review="Evidence review says one claim should stay cautious.",
        platform="youtube_shorts",
    )

    after = registry.list_prompts()
    assert after == before


def test_review_helpers_do_not_call_providers() -> None:
    """Review rendering helpers should work without any provider interaction."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_evidence_consistency_review(
        registry,
        game="Roblox",
        source_summary="Supplied summary only.",
        research_notes="Supplied notes only.",
        content_text="Generated text under review.",
        content_stage="script_draft",
    )

    assert rendered.prompt_name == "gaming_evidence_consistency_review"


def test_missing_required_review_values_fail_safely() -> None:
    """Review rendering helpers should reject missing required values safely."""

    registry = create_builtin_prompt_registry()

    with pytest.raises(CreatorOSValidationError):
        render_gaming_storyboard_quality_review(
            registry,
            title="Minecraft: Gaming Facts",
            game="Minecraft",
            script_text="Hook first, explanation next, conclusion last.",
            storyboard_text="",
            platform="youtube_shorts",
            target_duration_seconds=30,
        )
