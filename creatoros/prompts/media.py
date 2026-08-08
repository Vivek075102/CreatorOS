"""Media prompt constants and rendering helpers for builtin gaming prompts."""

from __future__ import annotations

from creatoros.prompts.models import RenderedPrompt
from creatoros.prompts.registry import PromptRegistry
from creatoros.prompts.renderer import PromptRenderer

GAMING_THUMBNAIL_CONCEPT = "gaming_thumbnail_concept"
GAMING_SCENE_VISUAL_PROMPT = "gaming_scene_visual_prompt"
GAMING_SCENE_MOTION_PROMPT = "gaming_scene_motion_prompt"
GAMING_NARRATION_DIRECTION = "gaming_narration_direction"


def render_gaming_thumbnail_concept(
    registry: PromptRegistry,
    *,
    title: str,
    game: str,
    topic: str,
    angle: str,
    hook: str,
    platform: str,
    visual_context: str,
) -> RenderedPrompt:
    """Render the builtin gaming thumbnail concept prompt."""

    definition = registry.get(GAMING_THUMBNAIL_CONCEPT)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "game": game,
            "topic": topic,
            "angle": angle,
            "hook": hook,
            "platform": platform,
            "visual_context": visual_context,
        },
    )


def render_gaming_scene_visual_prompt(
    registry: PromptRegistry,
    *,
    game: str,
    scene_number: int,
    scene_purpose: str,
    script_beat: str,
    visual_direction: str,
    on_screen_text: str,
    platform: str,
) -> RenderedPrompt:
    """Render the builtin gaming scene visual prompt."""

    definition = registry.get(GAMING_SCENE_VISUAL_PROMPT)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "scene_number": scene_number,
            "scene_purpose": scene_purpose,
            "script_beat": script_beat,
            "visual_direction": visual_direction,
            "on_screen_text": on_screen_text,
            "platform": platform,
        },
    )


def render_gaming_scene_motion_prompt(
    registry: PromptRegistry,
    *,
    game: str,
    scene_number: int,
    scene_purpose: str,
    visual_summary: str,
    script_beat: str,
    duration_seconds: float,
    platform: str,
) -> RenderedPrompt:
    """Render the builtin gaming scene motion prompt."""

    definition = registry.get(GAMING_SCENE_MOTION_PROMPT)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "scene_number": scene_number,
            "scene_purpose": scene_purpose,
            "visual_summary": visual_summary,
            "script_beat": script_beat,
            "duration_seconds": duration_seconds,
            "platform": platform,
        },
    )


def render_gaming_narration_direction(
    registry: PromptRegistry,
    *,
    title: str,
    game: str,
    script_text: str,
    target_duration_seconds: int,
    tone: str,
    platform: str,
) -> RenderedPrompt:
    """Render the builtin gaming narration direction prompt."""

    definition = registry.get(GAMING_NARRATION_DIRECTION)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "game": game,
            "script_text": script_text,
            "target_duration_seconds": target_duration_seconds,
            "tone": tone,
            "platform": platform,
        },
    )


__all__ = [
    "GAMING_NARRATION_DIRECTION",
    "GAMING_SCENE_MOTION_PROMPT",
    "GAMING_SCENE_VISUAL_PROMPT",
    "GAMING_THUMBNAIL_CONCEPT",
    "render_gaming_narration_direction",
    "render_gaming_scene_motion_prompt",
    "render_gaming_scene_visual_prompt",
    "render_gaming_thumbnail_concept",
]
