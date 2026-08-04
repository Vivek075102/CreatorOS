"""Unit tests for CreatorOS core content domain models."""

import pytest
from pydantic import ValidationError

from creatoros.domain.content import ContentBrief, ContentOpportunity, Scene, Script, Storyboard
from creatoros.domain.enums import ContentPlatform


def build_scene(*, scene_number: int = 1, duration_seconds: int = 12) -> Scene:
    """Create a minimal valid scene for content model tests."""

    return Scene(
        scene_number=scene_number,
        duration_seconds=duration_seconds,
        narration=f"Narration {scene_number}",
        visual_description=f"Visual description {scene_number}",
    )


def test_content_opportunity_generates_expected_id_prefix() -> None:
    """Content opportunities should generate opportunity-prefixed identifiers."""

    opportunity = ContentOpportunity(
        title="Fastest boss strategy",
        game="Elden Ring",
        topic="Boss guides",
        source="trend_feed",
        opportunity_score=82,
        reasoning="High search momentum.",
        estimated_duration_seconds=45,
    )

    assert opportunity.id.startswith("opportunity_")


def test_content_opportunity_validates_required_fields() -> None:
    """Content opportunity validation should reject blank or invalid values."""

    with pytest.raises(ValidationError):
        ContentOpportunity(
            title="   ",
            game="Elden Ring",
            topic="Boss guides",
            source="trend_feed",
            opportunity_score=82,
            reasoning="High search momentum.",
            estimated_duration_seconds=45,
        )

    with pytest.raises(ValidationError):
        ContentOpportunity(
            title="Fastest boss strategy",
            game="   ",
            topic="Boss guides",
            source="trend_feed",
            opportunity_score=82,
            reasoning="High search momentum.",
            estimated_duration_seconds=45,
        )

    with pytest.raises(ValidationError):
        ContentOpportunity(
            title="Fastest boss strategy",
            game="Elden Ring",
            topic="Boss guides",
            source="trend_feed",
            opportunity_score=101,
            reasoning="High search momentum.",
            estimated_duration_seconds=45,
        )

    with pytest.raises(ValidationError):
        ContentOpportunity(
            title="Fastest boss strategy",
            game="Elden Ring",
            topic="Boss guides",
            source="trend_feed",
            opportunity_score=82,
            reasoning="High search momentum.",
            estimated_duration_seconds=0,
        )


def test_content_opportunity_mutable_defaults_are_not_shared() -> None:
    """References lists should not be shared across opportunity instances."""

    first = ContentOpportunity(
        title="Fastest boss strategy",
        game="Elden Ring",
        topic="Boss guides",
        source="trend_feed",
        opportunity_score=82,
        reasoning="High search momentum.",
        estimated_duration_seconds=45,
    )
    second = ContentOpportunity(
        title="Hidden lore theory",
        game="Bloodborne",
        topic="Lore",
        source="trend_feed",
        opportunity_score=76,
        reasoning="Strong community discussion.",
        estimated_duration_seconds=50,
    )

    first.references.append("https://example.com/reference")

    assert second.references == []


def test_content_brief_generates_expected_id_prefix_and_rejects_blank_strings() -> None:
    """Content briefs should generate brief-prefixed IDs and reject blank required fields."""

    brief = ContentBrief(
        title="Boss guide short",
        audience="Action RPG players",
        platform=ContentPlatform.YOUTUBE_SHORTS,
        objective="Teach a fast strategy",
        tone="Direct",
        hook_direction="Immediate payoff",
    )

    assert brief.id.startswith("brief_")

    with pytest.raises(ValidationError):
        ContentBrief(
            title="Boss guide short",
            audience="Action RPG players",
            platform=ContentPlatform.YOUTUBE_SHORTS,
            objective="Teach a fast strategy",
            tone="Direct",
            hook_direction="   ",
        )


