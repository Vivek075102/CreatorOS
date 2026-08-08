"""Unit tests for typed script-output parsers."""

from __future__ import annotations

import pytest

from creatoros.core import StructuredOutputError, StructuredValueError
from creatoros.parsing import (
    GamingCTAOutput,
    GamingHookOutput,
    YouTubeShortsScriptOutput,
    parse_gaming_cta,
    parse_gaming_hook,
    parse_youtube_shorts_script,
)


def test_valid_youtube_shorts_output_parses() -> None:
    """A valid YouTube Shorts script should parse into the typed model."""

    parsed = parse_youtube_shorts_script(
        "TITLE:\nRoblox: Funny Myths\n"
        "HOOK:\nYou probably still believe this Roblox myth.\n"
        "BODY:\nPlayers keep repeating it, but the evidence is thinner than it sounds.\n"
        "ENDING:\nThat is why this myth needs cautious testing.\n"
        "CALL_TO_ACTION:\nWhich myth should we test next?\n"
        "ESTIMATED_DURATION_SECONDS:\n30\n"
        "EVIDENCE_NOTE:\nSupported by supplied discussion signals; exact mechanic behavior still needs care."
    )

    assert parsed == YouTubeShortsScriptOutput(
        title="Roblox: Funny Myths",
        hook="You probably still believe this Roblox myth.",
        body="Players keep repeating it, but the evidence is thinner than it sounds.",
        ending="That is why this myth needs cautious testing.",
        call_to_action="Which myth should we test next?",
        estimated_duration_seconds=30,
        evidence_note="Supported by supplied discussion signals; exact mechanic behavior still needs care.",
    )


def test_multiline_body_is_preserved() -> None:
    """Multiline BODY text should preserve internal newlines."""

    parsed = parse_youtube_shorts_script(
        "TITLE:\nRoblox: Funny Myths\n"
        "HOOK:\nYou probably still believe this Roblox myth.\n"
        "BODY:\nLine one.\nLine two.\nLine three.\n"
        "ENDING:\nThat is why this myth needs cautious testing.\n"
        "CALL_TO_ACTION:\nWhich myth should we test next?\n"
        "ESTIMATED_DURATION_SECONDS:\n30\n"
        "EVIDENCE_NOTE:\nSupported by supplied discussion signals."
    )

    assert parsed.body == "Line one.\nLine two.\nLine three."


def test_positive_duration_is_accepted() -> None:
    """Positive durations should parse successfully."""

    parsed = parse_youtube_shorts_script(
        "TITLE:\nRoblox: Funny Myths\n"
        "HOOK:\nYou probably still believe this Roblox myth.\n"
        "BODY:\nOne clear idea.\n"
        "ENDING:\nThat is why this myth needs cautious testing.\n"
        "CALL_TO_ACTION:\nWhich myth should we test next?\n"
        "ESTIMATED_DURATION_SECONDS:\n1\n"
        "EVIDENCE_NOTE:\nSupported by supplied discussion signals."
    )

    assert parsed.estimated_duration_seconds == 1


