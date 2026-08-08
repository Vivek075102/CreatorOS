"""Tests for builtin storyboard prompt rendering helpers."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.prompts import (
    create_builtin_prompt_registry,
    render_storyboard_scene_breakdown,
    render_storyboard_timing_review,
    render_storyboard_visual_direction,
)


def test_storyboard_scene_breakdown_renders_successfully() -> None:
    """The scene breakdown helper should render the builtin storyboard prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_storyboard_scene_breakdown(
        registry,
        title="Roblox: Funny Myths",
        game="Roblox",
        platform="youtube_shorts",
        hook="You probably still believe this Roblox myth.",
        body="Players often repeat three myths about game mechanics.",
        ending="Now you know which claims deserve checking.",
        call_to_action="Which myth should we test next?",
        target_duration_seconds=30,
    )

    assert rendered.prompt_name == "storyboard_scene_breakdown"
    assert rendered.prompt_version == 1
    assert "Roblox: Funny Myths" in rendered.text
    assert "Roblox" in rendered.text
    assert "You probably still believe this Roblox myth." in rendered.text
    assert "Players often repeat three myths about game mechanics." in rendered.text
    assert "30" in rendered.text


def test_storyboard_visual_direction_renders_successfully() -> None:
    """The visual direction helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_storyboard_visual_direction(
        registry,
        game="Minecraft",
        scene_number=2,
        scene_purpose="Develop the main idea clearly",
        script_beat="Explain the main myth or fact concisely",
        visual_summary="Gameplay footage with concise supporting overlays",
        platform="youtube_shorts",
        duration_seconds=8.5,
    )

    assert rendered.prompt_name == "storyboard_visual_direction"
    assert "2" in rendered.text
    assert "8.5" in rendered.text


def test_storyboard_timing_review_renders_successfully() -> None:
    """The timing review helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_storyboard_timing_review(
        registry,
        title="Minecraft: Gaming Facts",
        scene_summary="Scene 1: 5 seconds hook. Scene 2: 12 seconds explanation. Scene 3: 8 seconds example. Scene 4: 5 seconds ending.",
        target_duration_seconds=30,
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "storyboard_timing_review"
    assert "Scene 1: 5 seconds hook." in rendered.text


def test_storyboard_helpers_do_not_mutate_registry_definitions() -> None:
    """Storyboard rendering helpers should not mutate stored prompt definitions."""

    registry = create_builtin_prompt_registry()
    before = registry.get("storyboard_scene_breakdown").model_dump(mode="python")

    render_storyboard_scene_breakdown(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        platform="youtube_shorts",
        hook="Here is the hook.",
        body="Here is the body.",
        ending="Here is the ending.",
        call_to_action="What should we test next?",
        target_duration_seconds=30,
    )

    after = registry.get("storyboard_scene_breakdown").model_dump(mode="python")
    assert after == before


def test_storyboard_helpers_do_not_call_providers() -> None:
    """Storyboard rendering helpers should work without any provider interaction."""

    registry = create_builtin_prompt_registry()

    rendered = render_storyboard_timing_review(
        registry,
        title="Roblox: Funny Myths",
        scene_summary="Scene 1: 6 seconds. Scene 2: 12 seconds. Scene 3: 12 seconds.",
        target_duration_seconds=30,
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "storyboard_timing_review"


def test_missing_required_storyboard_values_are_rejected() -> None:
    """Storyboard rendering helpers should reject missing required values safely."""

    registry = create_builtin_prompt_registry()

    with pytest.raises(CreatorOSValidationError):
        render_storyboard_visual_direction(
            registry,
            game="Minecraft",
            scene_number=2,
            scene_purpose="",
            script_beat="Explain the main myth or fact concisely",
            visual_summary="Gameplay footage with concise supporting overlays",
            platform="youtube_shorts",
            duration_seconds=8.5,
        )
