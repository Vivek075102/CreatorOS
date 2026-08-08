"""Unit tests for parsing enums."""

from creatoros.parsing import FieldRequirement, ParseStatus


def test_parse_status_values_are_stable() -> None:
    """ParseStatus should expose the expected stable values."""

    assert ParseStatus.SUCCESS.value == "success"
    assert ParseStatus.PARTIAL.value == "partial"
    assert ParseStatus.FAILED.value == "failed"


def test_field_requirement_values_are_stable() -> None:
    """FieldRequirement should expose the expected stable values."""

    assert FieldRequirement.REQUIRED.value == "required"
    assert FieldRequirement.OPTIONAL.value == "optional"
