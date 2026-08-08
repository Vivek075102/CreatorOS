"""Research prompt constants and rendering helpers for builtin gaming prompts."""

from __future__ import annotations

from creatoros.prompts.models import RenderedPrompt
from creatoros.prompts.registry import PromptRegistry
from creatoros.prompts.renderer import PromptRenderer

GAMING_DISCOVER_TRENDS = "gaming_discover_trends"
GAMING_EVALUATE_OPPORTUNITY = "gaming_evaluate_opportunity"
GAMING_EXPAND_KEYWORDS = "gaming_expand_keywords"


def render_gaming_discover_trends(
    registry: PromptRegistry,
    *,
    game: str,
    topic: str,
    research_signals: str,
    platform: str,
    target_duration_seconds: int,
) -> RenderedPrompt:
    """Render the builtin gaming trend-discovery prompt."""

    definition = registry.get(GAMING_DISCOVER_TRENDS)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "topic": topic,
            "research_signals": research_signals,
            "platform": platform,
            "target_duration_seconds": target_duration_seconds,
        },
    )


def render_gaming_evaluate_opportunity(
    registry: PromptRegistry,
    *,
    game: str,
    title: str,
    topic: str,
    angle: str,
    source_summary: str,
    platform: str,
    target_duration_seconds: int,
) -> RenderedPrompt:
    """Render the builtin gaming opportunity-evaluation prompt."""

    definition = registry.get(GAMING_EVALUATE_OPPORTUNITY)
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
            "target_duration_seconds": target_duration_seconds,
        },
    )


def render_gaming_expand_keywords(
    registry: PromptRegistry,
    *,
    game: str,
    topic: str,
    seed_keywords: str,
    platform: str,
) -> RenderedPrompt:
    """Render the builtin gaming research-keyword expansion prompt."""

    definition = registry.get(GAMING_EXPAND_KEYWORDS)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "topic": topic,
            "seed_keywords": seed_keywords,
            "platform": platform,
        },
    )


__all__ = [
    "GAMING_DISCOVER_TRENDS",
    "GAMING_EVALUATE_OPPORTUNITY",
    "GAMING_EXPAND_KEYWORDS",
    "render_gaming_discover_trends",
    "render_gaming_evaluate_opportunity",
    "render_gaming_expand_keywords",
]
