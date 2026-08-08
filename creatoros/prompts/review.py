"""Review prompt constants and rendering helpers for builtin gaming prompts."""

from __future__ import annotations

from creatoros.prompts.models import RenderedPrompt
from creatoros.prompts.registry import PromptRegistry
from creatoros.prompts.renderer import PromptRenderer

GAMING_SCRIPT_QUALITY_REVIEW = "gaming_script_quality_review"
GAMING_EVIDENCE_CONSISTENCY_REVIEW = "gaming_evidence_consistency_review"
GAMING_STORYBOARD_QUALITY_REVIEW = "gaming_storyboard_quality_review"
GAMING_PUBLICATION_READINESS_REVIEW = "gaming_publication_readiness_review"


def render_gaming_script_quality_review(
    registry: PromptRegistry,
    *,
    title: str,
    game: str,
    topic: str,
    angle: str,
    source_summary: str,
    script_text: str,
    platform: str,
    target_duration_seconds: int,
) -> RenderedPrompt:
    """Render the builtin gaming script quality review prompt."""

    definition = registry.get(GAMING_SCRIPT_QUALITY_REVIEW)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "game": game,
            "topic": topic,
            "angle": angle,
            "source_summary": source_summary,
            "script_text": script_text,
            "platform": platform,
            "target_duration_seconds": target_duration_seconds,
        },
    )


def render_gaming_evidence_consistency_review(
    registry: PromptRegistry,
    *,
    game: str,
    source_summary: str,
    research_notes: str,
    content_text: str,
    content_stage: str,
) -> RenderedPrompt:
    """Render the builtin gaming evidence consistency review prompt."""

    definition = registry.get(GAMING_EVIDENCE_CONSISTENCY_REVIEW)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "game": game,
            "source_summary": source_summary,
            "research_notes": research_notes,
            "content_text": content_text,
            "content_stage": content_stage,
        },
    )


def render_gaming_storyboard_quality_review(
    registry: PromptRegistry,
    *,
    title: str,
    game: str,
    script_text: str,
    storyboard_text: str,
    platform: str,
    target_duration_seconds: int,
) -> RenderedPrompt:
    """Render the builtin gaming storyboard quality review prompt."""

    definition = registry.get(GAMING_STORYBOARD_QUALITY_REVIEW)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "game": game,
            "script_text": script_text,
            "storyboard_text": storyboard_text,
            "platform": platform,
            "target_duration_seconds": target_duration_seconds,
        },
    )


def render_gaming_publication_readiness_review(
    registry: PromptRegistry,
    *,
    title: str,
    game: str,
    script_text: str,
    storyboard_summary: str,
    thumbnail_summary: str,
    narration_summary: str,
    evidence_review: str,
    platform: str,
) -> RenderedPrompt:
    """Render the builtin gaming publication readiness review prompt."""

    definition = registry.get(GAMING_PUBLICATION_READINESS_REVIEW)
    renderer = PromptRenderer()
    return renderer.render(
        definition,
        {
            "title": title,
            "game": game,
            "script_text": script_text,
            "storyboard_summary": storyboard_summary,
            "thumbnail_summary": thumbnail_summary,
            "narration_summary": narration_summary,
            "evidence_review": evidence_review,
            "platform": platform,
        },
    )


__all__ = [
    "GAMING_EVIDENCE_CONSISTENCY_REVIEW",
    "GAMING_PUBLICATION_READINESS_REVIEW",
    "GAMING_SCRIPT_QUALITY_REVIEW",
    "GAMING_STORYBOARD_QUALITY_REVIEW",
    "render_gaming_evidence_consistency_review",
    "render_gaming_publication_readiness_review",
    "render_gaming_script_quality_review",
    "render_gaming_storyboard_quality_review",
]
