"""Core content-oriented domain models for CreatorOS."""

from __future__ import annotations

from pydantic import Field, computed_field, field_validator, model_validator

from creatoros.domain.base import CreatorOSModel, generate_id
from creatoros.domain.enums import ContentPlatform


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Reject blank strings for required textual fields."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class ContentOpportunity(CreatorOSModel):
    """Represents a scored content opportunity discovered during research."""

    id: str = Field(default_factory=lambda: generate_id("opportunity"))
    title: str
    game: str
    topic: str
    source: str
    opportunity_score: float
    reasoning: str
    estimated_duration_seconds: int
    references: list[str] = Field(default_factory=list)

    @field_validator("title", "game")
    @classmethod
    def validate_required_non_blank_strings(cls, value: str, info) -> str:
        """Reject blank values for required opportunity fields."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("opportunity_score")
    @classmethod
    def validate_opportunity_score(cls, value: float) -> float:
        """Ensure opportunity scores remain within the allowed range."""

        if not 0 <= value <= 100:
            raise ValueError("opportunity_score must be between 0 and 100")
        return value

    @field_validator("estimated_duration_seconds")
    @classmethod
    def validate_estimated_duration_seconds(cls, value: int) -> int:
        """Ensure estimated durations are positive."""

        if value <= 0:
            raise ValueError("estimated_duration_seconds must be greater than zero")
        return value


class ContentBrief(CreatorOSModel):
    """Represents a structured brief for content generation."""

    id: str = Field(default_factory=lambda: generate_id("brief"))
    title: str
    audience: str
    platform: ContentPlatform
    objective: str
    tone: str
    hook_direction: str
    constraints: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("title", "audience", "objective", "tone", "hook_direction")
    @classmethod
    def validate_required_non_blank_strings(cls, value: str, info) -> str:
        """Reject blank values for required brief fields."""

        return _validate_non_blank(value, field_name=info.field_name)


class Script(CreatorOSModel):
    """Represents a structured script for content production."""

    id: str = Field(default_factory=lambda: generate_id("script"))
    title: str
    hook: str
    body: str
    ending: str
    call_to_action: str
    estimated_duration_seconds: int
    version: int

    @field_validator("title", "hook", "body", "ending", "call_to_action")
    @classmethod
    def validate_required_non_blank_strings(cls, value: str, info) -> str:
        """Reject blank values for required script fields."""

        return _validate_non_blank(value, field_name=info.field_name)

    @field_validator("estimated_duration_seconds")
    @classmethod
    def validate_estimated_duration_seconds(cls, value: int) -> int:
        """Ensure script duration is positive."""

        if value <= 0:
            raise ValueError("estimated_duration_seconds must be greater than zero")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        """Ensure script versions start at one."""

        if value < 1:
            raise ValueError("version must be greater than or equal to 1")
        return value


class Scene(CreatorOSModel):
    """Represents a storyboard scene with timing and production notes."""

    id: str = Field(default_factory=lambda: generate_id("scene"))
    scene_number: int
    duration_seconds: int
    narration: str
    visual_description: str
    camera_direction: str | None = None
    sound_effects: list[str] = Field(default_factory=list)
    transition: str | None = None
    asset_notes: str | None = None

    @field_validator("scene_number")
    @classmethod
    def validate_scene_number(cls, value: int) -> int:
        """Ensure scene numbering starts at one."""

        if value < 1:
            raise ValueError("scene_number must be greater than or equal to 1")
        return value

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: int) -> int:
        """Ensure scene durations are positive."""

        if value <= 0:
            raise ValueError("duration_seconds must be greater than zero")
        return value

    @field_validator("narration", "visual_description")
    @classmethod
    def validate_required_non_blank_strings(cls, value: str, info) -> str:
        """Reject blank values for required scene fields."""

        return _validate_non_blank(value, field_name=info.field_name)


class Storyboard(CreatorOSModel):
    """Represents a full storyboard composed of ordered scenes."""

    id: str = Field(default_factory=lambda: generate_id("storyboard"))
    title: str
    scenes: list[Scene]
    notes: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str, info) -> str:
        """Reject blank storyboard titles."""

        return _validate_non_blank(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_scenes(self) -> Storyboard:
        """Ensure a storyboard contains at least one scene."""

        if not self.scenes:
            raise ValueError("scenes must contain at least one scene")
        return self

    @computed_field(return_type=int)
    def total_duration_seconds(self) -> int:
        """Return the total storyboard duration across all scenes."""

        return sum(scene.duration_seconds for scene in self.scenes)
