"""Tests for builtin script prompt rendering helpers."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.prompts import (
    create_builtin_prompt_registry,
    render_gaming_cta,
    render_gaming_hook,
    render_youtube_shorts_script,
)


def test_youtube_shorts_script_renders_successfully() -> None:
    """The script helper should render the builtin short-form script prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_youtube_shorts_script(
        registry,
        title="Roblox: Funny Myths",
        game="Roblox",
        topic="funny myths",
        angle="Test three popular myths",
        hook_direction="Challenge a common belief",
        platform="youtube_shorts",
        target_duration_seconds=30,
        source_summary="Supplied research notes discuss recurring myths about game mechanics.",
    )

    assert rendered.prompt_name == "youtube_shorts_script"
    assert rendered.prompt_version == 1
    assert "Roblox: Funny Myths" in rendered.text
    assert "Roblox" in rendered.text
    assert "funny myths" in rendered.text
    assert "30" in rendered.text
    assert "Supplied research notes discuss recurring myths about game mechanics." in rendered.text
    for label in ["TITLE:", "HOOK:", "BODY:", "ENDING:", "CALL_TO_ACTION:", "ESTIMATED_DURATION_SECONDS:", "EVIDENCE_NOTE:"]:
        assert label in rendered.text


def test_gaming_hook_renders_successfully() -> None:
    """The hook helper should render the builtin gaming hook prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_hook(
        registry,
        game="Minecraft",
        title="Minecraft: Hidden Facts",
        topic="gaming facts",
        angle="Reveal one overlooked mechanic",
        source_summary="Players keep resurfacing hidden mechanics discussions.",
        platform="youtube_shorts",
    )

    assert rendered.prompt_name == "gaming_hook"
    for label in ["HOOK_1:", "HOOK_2:", "HOOK_3:", "BEST_HOOK:", "WHY:"]:
        assert label in rendered.text


def test_gaming_cta_renders_successfully() -> None:
    """The CTA helper should render the builtin gaming CTA prompt successfully."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_cta(
        registry,
        game="Minecraft",
        topic="gaming facts",
        platform="youtube_shorts",
        tone="natural and concise",
    )

    assert rendered.prompt_name == "gaming_cta"
    for label in ["CTA:", "ALTERNATIVE:"]:
        assert label in rendered.text


def test_script_helpers_do_not_mutate_registry_definitions() -> None:
    """Script rendering helpers should not mutate stored prompt definitions."""

    registry = create_builtin_prompt_registry()
    before = registry.get("youtube_shorts_script").model_dump(mode="python")

    render_youtube_shorts_script(
        registry,
        title="Minecraft: Gaming Facts",
        game="Minecraft",
        topic="gaming facts",
        angle="Explain one clear fact",
        hook_direction="Start with a surprising fact",
        platform="youtube_shorts",
        target_duration_seconds=30,
        source_summary="Supplied evidence summary.",
    )

    after = registry.get("youtube_shorts_script").model_dump(mode="python")
    assert after == before


def test_script_helpers_do_not_call_providers() -> None:
    """Script rendering helpers should work without any provider interaction."""

    registry = create_builtin_prompt_registry()

    rendered = render_gaming_cta(
        registry,
        game="Roblox",
        topic="funny myths",
        platform="youtube_shorts",
        tone="playful but calm",
    )

    assert rendered.prompt_name == "gaming_cta"


def test_missing_required_script_values_are_rejected() -> None:
    """Script rendering helpers should reject missing required values safely."""

    registry = create_builtin_prompt_registry()

    with pytest.raises(CreatorOSValidationError):
        render_youtube_shorts_script(
            registry,
            title="Roblox: Funny Myths",
            game="Roblox",
            topic="funny myths",
            angle="Test three popular myths",
            hook_direction="Challenge a common belief",
            platform="youtube_shorts",
            target_duration_seconds=30,
            source_summary="",
        )
