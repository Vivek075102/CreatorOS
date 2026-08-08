"""Typed script-output contracts and parsers for builtin CreatorOS prompts."""

from __future__ import annotations

from pydantic import Field, ValidationError, field_validator, model_validator

from creatoros.core import StructuredOutputError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.converters import parse_int_field, wrap_model_validation_error
from creatoros.parsing.models import (
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)
from creatoros.parsing.parser import StructuredTextParser

YOUTUBE_SHORTS_SCRIPT_SPEC = StructuredOutputSpec(
    name="youtube_shorts_script_output",
    fields=(
        StructuredFieldSpec(name="TITLE"),
        StructuredFieldSpec(name="HOOK"),
        StructuredFieldSpec(name="BODY"),
        StructuredFieldSpec(name="ENDING"),
        StructuredFieldSpec(name="CALL_TO_ACTION"),
        StructuredFieldSpec(name="ESTIMATED_DURATION_SECONDS"),
        StructuredFieldSpec(name="EVIDENCE_NOTE"),
    ),
)

GAMING_HOOK_SPEC = StructuredOutputSpec(
    name="gaming_hook_output",
    fields=(
        StructuredFieldSpec(name="HOOK_1"),
        StructuredFieldSpec(name="HOOK_2"),
        StructuredFieldSpec(name="HOOK_3"),
        StructuredFieldSpec(name="BEST_HOOK"),
        StructuredFieldSpec(name="WHY"),
    ),
)

GAMING_CTA_SPEC = StructuredOutputSpec(
    name="gaming_cta_output",
    fields=(
        StructuredFieldSpec(name="CTA"),
        StructuredFieldSpec(name="ALTERNATIVE"),
    ),
)


def _trim_required_text(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


class YouTubeShortsScriptOutput(CreatorOSModel):
    """Validated output contract for `youtube_shorts_script`."""

    title: str
    hook: str
    body: str
    ending: str
    call_to_action: str
    estimated_duration_seconds: int = Field(gt=0)
    evidence_note: str

    @field_validator("title", "hook", "body", "ending", "call_to_action", "evidence_note")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


class GamingHookOutput(CreatorOSModel):
    """Validated output contract for `gaming_hook`."""

    hook_1: str
    hook_2: str
    hook_3: str
    best_hook: str
    why: str

    @field_validator("hook_1", "hook_2", "hook_3", "best_hook", "why")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_best_hook(self) -> GamingHookOutput:
        """Require `best_hook` to match one of the supplied candidates exactly."""

        if self.best_hook not in {self.hook_1, self.hook_2, self.hook_3}:
            raise ValueError("best_hook must match one of hook_1, hook_2, or hook_3")
        return self


class GamingCTAOutput(CreatorOSModel):
    """Validated output contract for `gaming_cta`."""

    cta: str
    alternative: str

    @field_validator("cta", "alternative")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank required output strings."""

        return _trim_required_text(value, field_name=info.field_name)


def parse_youtube_shorts_script(text: str) -> YouTubeShortsScriptOutput:
    """Parse structured YouTube Shorts script output into a validated typed model."""

    result = _parse_result(text, YOUTUBE_SHORTS_SCRIPT_SPEC)
    try:
        return YouTubeShortsScriptOutput(
            title=_require_value(result, "TITLE"),
            hook=_require_value(result, "HOOK"),
            body=_require_value(result, "BODY"),
            ending=_require_value(result, "ENDING"),
            call_to_action=_require_value(result, "CALL_TO_ACTION"),
            estimated_duration_seconds=parse_int_field(
                "ESTIMATED_DURATION_SECONDS",
                _require_value(result, "ESTIMATED_DURATION_SECONDS"),
            ),
            evidence_note=_require_value(result, "EVIDENCE_NOTE"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_hook(text: str) -> GamingHookOutput:
    """Parse structured gaming hook output into a validated typed model."""

    result = _parse_result(text, GAMING_HOOK_SPEC)
    try:
        return GamingHookOutput(
            hook_1=_require_value(result, "HOOK_1"),
            hook_2=_require_value(result, "HOOK_2"),
            hook_3=_require_value(result, "HOOK_3"),
            best_hook=_require_value(result, "BEST_HOOK"),
            why=_require_value(result, "WHY"),
        )
    except ValidationError as error:
        raise wrap_model_validation_error(error) from error


def parse_gaming_cta(text: str) -> GamingCTAOutput:
    """Parse structured gaming CTA output into a validated typed model."""

    result = _parse_result(text, GAMING_CTA_SPEC)
    try:
        return GamingCTAOutput(
            cta=_require_value(result, "CTA"),
            alternative=_require_value(result, "ALTERNATIVE"),
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
