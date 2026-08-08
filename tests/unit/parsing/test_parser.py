"""Unit tests for the structured text parser and model adapter."""

from __future__ import annotations

import pytest
from pydantic import Field

from creatoros.core import (
    CreatorOSValidationError,
    DuplicateParsedFieldError,
    StructuredOutputError,
)
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    FieldRequirement,
    ParseStatus,
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParser,
    parse_into_model,
)


class ExampleStructuredModel(CreatorOSModel):
    """Simple model used to verify generic parsed-model adaptation."""

    title: str
    topic: str
    notes: str | None = None


class DurationModel(CreatorOSModel):
    """Model used to verify normal Pydantic validation after parsing."""

    title: str
    estimated_duration_seconds: int = Field(gt=0)


def build_spec(*, allow_unknown_fields: bool = False) -> StructuredOutputSpec:
    """Return a reusable structured output specification for parser tests."""

    return StructuredOutputSpec(
        name="example_output",
        allow_unknown_fields=allow_unknown_fields,
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(name="TOPIC", aliases=("SUBJECT",)),
            StructuredFieldSpec(name="BODY"),
            StructuredFieldSpec(
                name="NOTES",
                requirement=FieldRequirement.OPTIONAL,
            ),
            StructuredFieldSpec(
                name="EMPTY_OPTIONAL",
                requirement=FieldRequirement.OPTIONAL,
                allow_blank=True,
            ),
        ),
    )


def test_simple_single_field_parsing() -> None:
    """The parser should parse a minimal valid structured response."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="single", fields=(StructuredFieldSpec(name="TITLE"),))

    result = parser.parse("TITLE:\nRoblox", spec)

    assert result.status is ParseStatus.SUCCESS
    assert result.get_value("TITLE") == "Roblox"


def test_multiple_fields_parsing() -> None:
    """Multiple canonical fields should parse deterministically."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(
        name="multi",
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(name="TOPIC"),
        ),
    )

    result = parser.parse("TITLE:\nRoblox\nTOPIC:\nfunny myths", spec)

    assert result.status is ParseStatus.SUCCESS
    assert result.get_value("title") == "Roblox"
    assert result.get_value("TOPIC") == "funny myths"


def test_multiline_field_values_preserve_internal_newlines() -> None:
    """Multiline field values should keep meaningful internal newlines."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="body_only", fields=(StructuredFieldSpec(name="BODY"),))

    result = parser.parse("BODY:\nline one\nline two\nline three", spec)

    assert result.get_value("BODY") == "line one\nline two\nline three"


def test_aliases_resolve_to_canonical_fields() -> None:
    """Alias labels should map back to the canonical field name."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(
        name="alias_demo",
        fields=(StructuredFieldSpec(name="TOPIC", aliases=("SUBJECT",)),),
    )

    result = parser.parse("SUBJECT:\ngaming facts", spec)

    assert result.status is ParseStatus.SUCCESS
    assert result.fields["TOPIC"].value == "gaming facts"


def test_optional_field_missing_is_supported_as_partial() -> None:
    """Missing optional fields should produce the narrow supported partial status."""

    parser = StructuredTextParser()
    spec = build_spec()
    text = "TITLE:\nMinecraft\nTOPIC:\ngaming facts\nBODY:\nOne clear point"

    result = parser.parse(text, spec)

    assert result.status is ParseStatus.PARTIAL
    assert result.missing_required_fields == ()
    assert result.unknown_fields == ()
    assert result.get_value("NOTES", required=False) is None


def test_required_field_missing_is_detected() -> None:
    """Missing required fields should return a failed parse result."""

    parser = StructuredTextParser()
    spec = build_spec()
    text = "TITLE:\nMinecraft\nBODY:\nOne clear point"

    result = parser.parse(text, spec)

    assert result.status is ParseStatus.FAILED
    assert result.missing_required_fields == ("TOPIC",)


