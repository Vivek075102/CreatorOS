"""Unit tests for typed research-output parsers."""

from __future__ import annotations

import pytest

from creatoros.core import StructuredOutputError, StructuredValueError
from creatoros.parsing import (
    GamingKeywordExpansionOutput,
    GamingOpportunityEvaluationOutput,
    GamingTrendDiscoveryOutput,
    parse_gaming_keyword_expansion,
    parse_gaming_opportunity_evaluation,
    parse_gaming_trend_discovery,
)


def test_valid_trend_discovery_parses() -> None:
    """A valid trend-discovery output should parse into the typed model."""

    parsed = parse_gaming_trend_discovery(
        "TITLE:\nMinecraft: Hidden Mechanics\n"
        "GAME:\nMinecraft\n"
        "TOPIC:\ngaming facts\n"
        "ANGLE:\nExplain one overlooked mechanic.\n"
        "WHY_NOW:\nPlayers are discussing recurring mechanic myths.\n"
        "SOURCE_SUMMARY:\nSupplied signals mention recurring hidden-mechanic debates.\n"
        "CONFIDENCE:\nmedium"
    )

    assert parsed == GamingTrendDiscoveryOutput(
        title="Minecraft: Hidden Mechanics",
        game="Minecraft",
        topic="gaming facts",
        angle="Explain one overlooked mechanic.",
        why_now="Players are discussing recurring mechanic myths.",
        source_summary="Supplied signals mention recurring hidden-mechanic debates.",
        confidence="medium",
    )


def test_multiline_source_summary_works() -> None:
    """Trend parsing should preserve meaningful internal newlines."""

    parsed = parse_gaming_trend_discovery(
        "TITLE:\nMinecraft: Hidden Mechanics\n"
        "GAME:\nMinecraft\n"
        "TOPIC:\ngaming facts\n"
        "ANGLE:\nExplain one overlooked mechanic.\n"
        "WHY_NOW:\nPlayers are asking whether the mechanic still works.\n"
        "SOURCE_SUMMARY:\nLine one of evidence.\nLine two of evidence.\n"
        "CONFIDENCE:\nhigh"
    )

    assert parsed.source_summary == "Line one of evidence.\nLine two of evidence."


@pytest.mark.parametrize("confidence", ["low", "medium", "high", " LOW "])
def test_confidence_values_are_accepted(confidence: str) -> None:
    """Trend discovery should accept only the supported confidence labels."""

    parsed = parse_gaming_trend_discovery(
        "TITLE:\nMinecraft: Hidden Mechanics\n"
        "GAME:\nMinecraft\n"
        "TOPIC:\ngaming facts\n"
        "ANGLE:\nExplain one overlooked mechanic.\n"
        "WHY_NOW:\nPlayers are asking whether the mechanic still works.\n"
        "SOURCE_SUMMARY:\nEvidence summary.\n"
        f"CONFIDENCE:\n{confidence}"
    )

    assert parsed.confidence in {"low", "medium", "high"}


def test_invalid_confidence_is_rejected() -> None:
    """Unsupported confidence values should fail safely."""

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_trend_discovery(
            "TITLE:\nMinecraft: Hidden Mechanics\n"
            "GAME:\nMinecraft\n"
            "TOPIC:\ngaming facts\n"
            "ANGLE:\nExplain one overlooked mechanic.\n"
            "WHY_NOW:\nPlayers are asking whether the mechanic still works.\n"
            "SOURCE_SUMMARY:\nEvidence summary.\n"
            "CONFIDENCE:\nvery high"
        )

    assert exc_info.value.code == "structured_output_invalid_value"
    assert exc_info.value.details == {"field_name": "CONFIDENCE", "expected_type": "literal"}


def test_missing_research_field_is_rejected() -> None:
    """Missing required research fields should fail safely."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_gaming_trend_discovery(
            "TITLE:\nMinecraft: Hidden Mechanics\n"
            "GAME:\nMinecraft\n"
            "TOPIC:\ngaming facts\n"
            "ANGLE:\nExplain one overlooked mechanic.\n"
            "SOURCE_SUMMARY:\nEvidence summary.\n"
            "CONFIDENCE:\nmedium"
        )

    assert exc_info.value.details == {"missing_required_fields": ("WHY_NOW",)}


def test_unknown_research_field_is_rejected() -> None:
    """Unknown research fields should not be silently accepted."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_gaming_trend_discovery(
            "TITLE:\nMinecraft: Hidden Mechanics\n"
            "GAME:\nMinecraft\n"
            "TOPIC:\ngaming facts\n"
            "ANGLE:\nExplain one overlooked mechanic.\n"
            "WHY_NOW:\nPlayers are asking whether the mechanic still works.\n"
            "SOURCE_SUMMARY:\nEvidence summary.\n"
            "CONFIDENCE:\nmedium\n"
            "EXTRA:\nnope"
        )

    assert exc_info.value.details == {"unknown_fields": ("EXTRA",)}


