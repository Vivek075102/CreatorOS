"""Enumerations used by the structured-output parsing subsystem."""

from enum import StrEnum


class ParseStatus(StrEnum):
    """Outcome categories for structured text parsing."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class FieldRequirement(StrEnum):
    """Whether a parsed field must be present in structured output."""

    REQUIRED = "required"
    OPTIONAL = "optional"
