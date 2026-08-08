"""Unit tests for typed media-output parsers."""

from __future__ import annotations

import pytest

from creatoros.core import StructuredOutputError, StructuredValueError
from creatoros.parsing import (
    GamingNarrationDirectionOutput,
    GamingSceneMotionOutput,
    GamingSceneVisualOutput,
    GamingThumbnailConceptOutput,
    parse_gaming_narration_direction,
    parse_gaming_scene_motion,
    parse_gaming_scene_visual,
    parse_gaming_thumbnail_concept,
)


def test_valid_thumbnail_output_parses() -> None:
    """Thumbnail concept output should parse successfully."""

    parsed = parse_gaming_thumbnail_concept(
        "CONCEPT:\nShow the hidden mechanic clearly.\n"
        "FOCAL_SUBJECT:\nThe mechanism in the center of the frame.\n"
        "BACKGROUND:\nBlurred in-game environment behind the mechanic.\n"
        "COMPOSITION:\nLarge focal subject with short top-text space.\n"
        "EXPRESSION_OR_ACTION:\nA clear activation moment.\n"
        "ON_IMAGE_TEXT:\nHidden?\n"
        "STYLE_DIRECTION:\nBold contrast with clean readability.\n"
        "AVOID:\nClutter and unsupported extra elements.\n"
        "EVIDENCE_NOTE:\nBased on the supplied mechanic discussion only."
    )

    assert isinstance(parsed, GamingThumbnailConceptOutput)
    assert parsed.on_image_text == "Hidden?"


def test_missing_thumbnail_field_rejected() -> None:
    """Missing thumbnail fields should fail safely."""

    with pytest.raises(StructuredOutputError):
        parse_gaming_thumbnail_concept(
            "CONCEPT:\nShow the hidden mechanic clearly.\n"
            "FOCAL_SUBJECT:\nThe mechanism in the center of the frame.\n"
            "BACKGROUND:\nBlurred in-game environment behind the mechanic.\n"
            "COMPOSITION:\nLarge focal subject with short top-text space.\n"
            "EXPRESSION_OR_ACTION:\nA clear activation moment.\n"
            "STYLE_DIRECTION:\nBold contrast with clean readability.\n"
            "AVOID:\nClutter and unsupported extra elements.\n"
            "EVIDENCE_NOTE:\nBased on the supplied mechanic discussion only."
        )


def test_valid_scene_visual_output_parses() -> None:
    """Scene visual output should parse successfully."""

    parsed = parse_gaming_scene_visual(
        "SCENE_NUMBER:\n1\n"
        "SUBJECT:\nA player-facing view of the mechanic.\n"
        "ENVIRONMENT:\nThe relevant in-game area.\n"
        "ACTION:\nThe mechanic activates visibly.\n"
        "COMPOSITION:\nTight framing around the mechanic.\n"
        "MOOD:\nCurious and focused.\n"
        "ON_SCREEN_TEXT:\nDoes this still work?\n"
        "STYLE_DIRECTION:\nReadable, crisp, and grounded.\n"
        "NEGATIVE_GUIDANCE:\nNo unsupported characters or logos."
    )

    assert isinstance(parsed, GamingSceneVisualOutput)
    assert parsed.scene_number == 1


def test_invalid_scene_visual_number_rejected() -> None:
    """Scene number must be positive in visual output."""

    with pytest.raises(StructuredValueError):
        parse_gaming_scene_visual(
            "SCENE_NUMBER:\n0\n"
            "SUBJECT:\nSubject.\n"
            "ENVIRONMENT:\nEnvironment.\n"
            "ACTION:\nAction.\n"
            "COMPOSITION:\nComposition.\n"
            "MOOD:\nMood.\n"
            "ON_SCREEN_TEXT:\nText.\n"
            "STYLE_DIRECTION:\nStyle.\n"
            "NEGATIVE_GUIDANCE:\nAvoid."
        )


def test_valid_motion_output_parses() -> None:
    """Scene motion output should parse successfully."""

    parsed = parse_gaming_scene_motion(
        "SCENE_NUMBER:\n2\n"
        "PRIMARY_MOTION:\nA short push toward the mechanic.\n"
        "SUBJECT_MOVEMENT:\nThe mechanism toggles once.\n"
        "CAMERA_DIRECTION:\nSlow forward move.\n"
        "TRANSITION_GUIDANCE:\nCut in quickly from the prior scene.\n"
        "PACING:\nFast but readable.\n"
        "DURATION_SECONDS:\n4.5\n"
        "AVOID:\nOverly complex motion paths."
    )

    assert isinstance(parsed, GamingSceneMotionOutput)
    assert parsed.duration_seconds == 4.5


@pytest.mark.parametrize("duration", ["0", "-2"])
def test_non_positive_motion_duration_rejected(duration: str) -> None:
    """Motion duration must be positive."""

    with pytest.raises(StructuredValueError):
        parse_gaming_scene_motion(
            "SCENE_NUMBER:\n2\n"
            "PRIMARY_MOTION:\nA short push toward the mechanic.\n"
            "SUBJECT_MOVEMENT:\nThe mechanism toggles once.\n"
            "CAMERA_DIRECTION:\nSlow forward move.\n"
            "TRANSITION_GUIDANCE:\nCut in quickly from the prior scene.\n"
            "PACING:\nFast but readable.\n"
            f"DURATION_SECONDS:\n{duration}\n"
            "AVOID:\nOverly complex motion paths."
        )


