"""Typed storyboard-output contracts and parsers for builtin CreatorOS prompts."""

from __future__ import annotations

import re
from typing import Literal, cast

from pydantic import ValidationError, field_validator, model_validator

from creatoros.core import StructuredOutputError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.converters import (
    parse_literal_field,
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
from creatoros.parsing.text import normalize_field_label, normalize_model_text

_SCENE_HEADER_PATTERN = re.compile(r"^SCENE_(\d+):$")
_HEADER_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 _-]*):$")
_SCENE_FIELD_NAMES = (
    "PURPOSE",
    "SCRIPT_BEAT",
    "VISUAL",
    "ON_SCREEN_TEXT",
    "DURATION_SECONDS",
)
_DURATION_TOLERANCE_SECONDS = 0.25

STORYBOARD_VISUAL_DIRECTION_SPEC = StructuredOutputSpec(
    name="storyboard_visual_direction_output",
    fields=(
        StructuredFieldSpec(name="SCENE_NUMBER"),
        StructuredFieldSpec(name="PRIMARY_VISUAL"),
        StructuredFieldSpec(name="COMPOSITION"),
        StructuredFieldSpec(name="MOTION"),
        StructuredFieldSpec(name="ON_SCREEN_TEXT"),
        StructuredFieldSpec(name="STYLE_NOTES"),
        StructuredFieldSpec(name="AVOID"),
    ),
)

STORYBOARD_TIMING_REVIEW_SPEC = StructuredOutputSpec(
    name="storyboard_timing_review_output",
    fields=(
        StructuredFieldSpec(name="DECISION"),
        StructuredFieldSpec(name="TOTAL_DURATION_ASSESSMENT"),
        StructuredFieldSpec(name="PACING"),
        StructuredFieldSpec(name="SCENE_ISSUES"),
        StructuredFieldSpec(name="RECOMMENDATIONS"),
    ),
)


def _trim_required_text(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class StoryboardScenePlan(CreatorOSModel):
    """Structured plan for one storyboard scene."""

    scene_number: int
    purpose: str
    script_beat: str
    visual: str
    on_screen_text: str
    duration_seconds: float

    @field_validator("scene_number")
    @classmethod
    def validate_scene_number(cls, value: int) -> int:
        """Require positive sequential scene numbers."""

        if value <= 0:
            raise ValueError("scene_number must be greater than 0")
        return value

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, value: float) -> float:
        """Require positive scene durations."""

        if value <= 0:
            raise ValueError("duration_seconds must be greater than 0")
        return value

    @field_validator("purpose", "script_beat", "visual", "on_screen_text")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class StoryboardSceneBreakdownOutput(CreatorOSModel):
    """Structured output contract for `storyboard_scene_breakdown`."""

    storyboard_title: str
    scenes: tuple[StoryboardScenePlan, ...]
    final_scene_count: int
    total_estimated_duration_seconds: float

    @field_validator("storyboard_title")
    @classmethod
    def validate_storyboard_title(cls, value: str) -> str:
        """Trim and reject blank storyboard titles."""

        return _trim_required_text(value, field_name="storyboard_title")

    @field_validator("final_scene_count")
    @classmethod
    def validate_final_scene_count(cls, value: int) -> int:
        """Require a positive final scene count."""

        if value <= 0:
            raise ValueError("final_scene_count must be greater than 0")
        return value

    @field_validator("total_estimated_duration_seconds")
    @classmethod
    def validate_total_estimated_duration_seconds(cls, value: float) -> float:
        """Require a positive total estimated duration."""

        if value <= 0:
            raise ValueError("total_estimated_duration_seconds must be greater than 0")
        return value

    @model_validator(mode="after")
    def validate_scenes(self) -> StoryboardSceneBreakdownOutput:
        """Require sequential scenes and duration consistency."""

        if not self.scenes:
            raise ValueError("scenes must contain at least one scene")

        expected_scene_numbers = list(range(1, len(self.scenes) + 1))
        actual_scene_numbers = [scene.scene_number for scene in self.scenes]
        if actual_scene_numbers != expected_scene_numbers:
            raise ValueError("scene numbers must be sequential starting at 1")

        if self.final_scene_count != len(self.scenes):
            raise ValueError("final_scene_count must equal the number of scenes")

        duration_total = sum(scene.duration_seconds for scene in self.scenes)
        if abs(duration_total - self.total_estimated_duration_seconds) > _DURATION_TOLERANCE_SECONDS:
            raise ValueError("total_estimated_duration_seconds must approximately equal scene durations")

        return self