def test_duplicate_field_is_rejected() -> None:
    """Duplicate canonical fields must not silently overwrite earlier values."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="dup", fields=(StructuredFieldSpec(name="TITLE"),))

    with pytest.raises(DuplicateParsedFieldError) as exc_info:
        parser.parse("TITLE:\nOne\nTITLE:\nTwo", spec)

    assert exc_info.value.code == "structured_output_duplicate_field"
    assert exc_info.value.details == {"field_name": "TITLE"}


def test_canonical_and_alias_duplicate_are_rejected() -> None:
    """A canonical field and one of its aliases should count as a duplicate."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(
        name="dup_alias",
        fields=(StructuredFieldSpec(name="TOPIC", aliases=("SUBJECT",)),),
    )

    with pytest.raises(DuplicateParsedFieldError):
        parser.parse("TOPIC:\nOne\nSUBJECT:\nTwo", spec)


def test_unknown_field_rejected_when_not_allowed() -> None:
    """Unknown field headers should be recorded and fail safely by result status."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="unknown", fields=(StructuredFieldSpec(name="TITLE"),))

    result = parser.parse("TITLE:\nRoblox\nEXTRA:\nunused", spec)

    assert result.status is ParseStatus.FAILED
    assert result.unknown_fields == ("EXTRA",)


def test_unknown_field_is_recorded_but_allowed_when_spec_permits_it() -> None:
    """Allowed unknown fields should be recorded without failing the parse."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(
        name="unknown_allowed",
        allow_unknown_fields=True,
        fields=(StructuredFieldSpec(name="TITLE"),),
    )

    result = parser.parse("TITLE:\nRoblox\nEXTRA:\nunused", spec)

    assert result.status is ParseStatus.SUCCESS
    assert result.unknown_fields == ("EXTRA",)


def test_blank_required_value_is_rejected() -> None:
    """Blank required values should raise a typed structured-output error."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="blank_required", fields=(StructuredFieldSpec(name="TITLE"),))

    with pytest.raises(StructuredOutputError) as exc_info:
        parser.parse("TITLE:\n   ", spec)

    assert exc_info.value.code == "structured_output_invalid"
    assert exc_info.value.details == {"field_name": "TITLE"}


def test_allow_blank_works_for_optional_field() -> None:
    """Optional blank values should be preserved only when explicitly allowed."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(
        name="blank_optional",
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(
                name="NOTES",
                requirement=FieldRequirement.OPTIONAL,
                allow_blank=True,
            ),
        ),
    )

    result = parser.parse("TITLE:\nRoblox\nNOTES:\n", spec)

    assert result.status is ParseStatus.SUCCESS
    assert result.get_value("NOTES", required=False) == ""


def test_blank_optional_value_without_allow_blank_is_rejected_consistently() -> None:
    """Explicit blank optional values should be treated as invalid input."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(
        name="blank_optional_invalid",
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(name="NOTES", requirement=FieldRequirement.OPTIONAL),
        ),
    )

    with pytest.raises(StructuredOutputError):
        parser.parse("TITLE:\nRoblox\nNOTES:\n", spec)


def test_preamble_before_first_field_is_rejected() -> None:
    """Content before the first field header should fail safely."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="preamble", fields=(StructuredFieldSpec(name="TITLE"),))

    with pytest.raises(StructuredOutputError):
        parser.parse("Here is your result\nTITLE:\nRoblox", spec)


def test_code_and_expression_text_remain_inert() -> None:
    """Code-like content should remain inert plain text."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="body_only", fields=(StructuredFieldSpec(name="BODY"),))
    text = "BODY:\n__import__('os').system('echo hacked')"

    result = parser.parse(text, spec)

    assert result.get_value("BODY") == "__import__('os').system('echo hacked')"


def test_braces_remain_inert_text() -> None:
    """Braced content should remain untouched plain text."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="body_only", fields=(StructuredFieldSpec(name="BODY"),))
    text = "BODY:\n{not: executed}"

    result = parser.parse(text, spec)

    assert result.get_value("BODY") == "{not: executed}"


