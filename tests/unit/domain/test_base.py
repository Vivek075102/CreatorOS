"""Unit tests for shared domain model helpers."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from creatoros.domain.base import CreatorOSModel, generate_id, utc_now


class ExampleModel(CreatorOSModel):
    """Minimal test model for base configuration behavior."""

    count: int


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    """utc_now should return a timezone-aware UTC datetime."""

    value = utc_now()

    assert value.tzinfo is not None
    assert value.utcoffset() == UTC.utcoffset(value)


def test_generate_id_produces_expected_prefix_and_uuid_shaped_suffix() -> None:
    """Generated identifiers should use the normalized prefix and UUID4 hex suffix."""

    value = generate_id("job")
    prefix, suffix = value.split("_", maxsplit=1)

    assert prefix == "job"
    assert len(suffix) == 32
    assert all(character in "0123456789abcdef" for character in suffix)


def test_generate_id_normalizes_spaces_and_hyphens() -> None:
    """Spaces and hyphens in prefixes should normalize to underscores."""

    value = generate_id("Step Result")
    prefix, suffix = value.rsplit("_", maxsplit=1)

    assert prefix == "step_result"
    assert len(suffix) == 32


@pytest.mark.parametrize("prefix", ["", "   ", "@@@", "job/result"])
def test_generate_id_rejects_blank_or_invalid_prefixes(prefix: str) -> None:
    """Blank or invalid prefixes should be rejected."""

    with pytest.raises(ValueError):
        generate_id(prefix)


def test_creatoros_model_rejects_unknown_fields() -> None:
    """Base domain models should reject unknown fields."""

    with pytest.raises(ValidationError):
        ExampleModel(count=1, unknown=True)


def test_creatoros_model_validates_assignment() -> None:
    """Base domain models should validate assignment updates."""

    model = ExampleModel(count=1)

    with pytest.raises(ValidationError):
        model.count = "invalid"
