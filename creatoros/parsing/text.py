"""Safe text normalization helpers for provider-independent structured parsing."""

from __future__ import annotations

import re

from creatoros.core import CreatorOSValidationError

_SEPARATOR_PATTERN = re.compile(r"[\s-]+")
_UNDERSCORE_PATTERN = re.compile(r"_+")
_VALID_LABEL_PATTERN = re.compile(r"^[A-Z0-9_]+$")


def normalize_field_label(label: str) -> str:
    """Normalize a field label into CreatorOS canonical uppercase form."""

    if not isinstance(label, str):
        raise CreatorOSValidationError(
            "field label must be a string",
            code="structured_output_invalid",
        )

    normalized_label = label.strip()
    if not normalized_label:
        raise CreatorOSValidationError(
            "field label must not be blank",
            code="structured_output_invalid",
        )

    normalized_label = _SEPARATOR_PATTERN.sub("_", normalized_label.upper())
    normalized_label = _UNDERSCORE_PATTERN.sub("_", normalized_label).strip("_")

    if not normalized_label or not _VALID_LABEL_PATTERN.fullmatch(normalized_label):
        raise CreatorOSValidationError(
            "field label contains invalid characters",
            code="structured_output_invalid",
        )

    return normalized_label


def normalize_model_text(text: str) -> str:
    """Normalize untrusted model text into a deterministic LF-only representation."""

    if not isinstance(text, str):
        raise CreatorOSValidationError(
            "structured text must be a string",
            code="structured_output_invalid",
        )

    normalized_text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_text:
        raise CreatorOSValidationError(
            "structured text must not be blank",
            code="structured_output_invalid",
        )

    return normalized_text
