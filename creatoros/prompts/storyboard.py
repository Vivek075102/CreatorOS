"""Storyboard prompt constants and rendering helpers for builtin gaming prompts."""

from __future__ import annotations

from creatoros.prompts.models import RenderedPrompt
from creatoros.prompts.registry import PromptRegistry
from creatoros.prompts.renderer import PromptRenderer

STORYBOARD_SCENE_BREAKDOWN = "storyboard_scene_breakdown"
STORYBOARD_VISUAL_DIRECTION = "storyboard_visual_direction"
STORYBOARD_TIMING_REVIEW = "storyboard_timing_review"


def render_storyboard_scene_breakdown(
    registry: PromptRegistry,
    *,
    title: str,
    game: str,
    platform: str,
    hook: str,
    body: str,
    ending: str,
    call_to_action: str,
    target_duration_seconds: int,
) -> RenderedPrompt:
    """Render the builtin storyboard scene breakdown prompt."""

    definition = registry.get(STORYBOARD_SCENE_BREAKDOWN)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "game": game,
            "platform": platform,
            "hook": hook,
            "body": body,
            "ending": ending,
            "call_to_action": call_to_action,
            "target_duration_seconds": target_duration_seconds,
        },
    )


def render_storyboard_visual_direction(
    registry: PromptRegistry,
    *,
    game: str,
    scene_number: int,
    scene_purpose: str,
    script_beat: str,
    visual_summary: str,
    platform: str,
    duration_seconds: float,
) -> RenderedPrompt:
    """Render the builtin storyboard visual direction prompt."""

    definition = registry.get(STORYBOARD_VISUAL_DIRECTION)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "scene_number": scene_number,
            "scene_purpose": scene_purpose,
            "script_beat": script_beat,
            "visual_summary": visual_summary,
            "platform": platform,
            "duration_seconds": duration_seconds,
        },
    )


def render_storyboard_timing_review(
    registry: PromptRegistry,
    *,
    title: str,
    scene_summary: str,
    target_duration_seconds: int,
    platform: str,
) -> RenderedPrompt:
    """Render the builtin storyboard timing review prompt."""

    definition = registry.get(STORYBOARD_TIMING_REVIEW)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "scene_summary": scene_summary,
            "target_duration_seconds": target_duration_seconds,
            "platform": platform,
        },
    )


__all__ = [
    "STORYBOARD_SCENE_BREAKDOWN",
    "STORYBOARD_TIMING_REVIEW",
    "STORYBOARD_VISUAL_DIRECTION",
    "render_storyboard_scene_breakdown",
    "render_storyboard_timing_review",
    "render_storyboard_visual_direction",
]