def test_valid_opportunity_evaluation_parses() -> None:
    """A valid opportunity evaluation should parse into the typed model."""

    parsed = parse_gaming_opportunity_evaluation(
        "DECISION:\naccept\n"
        "SCORE:\n82\n"
        "STRENGTHS:\nClear curiosity and short-form fit.\n"
        "RISKS:\nEvidence is useful but still limited.\n"
        "RECOMMENDED_ANGLE:\nTest one common myth carefully.\n"
        "HOOK_DIRECTION:\nChallenge the viewer's assumption.\n"
        "REASON:\nThe topic is specific and supported enough for a cautious short."
    )

    assert parsed == GamingOpportunityEvaluationOutput(
        decision="accept",
        score=82,
        strengths="Clear curiosity and short-form fit.",
        risks="Evidence is useful but still limited.",
        recommended_angle="Test one common myth carefully.",
        hook_direction="Challenge the viewer's assumption.",
        reason="The topic is specific and supported enough for a cautious short.",
    )


def test_score_zero_is_accepted() -> None:
    """Zero should remain a valid score boundary."""

    parsed = parse_gaming_opportunity_evaluation(
        "DECISION:\nreject\n"
        "SCORE:\n0\n"
        "STRENGTHS:\nThe title is concise.\n"
        "RISKS:\nEvidence is too weak.\n"
        "RECOMMENDED_ANGLE:\nNarrow the claim substantially.\n"
        "HOOK_DIRECTION:\nLead with uncertainty.\n"
        "REASON:\nThe current concept cannot be responsibly supported."
    )

    assert parsed.score == 0


def test_score_one_hundred_is_accepted() -> None:
    """One hundred should remain a valid score boundary."""

    parsed = parse_gaming_opportunity_evaluation(
        "DECISION:\naccept\n"
        "SCORE:\n100\n"
        "STRENGTHS:\nStrong relevance and clear evidence.\n"
        "RISKS:\nMinor phrasing drift risk only.\n"
        "RECOMMENDED_ANGLE:\nStay tightly focused on the main mechanic.\n"
        "HOOK_DIRECTION:\nOpen with the strongest supported surprise.\n"
        "REASON:\nThe concept is well-supported and concise."
    )

    assert parsed.score == 100