class StoryboardVisualDirectionOutput(CreatorOSModel):
    """Structured output contract for `storyboard_visual_direction`."""

    scene_number: int
    primary_visual: str
    composition: str
    motion: str
    on_screen_text: str
    style_notes: str
    avoid: str

    @field_validator("scene_number")
    @classmethod
    def validate_scene_number(cls, value: int) -> int:
        """Require a positive scene number."""

        if value <= 0:
            raise ValueError("scene_number must be greater than 0")
        return value

    @field_validator(
        "primary_visual",
        "composition",
        "motion",
        "on_screen_text",
        "style_notes",
        "avoid",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class StoryboardTimingReviewOutput(CreatorOSModel):
    """Structured output contract for `storyboard_timing_review`."""

    decision: Literal["accept", "revise"]
    total_duration_assessment: str
    pacing: str
    scene_issues: str
    recommendations: str

    @field_validator("total_duration_assessment", "pacing", "scene_issues", "recommendations")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


def parse_storyboard_scene_breakdown(text: str) -> StoryboardSceneBreakdownOutput:
    """Parse structured storyboard scene breakdown output."""

    parsed = _parse_scene_breakdown_sections(text)

    try:
        return StoryboardSceneBreakdownOutput(
            storyboard_title=parsed.storyboard_title,
            scenes=parsed.scenes,
            final_scene_count=parse_positive_int_field(
                "FINAL_SCENE_COUNT",
                parsed.final_scene_count,
            ),
            total_estimated_duration_seconds=parse_positive_float_field(
                "TOTAL_ESTIMATED_DURATION_SECONDS",
                parsed.total_estimated_duration_seconds,
            ),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_storyboard_visual_direction(text: str) -> StoryboardVisualDirectionOutput:
    """Parse structured storyboard visual-direction output."""

    result = _parse_flat_result(text, STORYBOARD_VISUAL_DIRECTION_SPEC)
    try:
        return StoryboardVisualDirectionOutput(
            scene_number=parse_positive_int_field("SCENE_NUMBER", _require_value(result, "SCENE_NUMBER")),
            primary_visual=_require_value(result, "PRIMARY_VISUAL"),
            composition=_require_value(result, "COMPOSITION"),
            motion=_require_value(result, "MOTION"),
            on_screen_text=_require_value(result, "ON_SCREEN_TEXT"),
            style_notes=_require_value(result, "STYLE_NOTES"),
            avoid=_require_value(result, "AVOID"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_storyboard_timing_review(text: str) -> StoryboardTimingReviewOutput:
    """Parse structured storyboard timing-review output."""

    result = _parse_flat_result(text, STORYBOARD_TIMING_REVIEW_SPEC)
    try:
        return StoryboardTimingReviewOutput(
            decision=cast(
                Literal["accept", "revise"],
                parse_literal_field("DECISION", _require_value(result, "DECISION"), ("accept", "revise")),
            ),
            total_duration_assessment=_require_value(result, "TOTAL_DURATION_ASSESSMENT"),
            pacing=_require_value(result, "PACING"),
            scene_issues=_require_value(result, "SCENE_ISSUES"),
            recommendations=_require_value(result, "RECOMMENDATIONS"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def _parse_scene_breakdown_sections(text: str) -> _StoryboardSectionParse:
    """Parse the repeating scene-block storyboard format safely."""

    normalized_text = normalize_model_text(text)
    lines = normalized_text.split("\n")
    index = 0

    if index >= len(lines) or lines[index].strip() != "STORYBOARD_TITLE:":
        raise StructuredOutputError(
            "storyboard output must begin with STORYBOARD_TITLE",
            code="structured_output_invalid",
        )
    index += 1
    storyboard_title, index = _consume_block_value(lines, index)
    if not storyboard_title:
        raise StructuredOutputError(
            "storyboard output contains an invalid field value",
            code="structured_output_invalid",
            details={"field_name": "STORYBOARD_TITLE"},
        )

    scenes: list[StoryboardScenePlan] = []
    seen_scene_numbers: set[int] = set()
    final_scene_count: str | None = None
    total_estimated_duration_seconds: str | None = None

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        scene_match = _SCENE_HEADER_PATTERN.fullmatch(line)
        if scene_match:
            scene_number = parse_positive_int_field("SCENE_NUMBER", scene_match.group(1))
            if scene_number in seen_scene_numbers:
                raise StructuredOutputError(
                    "storyboard output contains duplicate scene numbers",
                    code="structured_output_duplicate_field",
                    details={"field_name": f"SCENE_{scene_number}"},
                )
            if scene_number != len(scenes) + 1:
                raise StructuredOutputError(
                    "storyboard scene numbers must remain sequential",
                    code="structured_output_invalid",
                    details={"field_name": f"SCENE_{scene_number}"},
                )

            scene_fields, index = _parse_scene_fields(lines, index + 1)
            try:
                scenes.append(
                    StoryboardScenePlan(
                        scene_number=scene_number,
                        purpose=scene_fields["PURPOSE"],
                        script_beat=scene_fields["SCRIPT_BEAT"],
                        visual=scene_fields["VISUAL"],
                        on_screen_text=scene_fields["ON_SCREEN_TEXT"],
                        duration_seconds=parse_positive_float_field(
                            "DURATION_SECONDS",
                            scene_fields["DURATION_SECONDS"],
                        ),
                    )
                )
            except ValidationError as error:
                raise wrap_model_validation_error(error) from error
            seen_scene_numbers.add(scene_number)
            continue

        if line == "FINAL_SCENE_COUNT:":
            if final_scene_count is not None:
                raise StructuredOutputError(
                    "storyboard output contains duplicate final scene count",
                    code="structured_output_duplicate_field",
                    details={"field_name": "FINAL_SCENE_COUNT"},
                )
            final_scene_count, index = _consume_block_value(lines, index + 1)
            if not final_scene_count:
                raise StructuredOutputError(
                    "storyboard output contains an invalid field value",
                    code="structured_output_invalid",
                    details={"field_name": "FINAL_SCENE_COUNT"},
                )
            continue

        if line == "TOTAL_ESTIMATED_DURATION_SECONDS:":
            if total_estimated_duration_seconds is not None:
                raise StructuredOutputError(
                    "storyboard output contains duplicate total estimated duration",
                    code="structured_output_duplicate_field",
                    details={"field_name": "TOTAL_ESTIMATED_DURATION_SECONDS"},
                )
            total_estimated_duration_seconds, index = _consume_block_value(lines, index + 1)
            if not total_estimated_duration_seconds:
                raise StructuredOutputError(
                    "storyboard output contains an invalid field value",
                    code="structured_output_invalid",
                    details={"field_name": "TOTAL_ESTIMATED_DURATION_SECONDS"},
                )
            continue

        header_match = _HEADER_PATTERN.fullmatch(line)
        if header_match:
            label = normalize_field_label(header_match.group(1))
            raise StructuredOutputError(
                "storyboard output contains an unknown field",
                code="structured_output_invalid",
                details={"field_name": label},
            )

        raise StructuredOutputError(
            "storyboard output contains malformed content",
            code="structured_output_invalid",
        )

    if final_scene_count is None:
        raise StructuredOutputError(
            "storyboard output is missing a required field",
            code="structured_output_missing_field",
            details={"field_name": "FINAL_SCENE_COUNT"},
        )
    if total_estimated_duration_seconds is None:
        raise StructuredOutputError(
            "storyboard output is missing a required field",
            code="structured_output_missing_field",
            details={"field_name": "TOTAL_ESTIMATED_DURATION_SECONDS"},
        )

    return _StoryboardSectionParse(
        storyboard_title=storyboard_title,
        scenes=tuple(scenes),
        final_scene_count=final_scene_count,
        total_estimated_duration_seconds=total_estimated_duration_seconds,
    )


class _StoryboardSectionParse(CreatorOSModel):
    """Internal typed container for parsed storyboard section blocks."""

    storyboard_title: str
    scenes: tuple[StoryboardScenePlan, ...]
    final_scene_count: str
    total_estimated_duration_seconds: str


def _parse_scene_fields(lines: list[str], start_index: int) -> tuple[dict[str, str], int]:
    """Parse one storyboard scene field block safely."""

    scene_fields: dict[str, str] = {}
    index = start_index

    while index < len(lines):
        stripped_line = lines[index].strip()
        if not stripped_line:
            index += 1
            continue

        if _SCENE_HEADER_PATTERN.fullmatch(stripped_line):
            break
        if stripped_line in {"FINAL_SCENE_COUNT:", "TOTAL_ESTIMATED_DURATION_SECONDS:"}:
            break

        header_match = _HEADER_PATTERN.fullmatch(stripped_line)
        if not header_match:
            raise StructuredOutputError(
                "storyboard scene block contains malformed content",
                code="structured_output_invalid",
            )

        field_name = normalize_field_label(header_match.group(1))
        if field_name not in _SCENE_FIELD_NAMES:
            raise StructuredOutputError(
                "storyboard scene block contains an unknown field",
                code="structured_output_invalid",
                details={"field_name": field_name},
            )
        if field_name in scene_fields:
            raise StructuredOutputError(
                "storyboard scene block contains a duplicate field",
                code="structured_output_duplicate_field",
                details={"field_name": field_name},
            )

        field_value, index = _consume_block_value(lines, index + 1)
        if not field_value:
            raise StructuredOutputError(
                "storyboard scene block contains an invalid field value",
                code="structured_output_invalid",
                details={"field_name": field_name},
            )
        scene_fields[field_name] = field_value

    missing_fields = tuple(field_name for field_name in _SCENE_FIELD_NAMES if field_name not in scene_fields)
    if missing_fields:
        raise StructuredOutputError(
            "storyboard scene block is missing required fields",
            code="structured_output_missing_field",
            details={"field_name": missing_fields[0]},
        )

    return scene_fields, index


def _consume_block_value(lines: list[str], start_index: int) -> tuple[str, int]:
    """Consume a multiline block value until the next header-like line."""

    value_lines: list[str] = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        stripped_line = line.strip()
        if stripped_line and (
            _SCENE_HEADER_PATTERN.fullmatch(stripped_line)
            or stripped_line in {"FINAL_SCENE_COUNT:", "TOTAL_ESTIMATED_DURATION_SECONDS:"}
            or _HEADER_PATTERN.fullmatch(stripped_line)
        ):
            break

        value_lines.append(line)
        index += 1

    return "\n".join(value_lines).strip(), index


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
