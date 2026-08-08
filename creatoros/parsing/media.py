"""Typed media-output contracts and parsers for builtin CreatorOS prompts."""

from __future__ import annotations

from pydantic import ValidationError, field_validator

from creatoros.core import StructuredOutputError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.converters import (
    parse_positive_float_field,
    parse_positive_int_field,
    wrap_model_validation_error,
)
from creatoros.parsing.models import (
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)
from creatoros.parsing.parser import StructuredTextParser

GAMING_THUMBNAIL_CONCEPT_SPEC = StructuredOutputSpec(
    name="gaming_thumbnail_concept_output",
    fields=(
        StructuredFieldSpec(name="CONCEPT"),
        StructuredFieldSpec(name="FOCAL_SUBJECT"),
        StructuredFieldSpec(name="BACKGROUND"),
        StructuredFieldSpec(name="COMPOSITION"),
        StructuredFieldSpec(name="EXPRESSION_OR_ACTION"),
        StructuredFieldSpec(name="ON_IMAGE_TEXT"),
        StructuredFieldSpec(name="STYLE_DIRECTION"),
        StructuredFieldSpec(name="AVOID"),
        StructuredFieldSpec(name="EVIDENCE_NOTE"),
    ),
)

GAMING_SCENE_VISUAL_SPEC = StructuredOutputSpec(
    name="gaming_scene_visual_output",
    fields=(
        StructuredFieldSpec(name="SCENE_NUMBER"),
        StructuredFieldSpec(name="SUBJECT"),
        StructuredFieldSpec(name="ENVIRONMENT"),
        StructuredFieldSpec(name="ACTION"),
        StructuredFieldSpec(name="COMPOSITION"),
        StructuredFieldSpec(name="MOOD"),
        StructuredFieldSpec(name="ON_SCREEN_TEXT"),
        StructuredFieldSpec(name="STYLE_DIRECTION"),
        StructuredFieldSpec(name="NEGATIVE_GUIDANCE"),
    ),
)

GAMING_SCENE_MOTION_SPEC = StructuredOutputSpec(
    name="gaming_scene_motion_output",
    fields=(
        StructuredFieldSpec(name="SCENE_NUMBER"),
        StructuredFieldSpec(name="PRIMARY_MOTION"),
        StructuredFieldSpec(name="SUBJECT_MOVEMENT"),
        StructuredFieldSpec(name="CAMERA_DIRECTION"),
        StructuredFieldSpec(name="TRANSITION_GUIDANCE"),
        StructuredFieldSpec(name="PACING"),
        StructuredFieldSpec(name="DURATION_SECONDS"),
        StructuredFieldSpec(name="AVOID"),
    ),
)

GAMING_NARRATION_DIRECTION_SPEC = StructuredOutputSpec(
    name="gaming_narration_direction_output",
    fields=(
        StructuredFieldSpec(name="NARRATION_TEXT"),
        StructuredFieldSpec(name="TONE"),
        StructuredFieldSpec(name="PACE"),
        StructuredFieldSpec(name="EMPHASIS"),
        StructuredFieldSpec(name="PAUSE_GUIDANCE"),
        StructuredFieldSpec(name="PRONUNCIATION_NOTES"),
        StructuredFieldSpec(name="TARGET_DURATION_SECONDS"),
    ),
)


