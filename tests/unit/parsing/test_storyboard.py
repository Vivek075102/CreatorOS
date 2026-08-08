"""Unit tests for typed storyboard-output parsers."""

from __future__ import annotations

import pytest

from creatoros.core import StructuredOutputError, StructuredValueError
from creatoros.parsing import (
    StoryboardSceneBreakdownOutput,
    StoryboardTimingReviewOutput,
    StoryboardVisualDirectionOutput,
    parse_storyboard_scene_breakdown,
    parse_storyboard_timing_review,
    parse_storyboard_visual_direction,
)


def _scene_breakdown_text(*, total_duration: str = "30", final_scene_count: str = "2") -> str:
    """Return a reusable valid storyboard scene-breakdown payload."""

    return (
        "STORYBOARD_TITLE:\nMinecraft: Hidden Mechanics\n"
        "SCENE_1:\n"
        "PURPOSE:\nOpen with the hook.\n"
        "SCRIPT_BEAT:\nIntroduce the overlooked mechanic.\n"
        "VISUAL:\nClose-up gameplay view of the mechanic in action.\n"
        "ON_SCREEN_TEXT:\nHidden mechanic?\n"
        "DURATION_SECONDS:\n8\n"
        "SCENE_2:\n"
        "PURPOSE:\nResolve the claim clearly.\n"
        "SCRIPT_BEAT:\nExplain what the supplied evidence actually supports.\n"
        "VISUAL:\nShow the mechanic outcome with simple comparison framing.\n"
        "ON_SCREEN_TEXT:\nWhat the evidence supports\n"
        f"DURATION_SECONDS:\n22\n"
        f"FINAL_SCENE_COUNT:\n{final_scene_count}\n"
        f"TOTAL_ESTIMATED_DURATION_SECONDS:\n{total_duration}"
    )


def test_valid_scene_breakdown_parses() -> None:
    """A valid scene breakdown should parse into the typed output model."""

    parsed = parse_storyboard_scene_breakdown(_scene_breakdown_text())

    assert isinstance(parsed, StoryboardSceneBreakdownOutput)
    assert parsed.storyboard_title == "Minecraft: Hidden Mechanics"
    assert len(parsed.scenes) == 2
    assert parsed.final_scene_count == 2
    assert parsed.total_estimated_duration_seconds == 30.0


def test_three_scene_output_parses() -> None:
    """A three-scene storyboard should parse successfully."""

    text = (
        "STORYBOARD_TITLE:\nMinecraft: Hidden Mechanics\n"
        "SCENE_1:\nPURPOSE:\nHook.\nSCRIPT_BEAT:\nBeat one.\nVISUAL:\nVisual one.\nON_SCREEN_TEXT:\nText one.\nDURATION_SECONDS:\n7\n"
        "SCENE_2:\nPURPOSE:\nExplain.\nSCRIPT_BEAT:\nBeat two.\nVISUAL:\nVisual two.\nON_SCREEN_TEXT:\nText two.\nDURATION_SECONDS:\n10\n"
        "SCENE_3:\nPURPOSE:\nResolve.\nSCRIPT_BEAT:\nBeat three.\nVISUAL:\nVisual three.\nON_SCREEN_TEXT:\nText three.\nDURATION_SECONDS:\n13\n"
        "FINAL_SCENE_COUNT:\n3\n"
        "TOTAL_ESTIMATED_DURATION_SECONDS:\n30"
    )

    parsed = parse_storyboard_scene_breakdown(text)

    assert tuple(scene.scene_number for scene in parsed.scenes) == (1, 2, 3)


def test_multiline_scene_values_are_preserved() -> None:
    """Scene block values should preserve meaningful internal newlines."""

    text = _scene_breakdown_text().replace(
        "Close-up gameplay view of the mechanic in action.",
        "Close-up gameplay view.\nSecond descriptive line.",
    )

    parsed = parse_storyboard_scene_breakdown(text)

    assert parsed.scenes[0].visual == "Close-up gameplay view.\nSecond descriptive line."


def test_scene_numbers_are_sequential() -> None:
    """Scene numbers should remain sequential starting from one."""

    parsed = parse_storyboard_scene_breakdown(_scene_breakdown_text())

    assert tuple(scene.scene_number for scene in parsed.scenes) == (1, 2)


def test_missing_scene_number_rejected() -> None:
    """Scene numbering cannot start from scene two."""

    text = _scene_breakdown_text().replace("SCENE_1:", "SCENE_2:", 1)

    with pytest.raises(StructuredOutputError):
        parse_storyboard_scene_breakdown(text)


def test_duplicate_scene_number_rejected() -> None:
    """Duplicate scene numbers should fail safely."""

    text = _scene_breakdown_text().replace("SCENE_2:", "SCENE_1:")

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_storyboard_scene_breakdown(text)

    assert exc_info.value.code == "structured_output_duplicate_field"


def test_skipped_scene_number_rejected() -> None:
    """Skipped scene numbers should fail safely."""

    text = _scene_breakdown_text().replace("SCENE_2:", "SCENE_3:")

    with pytest.raises(StructuredOutputError):
        parse_storyboard_scene_breakdown(text)