def test_script_generates_expected_id_prefix_and_validates_fields() -> None:
    """Scripts should generate script-prefixed IDs and validate duration and version."""

    script = Script(
        title="Boss guide short",
        hook="This boss dies in 20 seconds.",
        body="Use stagger, move left, punish recovery.",
        ending="Now try it yourself.",
        call_to_action="Follow for more gaming guides.",
        estimated_duration_seconds=35,
        version=1,
    )

    assert script.id.startswith("script_")

    with pytest.raises(ValidationError):
        Script(
            title="Boss guide short",
            hook="This boss dies in 20 seconds.",
            body="Use stagger, move left, punish recovery.",
            ending="Now try it yourself.",
            call_to_action="Follow for more gaming guides.",
            estimated_duration_seconds=0,
            version=1,
        )

    with pytest.raises(ValidationError):
        Script(
            title="Boss guide short",
            hook="This boss dies in 20 seconds.",
            body="Use stagger, move left, punish recovery.",
            ending="Now try it yourself.",
            call_to_action="Follow for more gaming guides.",
            estimated_duration_seconds=35,
            version=0,
        )


def test_scene_generates_expected_id_prefix_and_validates_fields() -> None:
    """Scenes should generate scene-prefixed IDs and validate numbering and duration."""

    scene = build_scene()

    assert scene.id.startswith("scene_")

    with pytest.raises(ValidationError):
        build_scene(scene_number=0)

    with pytest.raises(ValidationError):
        build_scene(duration_seconds=0)

    with pytest.raises(ValidationError):
        Scene(
            scene_number=1,
            duration_seconds=10,
            narration="   ",
            visual_description="Clear visual direction",
        )


def test_scene_mutable_defaults_are_not_shared() -> None:
    """Sound effect lists should not be shared across scenes."""

    first = build_scene(scene_number=1)
    second = build_scene(scene_number=2)

    first.sound_effects.append("whoosh")

    assert second.sound_effects == []


def test_storyboard_generates_expected_id_prefix_and_computes_total_duration() -> None:
    """Storyboards should generate storyboard-prefixed IDs and compute total duration."""

    storyboard = Storyboard(
        title="Boss guide storyboard",
        scenes=[build_scene(scene_number=1, duration_seconds=10), build_scene(scene_number=2, duration_seconds=15)],
    )

    assert storyboard.id.startswith("storyboard_")
    assert storyboard.total_duration_seconds == 25


def test_storyboard_requires_at_least_one_scene_and_rejects_blank_title() -> None:
    """Storyboards should require scenes and non-blank titles."""

    with pytest.raises(ValidationError):
        Storyboard(title="Boss guide storyboard", scenes=[])

    with pytest.raises(ValidationError):
        Storyboard(title="   ", scenes=[build_scene()])


def test_storyboard_serializes_and_restores_predictably() -> None:
    """Storyboards should round-trip predictably through Pydantic serialization."""

    storyboard = Storyboard(
        title="Boss guide storyboard",
        scenes=[build_scene(scene_number=1, duration_seconds=10), build_scene(scene_number=2, duration_seconds=15)],
        notes="Keep cuts fast.",
    )

    dumped = storyboard.model_dump()
    restored = Storyboard.model_validate(
        storyboard.model_dump(exclude={"total_duration_seconds"}),
    )

    assert dumped["total_duration_seconds"] == 25
    assert restored == storyboard


def test_content_models_serialize_and_restore_predictably() -> None:
    """The core content models should round-trip predictably."""

    opportunity = ContentOpportunity(
        title="Fastest boss strategy",
        game="Elden Ring",
        topic="Boss guides",
        source="trend_feed",
        opportunity_score=82,
        reasoning="High search momentum.",
        estimated_duration_seconds=45,
        references=["https://example.com/reference"],
    )
    brief = ContentBrief(
        title="Boss guide short",
        audience="Action RPG players",
        platform=ContentPlatform.YOUTUBE_SHORTS,
        objective="Teach a fast strategy",
        tone="Direct",
        hook_direction="Immediate payoff",
        constraints=["Stay under 45 seconds"],
        notes="Focus on the first attempt.",
    )
    script = Script(
        title="Boss guide short",
        hook="This boss dies in 20 seconds.",
        body="Use stagger, move left, punish recovery.",
        ending="Now try it yourself.",
        call_to_action="Follow for more gaming guides.",
        estimated_duration_seconds=35,
        version=2,
    )

    assert ContentOpportunity.model_validate(opportunity.model_dump()) == opportunity
    assert ContentBrief.model_validate(brief.model_dump()) == brief
    assert Script.model_validate(script.model_dump()) == script