def test_parser_does_not_mutate_spec() -> None:
    """Parsing should not mutate the caller's specification object."""

    parser = StructuredTextParser()
    spec = build_spec()
    original = spec.model_dump()

    parser.parse("TITLE:\nMinecraft\nTOPIC:\nfacts\nBODY:\nOne point", spec)

    assert spec.model_dump() == original


def test_same_input_gives_same_result() -> None:
    """Identical input and spec should produce identical parse results."""

    parser = StructuredTextParser()
    spec = build_spec()
    text = "TITLE:\nMinecraft\nTOPIC:\ngaming facts\nBODY:\nOne point"

    first = parser.parse(text, spec)
    second = parser.parse(text, spec)

    assert first == second


def test_parse_into_model_maps_fields_by_default() -> None:
    """Canonical parsed labels should map to lower_snake_case model fields by default."""

    spec = StructuredOutputSpec(
        name="model_mapping",
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(name="TOPIC"),
            StructuredFieldSpec(
                name="NOTES",
                requirement=FieldRequirement.OPTIONAL,
            ),
        ),
    )

    model = parse_into_model(
        "TITLE:\nRoblox: Funny Myths\nTOPIC:\nfunny myths\nNOTES:\nKeep it short",
        spec=spec,
        model_type=ExampleStructuredModel,
    )

    assert model.title == "Roblox: Funny Myths"
    assert model.topic == "funny myths"
    assert model.notes == "Keep it short"


def test_parse_into_model_explicit_field_mapping_works() -> None:
    """Explicit field mappings should override the default name conversion."""

    spec = StructuredOutputSpec(
        name="explicit_mapping",
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(name="ESTIMATED_DURATION_SECONDS"),
        ),
    )

    model = parse_into_model(
        "TITLE:\nRoblox\nESTIMATED_DURATION_SECONDS:\n30",
        spec=spec,
        model_type=DurationModel,
    )

    assert model.title == "Roblox"
    assert model.estimated_duration_seconds == 30


def test_parse_into_model_safe_validation_failure_contains_no_raw_output() -> None:
    """Model validation failures should stay safe and avoid echoing raw provider text."""

    spec = StructuredOutputSpec(
        name="duration_invalid",
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(name="ESTIMATED_DURATION_SECONDS"),
        ),
    )
    raw_text = "TITLE:\nRoblox\nESTIMATED_DURATION_SECONDS:\n0"

    with pytest.raises(CreatorOSValidationError) as exc_info:
        parse_into_model(raw_text, spec=spec, model_type=DurationModel)

    assert exc_info.value.code == "structured_output_invalid"
    assert exc_info.value.details == {"field_names": ("estimated_duration_seconds",)}
    assert raw_text not in str(exc_info.value)
    assert "Roblox" not in str(exc_info.value)


def test_parse_into_model_rejects_failed_parse_results() -> None:
    """Failed parse results should not be converted into models."""

    spec = StructuredOutputSpec(
        name="failed_result",
        fields=(
            StructuredFieldSpec(name="TITLE"),
            StructuredFieldSpec(name="TOPIC"),
        ),
    )

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_into_model("TITLE:\nRoblox", spec=spec, model_type=ExampleStructuredModel)

    assert exc_info.value.code == "structured_output_invalid"
    assert exc_info.value.details == {"missing_required_fields": ("TOPIC",)}


def test_raw_output_is_not_in_duplicate_or_parse_errors() -> None:
    """Typed parsing exceptions should not include raw structured text."""

    parser = StructuredTextParser()
    spec = StructuredOutputSpec(name="dup", fields=(StructuredFieldSpec(name="TITLE"),))
    raw_text = "TITLE:\nsecret\nTITLE:\nother"

    with pytest.raises(DuplicateParsedFieldError) as exc_info:
        parser.parse(raw_text, spec)

    assert raw_text not in str(exc_info.value)
    assert "secret" not in str(exc_info.value)
