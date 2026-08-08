"""Tests for builtin research prompt rendering helpers."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.prompts import (
    create_builtin_prompt_registry,
    render_gaming_discover_trends,
    render_gaming_evaluate_opportunity,
    render_gaming_expand_keywords,
)


def test_gaming_discover_trends_renders_successfully() -> None:
    """The discover-trends helper should render a builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_discover_trends(
        registry,
        game="Minecraft",
        topic="gaming facts",
        research_signals="Players keep resurfacing quick hidden mechanics discussions.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    assert rendered.prompt_name == "gaming_discover_trends"
    assert rendered.prompt_version == 1
    assert "Minecraft" in rendered.text
    assert "gaming facts" in rendered.text
    assert "Players keep resurfacing quick hidden mechanics discussions." in rendered.text
    assert "30" in rendered.text


def test_missing_required_values_are_rejected() -> None:
    """Research render helpers should reject missing required values safely."""

    registry = create_builtin_prompt_registry()

    with pytest.raises(CreatorOSValidationError):
        render_gaming_discover_trends(
            registry,
            game="Minecraft",
            topic="gaming facts",
            research_signals="",
            platform="youtube_shorts",
            target_duration_seconds=30,
        )


def test_gaming_evaluate_opportunity_renders_successfully() -> None:
    """The evaluation helper should render a builtin evaluation prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_evaluate_opportunity(
        registry,
        game="Roblox",
        title="Roblox: Funny Myths",
        topic="funny myths",
        angle="Break down a recurring myth players repeat.",
        source_summary="Players are discussing recurring myths about game mechanics.",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    assert rendered.prompt_name == "gaming_evaluate_opportunity"
    for label in ["DECISION:", "SCORE:", "STRENGTHS:", "RISKS:", "RECOMMENDED_ANGLE:", "HOOK_DIRECTION:", "REASON:"]:
        assert label in rendered.text


def test_gaming_expand_keywords_renders_successfully() -> None:
    """The keyword-expansion helper should render its builtin prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_expand_keywords(
        registry,
        game="Minecraft",
        topic="gaming facts",
        seed_keywords="minecraft facts, hidden mechanics",
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_expand_keywords"
    for label in ["PRIMARY:", "RELATED:", "QUESTIONS:", "ENTITIES:"]:
        assert label in rendered.text


def test_helpers_do_not_mutate_registry_definitions() -> None:
    """Rendering helpers should not mutate stored prompt definitions."""

    registry = create_builtin_prompt_registry()
    before = registry.get("gaming_discover_trends").model_dump(mode="python")

    render_gaming_discover_trends(
        registry,
        game="Minecraft",
        topic="gaming facts",
        research_signals="Signals",
        platform="youtube_shorts",
        target_duration_seconds=30,
    )

    after = registry.get("gaming_discover_trends").model_dump(mode="python")
    assert after == before


def test_helpers_do_not_call_providers() -> None:
    """Rendering helpers should work without any provider interaction."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_expand_keywords(
        registry,
        game="Roblox",
        topic="funny myths",
        seed_keywords="roblox myths",
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_expand_keywords"