@pytest.mark.parametrize("duration", ["0", "-5"])
def test_non_positive_duration_is_rejected(duration: str) -> None:
    """Zero and negative durations should fail safely."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_youtube_shorts_script(
            "TITLE:\nRoblox: Funny Myths\n"
            "HOOK:\nYou probably still believe this Roblox myth.\n"
            "BODY:\nOne clear idea.\n"
            "ENDING:\nThat is why this myth needs cautious testing.\n"
            "CALL_TO_ACTION:\nWhich myth should we test next?\n"
            f"ESTIMATED_DURATION_SECONDS:\n{duration}\n"
            "EVIDENCE_NOTE:\nSupported by supplied discussion signals."
        )

    assert exc_info.value.code == "structured_output_invalid"


def test_malformed_duration_is_rejected() -> None:
    """Malformed duration values should fail safe integer conversion."""

    with pytest.raises(StructuredValueError) as exc_info:
        parse_youtube_shorts_script(
            "TITLE:\nRoblox: Funny Myths\n"
            "HOOK:\nYou probably still believe this Roblox myth.\n"
            "BODY:\nOne clear idea.\n"
            "ENDING:\nThat is why this myth needs cautious testing.\n"
            "CALL_TO_ACTION:\nWhich myth should we test next?\n"
            "ESTIMATED_DURATION_SECONDS:\nthirty\n"
            "EVIDENCE_NOTE:\nSupported by supplied discussion signals."
        )

    assert exc_info.value.details == {
        "field_name": "ESTIMATED_DURATION_SECONDS",
        "expected_type": "integer",
    }


def test_missing_script_field_is_rejected() -> None:
    """Missing required script fields should fail safely."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_youtube_shorts_script(
            "TITLE:\nRoblox: Funny Myths\n"
            "HOOK:\nYou probably still believe this Roblox myth.\n"
            "BODY:\nOne clear idea.\n"
            "ENDING:\nThat is why this myth needs cautious testing.\n"
            "ESTIMATED_DURATION_SECONDS:\n30\n"
            "EVIDENCE_NOTE:\nSupported by supplied discussion signals."
        )

    assert exc_info.value.details == {"missing_required_fields": ("CALL_TO_ACTION",)}


def test_unknown_script_field_is_rejected() -> None:
    """Unknown script fields should not be silently accepted."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_youtube_shorts_script(
            "TITLE:\nRoblox: Funny Myths\n"
            "HOOK:\nYou probably still believe this Roblox myth.\n"
            "BODY:\nOne clear idea.\n"
            "ENDING:\nThat is why this myth needs cautious testing.\n"
            "CALL_TO_ACTION:\nWhich myth should we test next?\n"
            "ESTIMATED_DURATION_SECONDS:\n30\n"
            "EVIDENCE_NOTE:\nSupported by supplied discussion signals.\n"
            "EXTRA:\nnope"
        )

    assert exc_info.value.details == {"unknown_fields": ("EXTRA",)}


def test_valid_gaming_hook_parses() -> None:
    """Valid hook output should parse successfully."""

    parsed = parse_gaming_hook(
        "HOOK_1:\nYou probably still believe this Roblox myth.\n"
        "HOOK_2:\nMost players repeat this Roblox mechanic claim without checking it.\n"
        "HOOK_3:\nThis Roblox myth sounds true until you test it.\n"
        "BEST_HOOK:\nYou probably still believe this Roblox myth.\n"
        "WHY:\nIt is the shortest and clearest curiosity hook."
    )

    assert parsed.hook_1 == "You probably still believe this Roblox myth."
    assert parsed.best_hook == parsed.hook_1


def test_best_hook_matching_hook_2_works() -> None:
    """Best hook should be able to select hook_2."""

    parsed = parse_gaming_hook(
        "HOOK_1:\nHook one.\n"
        "HOOK_2:\nHook two.\n"
        "HOOK_3:\nHook three.\n"
        "BEST_HOOK:\nHook two.\n"
        "WHY:\nIt is the most specific."
    )

    assert parsed.best_hook == parsed.hook_2


def test_best_hook_matching_hook_3_works() -> None:
    """Best hook should be able to select hook_3."""

    parsed = parse_gaming_hook(
        "HOOK_1:\nHook one.\n"
        "HOOK_2:\nHook two.\n"
        "HOOK_3:\nHook three.\n"
        "BEST_HOOK:\nHook three.\n"
        "WHY:\nIt is the most memorable."
    )

    assert parsed.best_hook == parsed.hook_3


def test_unmatched_best_hook_is_rejected() -> None:
    """Best hook must match one of the three provided hooks."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_gaming_hook(
            "HOOK_1:\nHook one.\n"
            "HOOK_2:\nHook two.\n"
            "HOOK_3:\nHook three.\n"
            "BEST_HOOK:\nDifferent hook.\n"
            "WHY:\nIt sounds stronger."
        )

    assert exc_info.value.code == "structured_output_invalid"


