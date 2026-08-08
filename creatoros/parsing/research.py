"""Typed research-output contracts and parsers for builtin CreatorOS prompts."""

from __future__ import annotations

from typing import Literal, cast

from pydantic import Field, ValidationError, field_validator

from creatoros.core import StructuredOutputError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.converters import (
    parse_bullet_list,
    parse_int_field,
    parse_literal_field,
    wrap_model_validation_error,
)
from creatoros.parsing.models import (
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)
from creatoros.parsing.parser import StructuredTextParser

GAMING_TREND_DISCOVERY_SPEC = StructuredOutputSpec(
    name="gaming_discover_trends_output",
    fields=(
        StructuredFieldSpec(name="TITLE"),
        StructuredFieldSpec(name="GAME"),
        StructuredFieldSpec(name="TOPIC"),
        StructuredFieldSpec(name="ANGLE"),
        StructuredFieldSpec(name="WHY_NOW"),
        StructuredFieldSpec(name="SOURCE_SUMMARY"),
        StructuredFieldSpec(name="CONFIDENCE"),
    ),
)

GAMING_OPPORTUNITY_EVALUATION_SPEC = StructuredOutputSpec(
    name="gaming_evaluate_opportunity_output",
    fields=(
        StructuredFieldSpec(name="DECISION"),
        StructuredFieldSpec(name="SCORE"),
        StructuredFieldSpec(name="STRENGTHS"),
        StructuredFieldSpec(name="RISKS"),
        StructuredFieldSpec(name="RECOMMENDED_ANGLE"),
        StructuredFieldSpec(name="HOOK_DIRECTION"),
        StructuredFieldSpec(name="REASON"),
    ),
)

GAMING_KEYWORD_EXPANSION_SPEC = StructuredOutputSpec(
    name="gaming_expand_keywords_output",
    fields=(
        StructuredFieldSpec(name="PRIMARY"),
        StructuredFieldSpec(name="RELATED", allow_blank=True),
        StructuredFieldSpec(name="QUESTIONS", allow_blank=True),
        StructuredFieldSpec(name="ENTITIES", allow_blank=True),
    ),
)


def _trim_required_text(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class GamingTrendDiscoveryOutput(CreatorOSModel):
    """Validated output contract for `gaming_discover_trends`."""

    title: str
    game: str
    topic: str
    angle: str
    why_now: str
    source_summary: str
    confidence: Literal["low", "medium", "high"]

    @field_validator("title", "game", "topic", "angle", "why_now", "source_summary")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingOpportunityEvaluationOutput(CreatorOSModel):
    """Validated output contract for `gaming_evaluate_opportunity`."""

    decision: Literal["accept", "revise", "reject"]
    score: int = Field(ge=0, le=100)
    strengths: str
    risks: str
    recommended_angle: str
    hook_direction: str
    reason: str

    @field_validator(
        "strengths",
        "risks",
        "recommended_angle",
        "hook_direction",
        "reason",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingKeywordExpansionOutput(CreatorOSModel):
    """Validated output contract for `gaming_expand_keywords`.

    Duplicate list items are rejected rather than silently removed so the parsed
    research output remains lossless and explicit.
    """

    primary: tuple[str, ...]
    related: tuple[str, ...]
    questions: tuple[str, ...]
    entities: tuple[str, ...]

    @field_validator("primary", "related", "questions", "entities")
    @classmethod
    def validate_items(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        """Trim tuple items, reject blanks, and preserve order."""

        normalized_items: list[str] = []
        seen_items: set[str] = set()
        for item in value:
            normalized_item = item.strip()
            if not normalized_item:
                raise ValueError(f"{info.field_name} items must not be blank")
            if normalized_item in seen_items:
                raise ValueError(f"{info.field_name} items must be unique")
            normalized_items.append(normalized_item)
            seen_items.add(normalized_item)
        return tuple(normalized_items)

    @field_validator("primary")
    @classmethod
    def validate_primary_not_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require at least one primary keyword."""

        if not value:
            raise ValueError("primary must contain at least one item")
        return value


def parse_gaming_trend_discovery(text: str) -> GamingTrendDiscoveryOutput:
    """Parse structured trend-discovery output into a validated typed model."""

    result = _parse_result(text, GAMING_TREND_DISCOVERY_SPEC)
    try:
        return GamingTrendDiscoveryOutput(
            title=_require_value(result, "TITLE"),
            game=_require_value(result, "GAME"),
            topic=_require_value(result, "TOPIC"),
            angle=_require_value(result, "ANGLE"),
            why_now=_require_value(result, "WHY_NOW"),
            source_summary=_require_value(result, "SOURCE_SUMMARY"),
            confidence=cast(
                Literal["low", "medium", "high"],
                parse_literal_field(
                    "CONFIDENCE",
                    _require_value(result, "CONFIDENCE"),
                    ("low", "medium", "high"),
                ),
            ),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_opportunity_evaluation(text: str) -> GamingOpportunityEvaluationOutput:
    """Parse structured opportunity-evaluation output into a validated typed model."""

    result = _parse_result(text, GAMING_OPPORTUNITY_EVALUATION_SPEC)
    try:
        return GamingOpportunityEvaluationOutput(
            decision=cast(
                Literal["accept", "revise", "reject"],
                parse_literal_field(
                    "DECISION",
                    _require_value(result, "DECISION"),
                    ("accept", "revise", "reject"),
                ),
            ),
            score=parse_int_field("SCORE", _require_value(result, "SCORE")),
            strengths=_require_value(result, "STRENGTHS"),
            risks=_require_value(result, "RISKS"),
            recommended_angle=_require_value(result, "RECOMMENDED_ANGLE"),
            hook_direction=_require_value(result, "HOOK_DIRECTION"),
            reason=_require_value(result, "REASON"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_keyword_expansion(text: str) -> GamingKeywordExpansionOutput:
    """Parse structured keyword-expansion output into a validated typed model."""

    result = _parse_result(text, GAMING_KEYWORD_EXPANSION_SPEC)
    try:
        return GamingKeywordExpansionOutput(
            primary=parse_bullet_list("PRIMARY", _require_value(result, "PRIMARY")),
            related=parse_bullet_list("RELATED", _require_value(result, "RELATED")),
            questions=parse_bullet_list("QUESTIONS", _require_value(result, "QUESTIONS")),
            entities=parse_bullet_list("ENTITIES", _require_value(result, "ENTITIES")),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def _parse_result(text: str, spec: StructuredOutputSpec) -> StructuredTextParseResult:
    """Parse text and reject failed results safely."""

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