@pytest.mark.parametrize("score", ["-1", "101"])
def test_out_of_range_scores_are_rejected(score: str) -> None:
    """Scores outside the supported range should fail validation safely."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_gaming_opportunity_evaluation(
            "DECISION:\naccept\n"
            f"SCORE:\n{score}\n"
            "STRENGTHS:\nClear curiosity and short-form fit.\n"
            "RISKS:\nEvidence is useful but still limited.\n"
            "RECOMMENDED_ANGLE:\nTest one common myth carefully.\n"
            "HOOK_DIRECTION:\nChallenge the viewer's assumption.\n"
            "REASON:\nThe topic is specific and supported enough for a cautious short."
        )

    assert exc_info.value.code == "structured_output_invalid"


def test_non_integer_score_is_rejected() -> None:
    """Malformed score values should fail safe integer conversion."""

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_opportunity_evaluation(
            "DECISION:\naccept\n"
            "SCORE:\n82.5\n"
            "STRENGTHS:\nClear curiosity and short-form fit.\n"
            "RISKS:\nEvidence is useful but still limited.\n"
            "RECOMMENDED_ANGLE:\nTest one common myth carefully.\n"
            "HOOK_DIRECTION:\nChallenge the viewer's assumption.\n"
            "REASON:\nThe topic is specific and supported enough for a cautious short."
        )

    assert exc_info.value.details == {"field_name": "SCORE", "expected_type": "integer"}


def test_invalid_decision_is_rejected() -> None:
    """Unsupported decisions should fail safely."""

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_opportunity_evaluation(
            "DECISION:\nmaybe\n"
            "SCORE:\n82\n"
            "STRENGTHS:\nClear curiosity and short-form fit.\n"
            "RISKS:\nEvidence is useful but still limited.\n"
            "RECOMMENDED_ANGLE:\nTest one common myth carefully.\n"
            "HOOK_DIRECTION:\nChallenge the viewer's assumption.\n"
            "REASON:\nThe topic is specific and supported enough for a cautious short."
        )

    assert exc_info.value.details == {"field_name": "DECISION", "expected_type": "literal"}


def test_valid_keyword_expansion_parses() -> None:
    """Valid keyword expansion output should parse into immutable tuples."""

    parsed = parse_gaming_keyword_expansion(
        "PRIMARY:\n- minecraft myths\n- minecraft mechanics\n"
        "RELATED:\n- redstone myths\n"
        "QUESTIONS:\n- does this mechanic actually work?\n"
        "ENTITIES:\n- redstone"
    )

    assert parsed == GamingKeywordExpansionOutput(
        primary=("minecraft myths", "minecraft mechanics"),
        related=("redstone myths",),
        questions=("does this mechanic actually work?",),
        entities=("redstone",),
    )


def test_keyword_bullet_lists_preserve_order() -> None:
    """Keyword parsing should preserve the supplied item order."""

    parsed = parse_gaming_keyword_expansion(
        "PRIMARY:\n- first\n- second\n- third\n"
        "RELATED:\n- related one\n- related two\n"
        "QUESTIONS:\n- question one\n"
        "ENTITIES:\n- entity one"
    )

    assert parsed.primary == ("first", "second", "third")
    assert parsed.related == ("related one", "related two")


def test_blank_keyword_bullet_is_rejected() -> None:
    """Blank bullet items should fail safely."""

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_keyword_expansion(
            "PRIMARY:\n- minecraft myths\n-   \n"
            "RELATED:\n- redstone myths\n"
            "QUESTIONS:\n- does this mechanic actually work?\n"
            "ENTITIES:\n- redstone"
        )

    assert exc_info.value.details == {
        "field_name": "PRIMARY",
        "expected_type": "simple_bullet_list",
    }


def test_primary_list_must_not_be_empty() -> None:
    """Primary keywords must contain at least one bullet item."""

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_gaming_keyword_expansion(
            "PRIMARY:\n\n"
            "RELATED:\n- redstone myths\n"
            "QUESTIONS:\n- does this mechanic actually work?\n"
            "ENTITIES:\n- redstone"
        )

    assert exc_info.value.code == "structured_output_invalid"


def test_keyword_duplicates_are_rejected_consistently() -> None:
    """Duplicate bullet items should be rejected rather than silently removed."""

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_keyword_expansion(
            "PRIMARY:\n- minecraft myths\n- minecraft myths\n"
            "RELATED:\n- redstone myths\n"
            "QUESTIONS:\n- does this mechanic actually work?\n"
            "ENTITIES:\n- redstone"
        )

    assert exc_info.value.details == {
        "field_name": "PRIMARY",
        "expected_type": "unique_simple_bullet_list",
    }


def test_raw_output_is_not_in_research_parser_errors() -> None:
    """Research parser errors should not expose raw response text."""

    raw_text = (
        "TITLE:\nMinecraft: Hidden Mechanics\n"
        "GAME:\nMinecraft\n"
        "TOPIC:\ngaming facts\n"
        "ANGLE:\nExplain one overlooked mechanic.\n"
        "WHY_NOW:\nPlayers are asking whether the mechanic still works.\n"
        "SOURCE_SUMMARY:\nsecret raw evidence line\n"
        "CONFIDENCE:\nvery high"
    )

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_trend_discovery(raw_text)

    assert raw_text not in str(exc_info.value)
    assert "secret raw evidence line" not in str(exc_info.value)


def test_research_models_serialize_and_restore() -> None:
    """Research output models should round-trip predictably."""

    discovery = GamingTrendDiscoveryOutput(
        title="Minecraft: Hidden Mechanics",
        game="Minecraft",
        topic="gaming facts",
        angle="Explain one overlooked mechanic.",
        why_now="Players are discussing recurring mechanic myths.",
        source_summary="Evidence summary.",
        confidence="medium",
    )
    evaluation = GamingOpportunityEvaluationOutput(
        decision="accept",
        score=82,
        strengths="Clear curiosity and short-form fit.",
        risks="Evidence is useful but still limited.",
        recommended_angle="Test one common myth carefully.",
        hook_direction="Challenge the viewer's assumption.",
        reason="The topic is specific and supported enough for a cautious short.",
    )
    keywords = GamingKeywordExpansionOutput(
        primary=("minecraft myths",),
        related=("redstone myths",),
        questions=("does this mechanic actually work?",),
        entities=("redstone",),
    )

    assert GamingTrendDiscoveryOutput.model_validate(discovery.model_dump()) == discovery
    assert GamingOpportunityEvaluationOutput.model_validate(evaluation.model_dump()) == evaluation
    assert GamingKeywordExpansionOutput.model_validate(keywords.model_dump()) == keywords


def test_research_parse_functions_are_deterministic() -> None:
    """Identical research input should produce identical parsed output."""

    text = (
        "PRIMARY:\n- minecraft myths\n- minecraft mechanics\n"
        "RELATED:\n- redstone myths\n"
        "QUESTIONS:\n- does this mechanic actually work?\n"
        "ENTITIES:\n- redstone"
    )

    assert parse_gaming_keyword_expansion(text) == parse_gaming_keyword_expansion(text)


def test_research_parsers_require_no_provider_calls() -> None:
    """Research parsers should operate purely on supplied text."""

    parsed = parse_gaming_keyword_expansion(
        "PRIMARY:\n- minecraft myths\n"
        "RELATED:\n\n"
        "QUESTIONS:\n\n"
        "ENTITIES:\n"
    )

    assert parsed.primary == ("minecraft myths",)
    assert parsed.related == ()
    assert parsed.questions == ()
    assert parsed.entities == ()