def test_valid_cta_parses() -> None:
    """Valid CTA output should parse successfully."""

    parsed = parse_gaming_cta(
        "CTA:\nWhich myth should we test next?\n"
        "ALTERNATIVE:\nTell me which mechanic sounds most suspicious."
    )

    assert parsed == GamingCTAOutput(
        cta="Which myth should we test next?",
        alternative="Tell me which mechanic sounds most suspicious.",
    )


def test_blank_cta_is_rejected() -> None:
    """Blank CTA values should fail safely."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_gaming_cta("CTA:\n   \nALTERNATIVE:\nAlternative text")

    assert exc_info.value.code == "structured_output_invalid"


def test_multiline_values_behave_predictably() -> None:
    """Multiline text values should be preserved where the generic parser allows them."""

    parsed = parse_gaming_cta(
        "CTA:\nAsk the viewer one direct question.\nSecond line stays.\n"
        "ALTERNATIVE:\nAlternative prompt."
    )

    assert parsed.cta == "Ask the viewer one direct question.\nSecond line stays."


def test_script_parse_functions_are_deterministic() -> None:
    """Identical script input should produce identical parsed output."""

    text = (
        "CTA:\nWhich myth should we test next?\n"
        "ALTERNATIVE:\nTell me which mechanic sounds most suspicious."
    )

    assert parse_gaming_cta(text) == parse_gaming_cta(text)


def test_raw_output_is_not_in_script_parser_errors() -> None:
    """Script parser errors should not expose raw response text."""

    raw_text = (
        "TITLE:\nRoblox: Funny Myths\n"
        "HOOK:\nYou probably still believe this Roblox myth.\n"
        "BODY:\nsecret internal script draft\n"
        "ENDING:\nThat is why this myth needs cautious testing.\n"
        "CALL_TO_ACTION:\nWhich myth should we test next?\n"
        "ESTIMATED_DURATION_SECONDS:\nthirty\n"
        "EVIDENCE_NOTE:\nSupported by supplied discussion signals."
    )

    with pytest.raises(StructuredValueError) as exc_info:
        parse_youtube_shorts_script(raw_text)

    assert raw_text not in str(exc_info.value)
    assert "secret internal script draft" not in str(exc_info.value)


def test_script_models_serialize_and_restore() -> None:
    """Script output models should round-trip predictably."""

    script = YouTubeShortsScriptOutput(
        title="Roblox: Funny Myths",
        hook="You probably still believe this Roblox myth.",
        body="One clear idea.",
        ending="That is why this myth needs cautious testing.",
        call_to_action="Which myth should we test next?",
        estimated_duration_seconds=30,
        evidence_note="Supported by supplied discussion signals.",
    )
    hook = GamingHookOutput(
        hook_1="Hook one.",
        hook_2="Hook two.",
        hook_3="Hook three.",
        best_hook="Hook two.",
        why="It is the most specific.",
    )
    cta = GamingCTAOutput(
        cta="Which myth should we test next?",
        alternative="Tell me which mechanic sounds most suspicious.",
    )

    assert YouTubeShortsScriptOutput.model_validate(script.model_dump()) == script
    assert GamingHookOutput.model_validate(hook.model_dump()) == hook
    assert GamingCTAOutput.model_validate(cta.model_dump()) == cta


def test_script_parsers_require_no_provider_calls() -> None:
    """Script parsers should operate purely on supplied text."""

    parsed = parse_gaming_cta(
        "CTA:\nWhich myth should we test next?\n"
        "ALTERNATIVE:\nTell me which mechanic sounds most suspicious."
    )

    assert parsed.cta.startswith("Which myth")
