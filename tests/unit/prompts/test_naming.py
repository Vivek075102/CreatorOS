"""Unit tests for prompt asset filename parsing and construction."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.prompts import build_prompt_asset_filename, parse_prompt_asset_filename


def test_valid_canonical_filenames_parse() -> None:
    """Canonical prompt asset filenames should parse correctly."""

    parsed = parse_prompt_asset_filename("discover_trends.v1.json")

    assert parsed.name == "discover_trends"
    assert parsed.version == 1
    assert parsed.filename == "discover_trends.v1.json"


def test_multi_digit_versions_parse() -> None:
    """Multi-digit prompt asset versions should parse correctly."""

    parsed = parse_prompt_asset_filename("youtube_shorts_script.v12.json")

    assert parsed.name == "youtube_shorts_script"
    assert parsed.version == 12


@pytest.mark.parametrize(
    "filename",
    [
        "Discover_Trends.v1.json",
        "discover trends.v1.json",
        "discover-trends.v1.json",
        "discover_trends.v0.json",
        "discover_trends.json",
        "discover_trends.v1.json.bak",
        ".discover_trends.v1.json",
    ],
)
def test_invalid_filenames_are_rejected(filename: str) -> None:
    """Invalid prompt asset filenames should be rejected safely."""

    with pytest.raises(CreatorOSValidationError) as exc_info:
        parse_prompt_asset_filename(filename)

    assert exc_info.value.code == "prompt_asset_invalid_filename"
    assert exc_info.value.details == {"filename": filename}


def test_build_and_parse_round_trip() -> None:
    """Building and parsing should round-trip the canonical asset identity."""

    filename = build_prompt_asset_filename("storyboard_scene_breakdown", 7)
    parsed = parse_prompt_asset_filename(filename)

    assert filename == "storyboard_scene_breakdown.v7.json"
    assert parsed.name == "storyboard_scene_breakdown"
    assert parsed.version == 7
