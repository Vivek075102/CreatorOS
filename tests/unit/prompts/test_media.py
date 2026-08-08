"""Tests for builtin media prompt rendering helpers."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.prompts import (
    create_builtin_prompt_registry,
    render_gaming_narration_direction,
    render_gaming_scene_motion_prompt,
    render_gaming_scene_visual_prompt,
    render_gaming_thumbnail_concept,
)


def test_gaming_thumbnail_concept_renders_successfully() -> None:
    """The thumbnail concept helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_thumbnail_concept(
        registry,
        title="Roblox: Funny Myths",
        game="Roblox",
        topic="funny myths",
        angle="Test three popular myths",
        hook="You probably still believe this Roblox myth.",
        platform="youtube_shorts",
        visual_context="Clean gameplay-inspired context with one clear focal subject.",
    )

    assert rendered.prompt_name == "gaming_thumbnail_concept"
    assert "Roblox: Funny Myths" in rendered.text
    assert "Roblox" in rendered.text


def test_gaming_scene_visual_prompt_renders_successfully() -> None:
    """The scene visual helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_scene_visual_prompt(
        registry,
        game="Minecraft",
        scene_number=2,
        scene_purpose="Develop the main idea clearly",
        script_beat="Explain the main myth or fact concisely",
        visual_direction="Focus on one clear gameplay-related visual moment with readable overlays.",
        on_screen_text="Myth or Fact?",
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_scene_visual_prompt"
    assert "2" in rendered.text


def test_gaming_scene_motion_prompt_renders_successfully() -> None:
    """The scene motion helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_scene_motion_prompt(
        registry,
        game="Minecraft",
        scene_number=2,
        scene_purpose="Develop the main idea clearly",
        visual_summary="Gameplay footage with concise supporting overlays",
        script_beat="Explain the main myth or fact concisely",
        duration_seconds=8.5,
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_scene_motion_prompt"
    assert "2" in rendered.text
    assert "8.5" in rendered.text


def test_gaming_narration_direction_renders_successfully() -> None:
    """The narration direction helper should render the builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_narration_direction(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        script_text="You probably missed this gaming detail, and here is the quick explanation.",
        target_duration_seconds=30,
        tone="natural and concise",
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_narration_direction"
    assert "You probably missed this gaming detail" in rendered.text


def test_media_helpers_do_not_mutate_registry_definitions() -> None:
    """Media rendering helpers should not mutate stored prompt definitions."""

    registry = create_builtin_prompt_registry()
    before = registry.get("gaming_thumbnail_concept").model_dump(mode="python")

    render_gaming_thumbnail_concept(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        topic="gaming facts",
        angle="Explain one clear fact",
        hook="You probably missed this gaming detail.",
        platform="youtube_shorts",
        visual_context="Clean gameplay-inspired context with one clear focal subject.",
    )

    after = registry.get("gaming_thumbnail_concept").model_dump(mode="python")
    assert after == before


def test_media_helpers_do_not_call_providers() -> None:
    """Media rendering helpers should work without any provider interaction."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_narration_direction(
        registry,
        title="Roblox: Funny Myths",
        game="Roblox",
        script_text="You probably still believe this Roblox myth.",
        target_duration_seconds=30,
        tone="natural and concise",
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_narration_direction"


def test_missing_required_media_values_fail_safely() -> None:
    """Media rendering helpers should reject missing required values safely."""

    registry = create_builtin_prompt_registry()

    with pytest.raises(CreatorOSValidationError):
        render_gaming_scene_visual_prompt(
            registry,
            game="Minecraft",
            scene_number=2,
            scene_purpose="Develop the main idea clearly",
            script_beat="",
            visual_direction="Focus on one clear gameplay-related visual moment with readable overlays.",
            on_screen_text="Myth or Fact?",
            platform="youtube_shorts",
        )
