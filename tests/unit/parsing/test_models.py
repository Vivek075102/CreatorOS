"""Unit tests for structured-output parsing models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from creatoros.core import CreatorOSValidationError
from creatoros.parsing import (
    FieldRequirement,
    ParsedField,
    ParseStatus,
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)


def build_field_spec(
    name: str = "TITLE",
    *,
    requirement: FieldRequirement = FieldRequirement.REQUIRED,
    allow_blank: bool = False,
    aliases: tuple[str, ...] = (),
) -> StructuredFieldSpec:
    """Return a reusable structured field specification."""

    return StructuredFieldSpec(
        name=name,
        requirement=requirement,
        allow_blank=allow_blank,
        aliases=aliases,
    )


def test_parsed_field_normalizes_name_and_value() -> None:
    """ParsedField should normalize labels and trim surrounding value whitespace."""

    field = ParsedField(name=" decision ", value="  accept\nwith caution  ", present=True)

    assert field.name == "DECISION"
    assert field.value == "accept\nwith caution"


def test_parsed_field_requires_value_when_present() -> None:
    """Present parsed fields must provide a non-None value."""

    with pytest.raises(ValidationError):
        ParsedField(name="TITLE", present=True)


def test_parsed_field_mutable_defaults_are_isolated() -> None:
    """ParsedField metadata dictionaries should not be shared."""

    first = ParsedField(name="TITLE")
    second = ParsedField(name="TOPIC")
    first.metadata["demo"] = True

    assert second.metadata == {}


def test_structured_field_spec_normalizes_aliases() -> None:
    """Field spec aliases should normalize into canonical uppercase labels."""

    spec = build_field_spec(name="call to action", aliases=("cta", "closing prompt"))

    assert spec.name == "CALL_TO_ACTION"
    assert spec.aliases == ("CTA", "CLOSING_PROMPT")


def test_structured_field_spec_rejects_duplicate_aliases() -> None:
    """Duplicate normalized aliases should be rejected."""

    with pytest.raises(ValidationError):
        build_field_spec(aliases=("topic", "TOPIC"))


def test_structured_field_spec_rejects_canonical_name_as_alias() -> None:
    """Canonical field names must not also appear as aliases."""

    with pytest.raises(ValidationError):
        build_field_spec(name="topic", aliases=("TOPIC",))


def test_structured_output_spec_requires_at_least_one_field() -> None:
    """Structured output specs must declare at least one field."""

    with pytest.raises(ValidationError):
        StructuredOutputSpec(name="review", fields=())


def test_structured_output_spec_rejects_alias_collisions() -> None:
    """Aliases must not collide across field specifications."""

    with pytest.raises(ValidationError):
        StructuredOutputSpec(
            name="review",
            fields=(
                build_field_spec(name="TITLE", aliases=("NAME",)),
                build_field_spec(name="TOPIC", aliases=("name",)),
            ),
        )


def test_structured_output_spec_resolves_canonical_names_and_aliases() -> None:
    """Specs should resolve both canonical labels and aliases."""

    spec = StructuredOutputSpec(
        name="review",
        fields=(build_field_spec(name="CALL TO ACTION", aliases=("cta",)),),
    )

    assert spec.resolve_field_name("CALL TO ACTION") == "CALL_TO_ACTION"
    assert spec.resolve_field_name("cta") == "CALL_TO_ACTION"
    assert spec.resolve_field_name("missing") is None


def test_required_field_names_are_immutable() -> None:
    """Required field names should be exposed through a frozenset."""

    spec = StructuredOutputSpec(
        name="review",
        fields=(
            build_field_spec(name="TITLE"),
            build_field_spec(name="NOTES", requirement=FieldRequirement.OPTIONAL),
        ),
    )

    assert spec.required_field_names == frozenset({"TITLE"})
    with pytest.raises(AttributeError):
        spec.required_field_names.add("OTHER")  # type: ignore[attr-defined]


def test_parse_result_normalizes_names_and_get_value() -> None:
    """Parse results should normalize names and expose safe lookup helpers."""

    result = StructuredTextParseResult(
        status=ParseStatus.SUCCESS,
        fields={"title": ParsedField(name="title", value="Roblox", present=True)},
        raw_length=10,
    )

    assert result.fields["TITLE"].name == "TITLE"
    assert result.get_value(" title ") == "Roblox"


def test_get_value_missing_required_raises_safe_error() -> None:
    """Missing required parsed fields should raise safe validation errors."""

    result = StructuredTextParseResult(
        status=ParseStatus.PARTIAL,
        fields={"TITLE": ParsedField(name="TITLE", value="Roblox", present=True)},
        raw_length=10,
    )

    with pytest.raises(CreatorOSValidationError) as exc_info:
        result.get_value("body")

    assert exc_info.value.code == "parsed_field_missing"
    assert exc_info.value.details == {"field_name": "BODY"}
    assert "Roblox" not in str(exc_info.value)


def test_parse_result_serializes_and_restores() -> None:
    """Parse results should round-trip predictably through Pydantic."""

    result = StructuredTextParseResult(
        status=ParseStatus.SUCCESS,
        fields={
            "TITLE": ParsedField(
                name="TITLE",
                value="Minecraft: Gaming Facts",
                present=True,
            )
        },
        raw_length=32,
        metadata={"spec_name": "demo"},
    )

    restored = StructuredTextParseResult.model_validate(result.model_dump())

    assert restored == result


def test_parse_result_mutable_defaults_are_isolated() -> None:
    """Parse result metadata dictionaries should not be shared."""

    first = StructuredTextParseResult(status=ParseStatus.SUCCESS, fields={}, raw_length=0)
    second = StructuredTextParseResult(status=ParseStatus.SUCCESS, fields={}, raw_length=0)
    first.metadata["demo"] = True

    assert second.metadata == {}
