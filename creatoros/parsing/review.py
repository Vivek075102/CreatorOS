"""Typed review-output contracts and parsers for builtin CreatorOS prompts."""

from __future__ import annotations

from typing import Literal, cast

from pydantic import ValidationError, field_validator

from creatoros.core import StructuredOutputError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.converters import parse_literal_field, wrap_model_validation_error
from creatoros.parsing.models import (
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)
from creatoros.parsing.parser import StructuredTextParser

GAMING_SCRIPT_QUALITY_REVIEW_SPEC = StructuredOutputSpec(
    name="gaming_script_quality_review_output",
    fields=(
        StructuredFieldSpec(name="DECISION"),
        StructuredFieldSpec(name="SUMMARY"),
        StructuredFieldSpec(name="HOOK_REVIEW"),
        StructuredFieldSpec(name="CLARITY_REVIEW"),
        StructuredFieldSpec(name="STRUCTURE_REVIEW"),
        StructuredFieldSpec(name="FACTUAL_RESTRAINT"),
        StructuredFieldSpec(name="PACING_REVIEW"),
        StructuredFieldSpec(name="ENDING_REVIEW"),
        StructuredFieldSpec(name="ISSUES"),
        StructuredFieldSpec(name="RECOMMENDATIONS"),
    ),
)

GAMING_EVIDENCE_CONSISTENCY_REVIEW_SPEC = StructuredOutputSpec(
    name="gaming_evidence_consistency_review_output",
    fields=(
        StructuredFieldSpec(name="DECISION"),
        StructuredFieldSpec(name="SUMMARY"),
        StructuredFieldSpec(name="SUPPORTED_CLAIMS"),
        StructuredFieldSpec(name="UNSUPPORTED_CLAIMS"),
        StructuredFieldSpec(name="CONTRADICTIONS"),
        StructuredFieldSpec(name="UNCERTAINTIES"),
        StructuredFieldSpec(name="OVERSTATEMENTS"),
        StructuredFieldSpec(name="RECOMMENDATIONS"),
    ),
)

GAMING_STORYBOARD_QUALITY_REVIEW_SPEC = StructuredOutputSpec(
    name="gaming_storyboard_quality_review_output",
    fields=(
        StructuredFieldSpec(name="DECISION"),
        StructuredFieldSpec(name="SUMMARY"),
        StructuredFieldSpec(name="SCRIPT_FIDELITY"),
        StructuredFieldSpec(name="HOOK_SCENE"),
        StructuredFieldSpec(name="SCENE_SEQUENCE"),
        StructuredFieldSpec(name="VISUAL_CLARITY"),
        StructuredFieldSpec(name="PACING"),
        StructuredFieldSpec(name="ENDING_SCENE"),
        StructuredFieldSpec(name="UNSUPPORTED_VISUALS"),
        StructuredFieldSpec(name="ISSUES"),
        StructuredFieldSpec(name="RECOMMENDATIONS"),
    ),
)

GAMING_PUBLICATION_READINESS_REVIEW_SPEC = StructuredOutputSpec(
    name="gaming_publication_readiness_review_output",
    fields=(
        StructuredFieldSpec(name="DECISION"),
        StructuredFieldSpec(name="SUMMARY"),
        StructuredFieldSpec(name="ARTIFACT_ALIGNMENT"),
        StructuredFieldSpec(name="EVIDENCE_STATUS"),
        StructuredFieldSpec(name="MISSING_OR_INCOMPLETE"),
        StructuredFieldSpec(name="BLOCKERS"),
        StructuredFieldSpec(name="NON_BLOCKING_IMPROVEMENTS"),
        StructuredFieldSpec(name="HUMAN_REVIEW_FOCUS"),
    ),
)


