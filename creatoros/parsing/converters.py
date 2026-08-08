"""Focused safe conversion helpers for structured-output parser adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from pydantic import ValidationError

from creatoros.core import StructuredOutputError, StructuredValueError


def parse_int_field(field_name: str, value: str) -> int:
    """Convert a parsed field value into an integer safely."""

    normalized_value = value.strip()
    try:
        return int(normalized_value)
    except ValueError as error:
        raise StructuredValueError(field_name, expected_type="integer") from error


def parse_literal_field(field_name: str, value: str, allowed_values: Iterable[str]) -> str:
    """Convert a parsed field value into one of a fixed set of safe literal values."""

    normalized_value = value.strip().lower()
    allowed = tuple(allowed_values)
    if normalized_value not in allowed:
        raise StructuredValueError(field_name, expected_type="literal")
    return normalized_value


def parse_bullet_list(field_name: str, value: str) -> tuple[str, ...]:
    """Parse a simple bullet-list field into an immutable ordered tuple.

    Duplicate items are rejected rather than silently removed so the structured
    output contract stays explicit and lossless.
    """

    normalized_value = value.strip()
    if not normalized_value:
        return ()

    items: list[str] = []
    seen_items: set[str] = set()
    for line in normalized_value.split("\n"):
        stripped_line = line.strip()
        if not stripped_line.startswith("-"):
            raise StructuredValueError(field_name, expected_type="simple_bullet_list")

        bullet_value = stripped_line[1:].strip()
        if not bullet_value:
            raise StructuredValueError(field_name, expected_type="simple_bullet_list")
        if bullet_value in seen_items:
            raise StructuredValueError(field_name, expected_type="unique_simple_bullet_list")

        items.append(bullet_value)
        seen_items.add(bullet_value)

    return tuple(items)


def wrap_model_validation_error(error: ValidationError) -> StructuredOutputError:
    """Convert model validation failures into a safe structured-output error."""

    field_names: set[str] = set()
    for item in error.errors():
        location = item.get("loc", ())
        if location and isinstance(location[0], str):
            field_names.add(cast(str, location[0]))

    return StructuredOutputError(
        "structured output model validation failed",
        code="structured_output_invalid",
        details={"field_names": tuple(sorted(field_names))},
    )