def test_missing_scene_field_rejected() -> None:
    """Missing required fields inside a scene block should fail safely."""

    text = _scene_breakdown_text().replace("ON_SCREEN_TEXT:\nHidden mechanic?\n", "")

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_storyboard_scene_breakdown(text)

    assert exc_info.value.code == "structured_output_missing_field"


def test_unknown_scene_field_rejected() -> None:
    """Unknown fields inside a scene block should fail safely."""

    text = _scene_breakdown_text().replace(
        "DURATION_SECONDS:\n8\n",
        "EXTRA:\nNope\nDURATION_SECONDS:\n8\n",
    )

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_storyboard_scene_breakdown(text)

    assert exc_info.value.details == {"field_name": "EXTRA"}


def test_malformed_duration_rejected() -> None:
    """Malformed scene duration values should fail safe float conversion."""

    text = _scene_breakdown_text().replace("DURATION_SECONDS:\n8\n", "DURATION_SECONDS:\nfast\n")

    with pytest.raises(StructuredValueError):
        parse_storyboard_scene_breakdown(text)


@pytest.mark.parametrize("duration", ["0", "-1"])
def test_non_positive_scene_duration_rejected(duration: str) -> None:
    """Scene durations must be positive."""

    text = _scene_breakdown_text().replace("DURATION_SECONDS:\n8\n", f"DURATION_SECONDS:\n{duration}\n")

    with pytest.raises(StructuredValueError):
        parse_storyboard_scene_breakdown(text)


def test_final_scene_count_mismatch_rejected() -> None:
    """Final scene count must equal the number of parsed scenes."""

    with pytest.raises(StructuredOutputError):
        parse_storyboard_scene_breakdown(_scene_breakdown_text(final_scene_count="3"))


def test_total_duration_mismatch_outside_tolerance_rejected() -> None:
    """Total duration must approximately match the scene-duration sum."""

    with pytest.raises(StructuredOutputError):
        parse_storyboard_scene_breakdown(_scene_breakdown_text(total_duration="31"))


def test_valid_visual_direction_parses() -> None:
    """Visual-direction output should parse successfully."""

    parsed = parse_storyboard_visual_direction(
        "SCENE_NUMBER:\n2\n"
        "PRIMARY_VISUAL:\nMechanic close-up with clear focal framing.\n"
        "COMPOSITION:\nCenter-weighted framing with space for overlay text.\n"
        "MOTION:\nSmall forward push toward the mechanic.\n"
        "ON_SCREEN_TEXT:\nWhat really happens\n"
        "STYLE_NOTES:\nKeep the look crisp and readable.\n"
        "AVOID:\nOvercrowded HUD clutter."
    )

    assert isinstance(parsed, StoryboardVisualDirectionOutput)
    assert parsed.scene_number == 2


def test_invalid_visual_scene_number_rejected() -> None:
    """Scene number must be positive in visual direction output."""

    with pytest.raises(StructuredValueError):
        parse_storyboard_visual_direction(
            "SCENE_NUMBER:\n0\n"
            "PRIMARY_VISUAL:\nA visual.\n"
            "COMPOSITION:\nA composition.\n"
            "MOTION:\nA motion.\n"
            "ON_SCREEN_TEXT:\nText.\n"
            "STYLE_NOTES:\nNotes.\n"
            "AVOID:\nAvoid."
        )


def test_valid_timing_review_parses() -> None:
    """Timing review output should parse successfully."""

    parsed = parse_storyboard_timing_review(
        "DECISION:\naccept\n"
        "TOTAL_DURATION_ASSESSMENT:\nThe total duration stays close to target.\n"
        "PACING:\nThe opening moves quickly enough for the hook.\n"
        "SCENE_ISSUES:\nNone.\n"
        "RECOMMENDATIONS:\nKeep scene transitions tight."
    )

    assert isinstance(parsed, StoryboardTimingReviewOutput)
    assert parsed.decision == "accept"


def test_invalid_timing_decision_rejected() -> None:
    """Unsupported timing-review decisions should fail safely."""

    with pytest.raises(StructuredValueError):
        parse_storyboard_timing_review(
            "DECISION:\nmaybe\n"
            "TOTAL_DURATION_ASSESSMENT:\nAssessment.\n"
            "PACING:\nPacing.\n"
            "SCENE_ISSUES:\nIssues.\n"
            "RECOMMENDATIONS:\nRecommendations."
        )


def test_storyboard_raw_output_not_in_errors() -> None:
    """Storyboard parser errors should not expose raw model output."""

    raw_text = _scene_breakdown_text().replace(
        "DURATION_SECONDS:\n8\n",
        "DURATION_SECONDS:\nsecret-value\n",
    )

    with pytest.raises(StructuredValueError) as exc_info:
        parse_storyboard_scene_breakdown(raw_text)

    assert raw_text not in str(exc_info.value)
    assert "secret-value" not in str(exc_info.value)


def test_storyboard_parsers_require_no_provider_calls() -> None:
    """Storyboard parsers should operate only on supplied text."""

    parsed = parse_storyboard_timing_review(
        "DECISION:\nrevise\n"
        "TOTAL_DURATION_ASSESSMENT:\nThe total runs long.\n"
        "PACING:\nMiddle scenes drag slightly.\n"
        "SCENE_ISSUES:\nScene two is long.\n"
        "RECOMMENDATIONS:\nTrim the middle scene."
    )

    assert parsed.decision == "revise"