def test_malformed_motion_duration_rejected() -> None:
    """Malformed motion duration values should fail safe float conversion."""

    with pytest.raises(StructuredValueError):
        parse_gaming_scene_motion(
            "SCENE_NUMBER:\n2\n"
            "PRIMARY_MOTION:\nA short push toward the mechanic.\n"
            "SUBJECT_MOVEMENT:\nThe mechanism toggles once.\n"
            "CAMERA_DIRECTION:\nSlow forward move.\n"
            "TRANSITION_GUIDANCE:\nCut in quickly from the prior scene.\n"
            "PACING:\nFast but readable.\n"
            "DURATION_SECONDS:\nfast\n"
            "AVOID:\nOverly complex motion paths."
        )


def test_valid_narration_output_parses() -> None:
    """Narration direction output should parse successfully."""

    parsed = parse_gaming_narration_direction(
        "NARRATION_TEXT:\nYou probably still believe this myth.\n"
        "TONE:\nCalm and curious.\n"
        "PACE:\nBrisk but clear.\n"
        "EMPHASIS:\nStress the claim and the correction.\n"
        "PAUSE_GUIDANCE:\nPause briefly before the resolution line.\n"
        "PRONUNCIATION_NOTES:\nSay the game term carefully.\n"
        "TARGET_DURATION_SECONDS:\n30"
    )

    assert isinstance(parsed, GamingNarrationDirectionOutput)
    assert parsed.target_duration_seconds == 30


@pytest.mark.parametrize("duration", ["0", "-1"])
def test_non_positive_narration_duration_rejected(duration: str) -> None:
    """Narration target duration must be positive."""

    with pytest.raises(StructuredValueError):
        parse_gaming_narration_direction(
            "NARRATION_TEXT:\nText.\n"
            "TONE:\nTone.\n"
            "PACE:\nPace.\n"
            "EMPHASIS:\nEmphasis.\n"
            "PAUSE_GUIDANCE:\nPause.\n"
            "PRONUNCIATION_NOTES:\nNotes.\n"
            f"TARGET_DURATION_SECONDS:\n{duration}"
        )


def test_media_raw_output_omitted_from_errors() -> None:
    """Media parser errors should not expose raw response text."""

    raw_text = (
        "SCENE_NUMBER:\n2\n"
        "PRIMARY_MOTION:\nA short push toward the mechanic.\n"
        "SUBJECT_MOVEMENT:\nsecret movement description\n"
        "CAMERA_DIRECTION:\nSlow forward move.\n"
        "TRANSITION_GUIDANCE:\nCut in quickly from the prior scene.\n"
        "PACING:\nFast but readable.\n"
        "DURATION_SECONDS:\nfast\n"
        "AVOID:\nOverly complex motion paths."
    )

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_scene_motion(raw_text)

    assert raw_text not in str(exc_info.value)
    assert "secret movement description" not in str(exc_info.value)


def test_media_models_serialize_and_restore() -> None:
    """Media output models should round-trip predictably."""

    thumbnail = GamingThumbnailConceptOutput(
        concept="Show the hidden mechanic clearly.",
        focal_subject="The mechanism in the center of the frame.",
        background="Blurred in-game environment behind the mechanic.",
        composition="Large focal subject with short top-text space.",
        expression_or_action="A clear activation moment.",
        on_image_text="Hidden?",
        style_direction="Bold contrast with clean readability.",
        avoid="Clutter and unsupported extra elements.",
        evidence_note="Based on the supplied mechanic discussion only.",
    )
    visual = GamingSceneVisualOutput(
        scene_number=1,
        subject="A player-facing view of the mechanic.",
        environment="The relevant in-game area.",
        action="The mechanic activates visibly.",
        composition="Tight framing around the mechanic.",
        mood="Curious and focused.",
        on_screen_text="Does this still work?",
        style_direction="Readable, crisp, and grounded.",
        negative_guidance="No unsupported characters or logos.",
    )
    motion = GamingSceneMotionOutput(
        scene_number=2,
        primary_motion="A short push toward the mechanic.",
        subject_movement="The mechanism toggles once.",
        camera_direction="Slow forward move.",
        transition_guidance="Cut in quickly from the prior scene.",
        pacing="Fast but readable.",
        duration_seconds=4.5,
        avoid="Overly complex motion paths.",
    )
    narration = GamingNarrationDirectionOutput(
        narration_text="You probably still believe this myth.",
        tone="Calm and curious.",
        pace="Brisk but clear.",
        emphasis="Stress the claim and the correction.",
        pause_guidance="Pause briefly before the resolution line.",
        pronunciation_notes="Say the game term carefully.",
        target_duration_seconds=30,
    )

    assert GamingThumbnailConceptOutput.model_validate(thumbnail.model_dump()) == thumbnail
    assert GamingSceneVisualOutput.model_validate(visual.model_dump()) == visual
    assert GamingSceneMotionOutput.model_validate(motion.model_dump()) == motion
    assert GamingNarrationDirectionOutput.model_validate(narration.model_dump()) == narration


def test_media_parsers_require_no_provider_calls() -> None:
    """Media parsers should operate only on supplied text."""

    parsed = parse_gaming_thumbnail_concept(
        "CONCEPT:\nShow the hidden mechanic clearly.\n"
        "FOCAL_SUBJECT:\nThe mechanism in the center of the frame.\n"
        "BACKGROUND:\nBlurred in-game environment behind the mechanic.\n"
        "COMPOSITION:\nLarge focal subject with short top-text space.\n"
        "EXPRESSION_OR_ACTION:\nA clear activation moment.\n"
        "ON_IMAGE_TEXT:\nHidden?\n"
        "STYLE_DIRECTION:\nBold contrast with clean readability.\n"
        "AVOID:\nClutter and unsupported extra elements.\n"
        "EVIDENCE_NOTE:\nBased on the supplied mechanic discussion only."
    )

    assert parsed.concept.startswith("Show")
