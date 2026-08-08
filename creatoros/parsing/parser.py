"""Provider-independent parsing of structured label/value text into CreatorOS models."""

from __future__ import annotations

import re

from pydantic import ValidationError

from creatoros.core import (
    CreatorOSValidationError,
    DuplicateParsedFieldError,
    StructuredOutputError,
)
from creatoros.domain import CreatorOSModel
from creatoros.parsing.enums import FieldRequirement, ParseStatus
from creatoros.parsing.models import (
    ParsedField,
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)
from creatoros.parsing.text import normalize_field_label, normalize_model_text

_HEADER_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 _-]*):$")


class StructuredTextParser:
    """Parse deterministic label/value text into validated structured field results."""

    def parse(
        self,
        text: str,
        spec: StructuredOutputSpec,
    ) -> StructuredTextParseResult:
        """Parse structured text according to the supplied output specification.

        `ParseStatus.PARTIAL` is reserved for the narrow case where all required
        fields are valid but one or more optional fields are absent. Structural
        corruption such as duplicate fields, explicit invalid blanks, or preamble
        content raises typed parsing exceptions instead of returning a result.
        """

        normalized_text = normalize_model_text(text)
        lines = normalized_text.split("\n")

        parsed_values: dict[str, str] = {}
        unknown_fields: list[str] = []
        current_label: str | None = None
        current_lines: list[str] = []
        seen_any_header = False

        def finalize_current_field() -> None:
            nonlocal current_label, current_lines
            if current_label is None:
                return

            normalized_value = "\n".join(current_lines).strip()
            resolved_name = spec.resolve_field_name(current_label)
            if resolved_name is None:
                if current_label not in unknown_fields:
                    unknown_fields.append(current_label)
            else:
                field_spec = _get_field_spec(spec, resolved_name)
                if not normalized_value and not field_spec.allow_blank:
                    raise StructuredOutputError(
                        "parsed field value is invalid",
                        code="structured_output_invalid",
                        details={"field_name": resolved_name},
                    )
                if resolved_name in parsed_values:
                    raise DuplicateParsedFieldError(resolved_name)
                parsed_values[resolved_name] = normalized_value

            current_label = None
            current_lines = []

        for line in lines:
            header_match = _HEADER_PATTERN.fullmatch(line)
            if header_match:
                finalize_current_field()
                seen_any_header = True
                current_label = normalize_field_label(header_match.group(1))
                current_lines = []
                continue

            if not seen_any_header:
                raise StructuredOutputError(
                    "structured output must begin with a recognized field header",
                    code="structured_output_invalid",
                )

            if current_label is None:
                raise StructuredOutputError(
                    "structured output encountered invalid field state",
                    code="structured_output_invalid",
                )

            current_lines.append(line)

        finalize_current_field()

        missing_required_fields = [
            field_name for field_name in spec.required_field_names if field_name not in parsed_values
        ]

        parsed_fields: dict[str, ParsedField] = {}
        optional_absent = False
        for field_spec in spec.fields:
            value = parsed_values.get(field_spec.name)
            present = field_spec.name in parsed_values
            if not present and field_spec.requirement is FieldRequirement.OPTIONAL:
                optional_absent = True
            parsed_fields[field_spec.name] = ParsedField(
                name=field_spec.name,
                value=value,
                requirement=field_spec.requirement,
                present=present,
                metadata={"aliases": field_spec.aliases},
            )

        if missing_required_fields or (unknown_fields and not spec.allow_unknown_fields):
            status = ParseStatus.FAILED
        elif optional_absent:
            status = ParseStatus.PARTIAL
        else:
            status = ParseStatus.SUCCESS

        return StructuredTextParseResult(
            status=status,
            fields=parsed_fields,
            missing_required_fields=tuple(missing_required_fields),
            unknown_fields=tuple(unknown_fields),
            raw_length=len(normalized_text),
            metadata={
                "spec_name": spec.name,
                "allow_unknown_fields": spec.allow_unknown_fields,
            },
        )


def parse_into_model[T: CreatorOSModel](
    text: str,
    *,
    spec: StructuredOutputSpec,
    model_type: type[T],
    field_mapping: dict[str, str] | None = None,
) -> T:
    """Parse structured text and validate it into a typed CreatorOS model."""

    parser = StructuredTextParser()
    result = parser.parse(text, spec)

    if result.status is ParseStatus.FAILED:
        details: dict[str, object] = {}
        if result.missing_required_fields:
            details["missing_required_fields"] = result.missing_required_fields
        if result.unknown_fields and not spec.allow_unknown_fields:
            details["unknown_fields"] = result.unknown_fields
        raise StructuredOutputError(
            "structured output could not be mapped into a model",
            code="structured_output_invalid",
            details=details,
        )

    normalized_mapping = {
        normalize_field_label(key): value for key, value in (field_mapping or {}).items()
    }

    payload: dict[str, str] = {}
    for field_name, parsed_field in result.fields.items():
        if not parsed_field.present:
            continue

        model_field_name = normalized_mapping.get(field_name, field_name.lower())
        if parsed_field.value is None:
            continue
        payload[model_field_name] = parsed_field.value

    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        field_names = tuple(_extract_validation_field_names(error))
        raise CreatorOSValidationError(
            "parsed model validation failed",
            code="structured_output_invalid",
            details={"field_names": field_names},
        ) from error


def _get_field_spec(spec: StructuredOutputSpec, name: str) -> StructuredFieldSpec:
    """Return the matching field spec for a canonical field name."""

    for field_spec in spec.fields:
        if field_spec.name == name:
            return field_spec
    raise StructuredOutputError(
        "structured output specification is inconsistent",
        code="structured_output_invalid",
        details={"field_name": name},
    )


def _extract_validation_field_names(error: ValidationError) -> list[str]:
    """Return safe normalized field names from a Pydantic validation error."""

    field_names: list[str] = []
    for item in error.errors():
        location = item.get("loc", ())
        if not location:
            continue
        first_part = location[0]
        if isinstance(first_part, str):
            field_names.append(first_part)
    return sorted(set(field_names))
