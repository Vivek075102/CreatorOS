"""Unit tests for parsing text normalization helpers."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.parsing import normalize_field_label, normalize_model_text


def test_normalize_field_label_trims_and_uppercases() -> None:
    """Field labels should normalize into canonical uppercase form."""

    assert normalize_field_label("decision") == "DECISION"
    assert normalize_field_label(" Decision ") == "DECISION"


def test_normalize_field_label_normalizes_spaces_and_hyphens() -> None:
    """Spaces and hyphens should normalize to underscores."""

    assert normalize_field_label("CALL TO ACTION") == "CALL_TO_ACTION"
    assert normalize_field_label("call-to-action") == "CALL_TO_ACTION"


@pytest.mark.parametrize("label", ["", "   ", "a/b", "x.y", "{danger}", "name()"])
def test_invalid_labels_are_rejected(label: str) -> None:
    """Invalid field labels should raise safe validation errors."""

    with pytest.raises(CreatorOSValidationError):
        normalize_field_label(label)


def test_normalize_model_text_removes_bom_and_normalizes_crlf() -> None:
    """Model text normalization should remove BOMs and use LF newlines."""

    text = "\ufeffTITLE:\r\nOne\r\nTwo\r\n"

    assert normalize_model_text(text) == "TITLE:\nOne\nTwo"


def test_normalize_model_text_rejects_blank_text() -> None:
    """Blank structured text should be rejected."""

    with pytest.raises(CreatorOSValidationError):
        normalize_model_text(" \r\n ")


def test_normalize_model_text_requires_string_input() -> None:
    """Only string input should be accepted by the normalizer."""

    with pytest.raises(CreatorOSValidationError):
        normalize_model_text(123)  # type: ignore[arg-type]