def _trim_required_text(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class GamingThumbnailConceptOutput(CreatorOSModel):
    """Structured output contract for `gaming_thumbnail_concept`."""

    concept: str
    focal_subject: str
    background: str
    composition: str
    expression_or_action: str
    on_image_text: str
    style_direction: str
    avoid: str
    evidence_note: str

    @field_validator(
        "concept",
        "focal_subject",
        "background",
        "composition",
        "expression_or_action",
        "on_image_text",
        "style_direction",
        "avoid",
        "evidence_note",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingSceneVisualOutput(CreatorOSModel):
    """Structured output contract for `gaming_scene_visual_prompt`."""

    scene_number: int
    subject: str
    environment: str
    action: str
    composition: str
    mood: str
    on_screen_text: str
    style_direction: str
    negative_guidance: str

    @field_validator("scene_number")
    @classmethod
    def validate_scene_number(cls, value: int) -> int:
        """Require a positive scene number."""

        if value <= 0:
            raise ValueError("scene_number must be greater than 0")
        return value

    @field_validator(
        "subject",
        "environment",
        "action",
        "composition",
        "mood",
        "on_screen_text",
        "style_direction",
        "negative_guidance",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingSceneMotionOutput(CreatorOSModel):
    """Structured output contract for `gaming_scene_motion_prompt`."""

    scene_number: int
    primary_motion: str
    subject_movement: str
    camera_direction: str
    transition_guidance: str
    pacing: str
    duration_seconds: float
    avoid: str

    @field_validator("scene_number")
    @classmethod
    def validate_scene_number(cls, value: int) -> int:
        """Require a positive scene number."""

        if value <= 0:
            raise ValueError("scene_number must be greater than 0")
        return value

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require a positive scene duration."""

        if value <= 0:
            raise ValueError("duration_seconds must be greater than 0")
        return value

    @field_validator(
        "primary_motion",
        "subject_movement",
        "camera_direction",
        "transition_guidance",
        "pacing",
        "avoid",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingNarrationDirectionOutput(CreatorOSModel):
    """Structured output contract for `gaming_narration_direction`."""

    narration_text: str
    tone: str
    pace: str
    emphasis: str
    pause_guidance: str
    pronunciation_notes: str
    target_duration_seconds: int

    @field_validator("target_duration_seconds")
    @classmethod
    def validate_target_duration_seconds(cls, value: int) -> int:
        """Require a positive narration target duration."""

        if value <= 0:
            raise ValueError("target_duration_seconds must be greater than 0")
        return value

    @field_validator(
        "narration_text",
        "tone",
        "pace",
        "emphasis",
        "pause_guidance",
        "pronunciation_notes",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


def parse_gaming_thumbnail_concept(text: str) -> GamingThumbnailConceptOutput:
    """Parse structured thumbnail-concept output."""

    result = _parse_flat_result(text, GAMING_THUMBNAIL_CONCEPT_SPEC)
    try:
        return GamingThumbnailConceptOutput(
            concept=_require_value(result, "CONCEPT"),
            focal_subject=_require_value(result, "FOCAL_SUBJECT"),
            background=_require_value(result, "BACKGROUND"),
            composition=_require_value(result, "COMPOSITION"),
            expression_or_action=_require_value(result, "EXPRESSION_OR_ACTION"),
            on_image_text=_require_value(result, "ON_IMAGE_TEXT"),
            style_direction=_require_value(result, "STYLE_DIRECTION"),
            avoid=_require_value(result, "AVOID"),
            evidence_note=_require_value(result, "EVIDENCE_NOTE"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_scene_visual(text: str) -> GamingSceneVisualOutput:
    """Parse structured scene-visual output."""

    result = _parse_flat_result(text, GAMING_SCENE_VISUAL_SPEC)
    try:
        return GamingSceneVisualOutput(
            scene_number=parse_positive_int_field("SCENE_NUMBER", _require_value(result, "SCENE_NUMBER")),
            subject=_require_value(result, "SUBJECT"),
            environment=_require_value(result, "ENVIRONMENT"),
            action=_require_value(result, "ACTION"),
            composition=_require_value(result, "COMPOSITION"),
            mood=_require_value(result, "MOOD"),
            on_screen_text=_require_value(result, "ON_SCREEN_TEXT"),
            style_direction=_require_value(result, "STYLE_DIRECTION"),
            negative_guidance=_require_value(result, "NEGATIVE_GUIDANCE"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_scene_motion(text: str) -> GamingSceneMotionOutput:
    """Parse structured scene-motion output."""

    result = _parse_flat_result(text, GAMING_SCENE_MOTION_SPEC)
    try:
        return GamingSceneMotionOutput(
            scene_number=parse_positive_int_field("SCENE_NUMBER", _require_value(result, "SCENE_NUMBER")),
            primary_motion=_require_value(result, "PRIMARY_MOTION"),
            subject_movement=_require_value(result, "SUBJECT_MOVEMENT"),
            camera_direction=_require_value(result, "CAMERA_DIRECTION"),
            transition_guidance=_require_value(result, "TRANSITION_GUIDANCE"),
            pacing=_require_value(result, "PACING"),
            duration_seconds=parse_positive_float_field("DURATION_SECONDS", _require_value(result, "DURATION_SECONDS")),
            avoid=_require_value(result, "AVOID"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_narration_direction(text: str) -> GamingNarrationDirectionOutput:
    """Parse structured narration-direction output."""

    result = _parse_flat_result(text, GAMING_NARRATION_DIRECTION_SPEC)
    try:
        return GamingNarrationDirectionOutput(
            narration_text=_require_value(result, "NARRATION_TEXT"),
            tone=_require_value(result, "TONE"),
            pace=_require_value(result, "PACE"),
            emphasis=_require_value(result, "EMPHASIS"),
            pause_guidance=_require_value(result, "PAUSE_GUIDANCE"),
            pronunciation_notes=_require_value(result, "PRONUNCIATION_NOTES"),
            target_duration_seconds=parse_positive_int_field(
                "TARGET_DURATION_SECONDS",
                _require_value(result, "TARGET_DURATION_SECONDS"),
            ),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def _parse_flat_result(text: str, spec: StructuredOutputSpec) -> StructuredTextParseResult:
    """Parse text with the flat structured parser and reject failed results safely."""

    parser = StructuredTextParser()
    result = parser.parse(text, spec)
    if result.status.value == "failed":
        details: dict[str, object] = {}
        if result.missing_required_fields:
            details["missing_required_fields"] = result.missing_required_fields
        if result.unknown_fields:
            details["unknown_fields"] = result.unknown_fields
        raise StructuredOutputError(
            "structured output could not be parsed",
            code="structured_output_invalid",
            details=details,
        )
    return result


def _require_value(result: StructuredTextParseResult, field_name: str) -> str:
    """Return a required parsed string value."""

    value = result.get_value(field_name)
    assert value is not None
    return value