def _trim_required_text(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class GamingScriptQualityReviewOutput(CreatorOSModel):
    """Structured advisory output for `gaming_script_quality_review`."""

    decision: Literal["accept", "revise"]
    summary: str
    hook_review: str
    clarity_review: str
    structure_review: str
    factual_restraint: str
    pacing_review: str
    ending_review: str
    issues: str
    recommendations: str

    @field_validator(
        "summary",
        "hook_review",
        "clarity_review",
        "structure_review",
        "factual_restraint",
        "pacing_review",
        "ending_review",
        "issues",
        "recommendations",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank advisory review text."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingEvidenceConsistencyReviewOutput(CreatorOSModel):
    """Structured advisory output for `gaming_evidence_consistency_review`."""

    decision: Literal["consistent", "revise", "insufficient_evidence"]
    summary: str
    supported_claims: str
    unsupported_claims: str
    contradictions: str
    uncertainties: str
    overstatements: str
    recommendations: str

    @field_validator(
        "summary",
        "supported_claims",
        "unsupported_claims",
        "contradictions",
        "uncertainties",
        "overstatements",
        "recommendations",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank advisory review text."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingStoryboardQualityReviewOutput(CreatorOSModel):
    """Structured advisory output for `gaming_storyboard_quality_review`."""

    decision: Literal["accept", "revise"]
    summary: str
    script_fidelity: str
    hook_scene: str
    scene_sequence: str
    visual_clarity: str
    pacing: str
    ending_scene: str
    unsupported_visuals: str
    issues: str
    recommendations: str

    @field_validator(
        "summary",
        "script_fidelity",
        "hook_scene",
        "scene_sequence",
        "visual_clarity",
        "pacing",
        "ending_scene",
        "unsupported_visuals",
        "issues",
        "recommendations",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank advisory review text."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingPublicationReadinessReviewOutput(CreatorOSModel):
    """Structured advisory output for `gaming_publication_readiness_review`."""

    decision: Literal["ready_for_human_review", "revise_before_human_review"]
    summary: str
    artifact_alignment: str
    evidence_status: str
    missing_or_incomplete: str
    blockers: str
    non_blocking_improvements: str
    human_review_focus: str

    @field_validator(
        "summary",
        "artifact_alignment",
        "evidence_status",
        "missing_or_incomplete",
        "blockers",
        "non_blocking_improvements",
        "human_review_focus",
    )
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank advisory review text."""

        return _trim_required_text(value, field_name=info.field_name)


def parse_gaming_script_quality_review(text: str) -> GamingScriptQualityReviewOutput:
    """Parse structured script-quality review output."""

    result = _parse_flat_result(text, GAMING_SCRIPT_QUALITY_REVIEW_SPEC)
    try:
        return GamingScriptQualityReviewOutput(
            decision=cast(
                Literal["accept", "revise"],
                parse_literal_field("DECISION", _require_value(result, "DECISION"), ("accept", "revise")),
            ),
            summary=_require_value(result, "SUMMARY"),
            hook_review=_require_value(result, "HOOK_REVIEW"),
            clarity_review=_require_value(result, "CLARITY_REVIEW"),
            structure_review=_require_value(result, "STRUCTURE_REVIEW"),
            factual_restraint=_require_value(result, "FACTUAL_RESTRAINT"),
            pacing_review=_require_value(result, "PACING_REVIEW"),
            ending_review=_require_value(result, "ENDING_REVIEW"),
            issues=_require_value(result, "ISSUES"),
            recommendations=_require_value(result, "RECOMMENDATIONS"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_evidence_consistency_review(text: str) -> GamingEvidenceConsistencyReviewOutput:
    """Parse structured evidence-consistency review output."""

    result = _parse_flat_result(text, GAMING_EVIDENCE_CONSISTENCY_REVIEW_SPEC)
    try:
        return GamingEvidenceConsistencyReviewOutput(
            decision=cast(
                Literal["consistent", "revise", "insufficient_evidence"],
                parse_literal_field(
                    "DECISION",
                    _require_value(result, "DECISION"),
                    ("consistent", "revise", "insufficient_evidence"),
                ),
            ),
            summary=_require_value(result, "SUMMARY"),
            supported_claims=_require_value(result, "SUPPORTED_CLAIMS"),
            unsupported_claims=_require_value(result, "UNSUPPORTED_CLAIMS"),
            contradictions=_require_value(result, "CONTRADICTIONS"),
            uncertainties=_require_value(result, "UNCERTAINTIES"),
            overstatements=_require_value(result, "OVERSTATEMENTS"),
            recommendations=_require_value(result, "RECOMMENDATIONS"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_storyboard_quality_review(text: str) -> GamingStoryboardQualityReviewOutput:
    """Parse structured storyboard-quality review output."""

    result = _parse_flat_result(text, GAMING_STORYBOARD_QUALITY_REVIEW_SPEC)
    try:
        return GamingStoryboardQualityReviewOutput(
            decision=cast(
                Literal["accept", "revise"],
                parse_literal_field("DECISION", _require_value(result, "DECISION"), ("accept", "revise")),
            ),
            summary=_require_value(result, "SUMMARY"),
            script_fidelity=_require_value(result, "SCRIPT_FIDELITY"),
            hook_scene=_require_value(result, "HOOK_SCENE"),
            scene_sequence=_require_value(result, "SCENE_SEQUENCE"),
            visual_clarity=_require_value(result, "VISUAL_CLARITY"),
            pacing=_require_value(result, "PACING"),
            ending_scene=_require_value(result, "ENDING_SCENE"),
            unsupported_visuals=_require_value(result, "UNSUPPORTED_VISUALS"),
            issues=_require_value(result, "ISSUES"),
            recommendations=_require_value(result, "RECOMMENDATIONS"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_publication_readiness_review(
    text: str,
) -> GamingPublicationReadinessReviewOutput:
    """Parse structured publication-readiness advisory review output."""

    result = _parse_flat_result(text, GAMING_PUBLICATION_READINESS_REVIEW_SPEC)
    try:
        return GamingPublicationReadinessReviewOutput(
            decision=cast(
                Literal["ready_for_human_review", "revise_before_human_review"],
                parse_literal_field(
                    "DECISION",
                    _require_value(result, "DECISION"),
                    ("ready_for_human_review", "revise_before_human_review"),
                ),
            ),
            summary=_require_value(result, "SUMMARY"),
            artifact_alignment=_require_value(result, "ARTIFACT_ALIGNMENT"),
            evidence_status=_require_value(result, "EVIDENCE_STATUS"),
            missing_or_incomplete=_require_value(result, "MISSING_OR_INCOMPLETE"),
            blockers=_require_value(result, "BLOCKERS"),
            non_blocking_improvements=_require_value(result, "NON_BLOCKING_IMPROVEMENTS"),
            human_review_focus=_require_value(result, "HUMAN_REVIEW_FOCUS"),
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
