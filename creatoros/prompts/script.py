"""Script prompt constants and rendering helpers for builtin gaming prompts."""

from __future__ import annotations

from creatoros.prompts.models import RenderedPrompt
from creatoros.prompts.registry import PromptRegistry
from creatoros.prompts.renderer import PromptRenderer

YOUTUBE_SHORTS_SCRIPT = "youtube_shorts_script"
GAMING_HOOK = "gaming_hook"
GAMING_CTA = "gaming_cta"


def render_youtube_shorts_script(
    registry: PromptRegistry,
    *,
    title: str,
    game: str,
    topic: str,
    angle: str,
    hook_direction: str,
    platform: str,
    target_duration_seconds: int,
    source_summary: str,
) -> RenderedPrompt:
    """Render the builtin short-form gaming script prompt."""

    definition = registry.get(YOUTUBE_SHORTS_SCRIPT)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "game": game,
            "topic": topic,
            "angle": angle,
            "hook_direction": hook_direction,
            "platform": platform,
            "target_duration_seconds": target_duration_seconds,
            "source_summary": source_summary,
        },
    )


def render_gaming_hook(
    registry: PromptRegistry,
    *,
    game: str,
    title: str,
    topic: str,
    angle: str,
    source_summary: str,
    platform: str,
) -> RenderedPrompt:
    """Render the builtin gaming hook prompt."""

    definition = registry.get(GAMING_HOOK)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "title": title,
            "topic": topic,
            "angle": angle,
            "source_summary": source_summary,
            "platform": platform,
        },
    )


def render_gaming_cta(
    registry: PromptRegistry,
    *,
    game: str,
    topic: str,
    platform: str,
    tone: str,
) -> RenderedPrompt:
    """Render the builtin gaming CTA prompt."""

    definition = registry.get(GAMING_CTA)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "topic": topic,
            "platform": platform,
            "tone": tone,
        },
    )


__all__ = [
    "GAMING_CTA",
    "GAMING_HOOK",
    "YOUTUBE_SHORTS_SCRIPT",
    "render_gaming_cta",
    "render_gaming_hook",
    "render_youtube_shorts_script",
]
