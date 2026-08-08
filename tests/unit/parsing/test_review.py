"""Unit tests for typed review-output parsers."""

from __future__ import annotations

import pytest

from creatoros.core import StructuredOutputError, StructuredValueError
from creatoros.parsing import (
    GamingEvidenceConsistencyReviewOutput,
    GamingPublicationReadinessReviewOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    parse_gaming_evidence_consistency_review,
    parse_gaming_publication_readiness_review,
    parse_gaming_script_quality_review,
    parse_gaming_storyboard_quality_review,
)


def test_valid_script_review_parses() -> None:
    """Script quality review output should parse successfully."""

    parsed = parse_gaming_script_quality_review(
        "DECISION:\naccept\n"
        "SUMMARY:\nThe script is clear and focused.\n"
        "HOOK_REVIEW:\nThe hook creates immediate curiosity.\n"
        "CLARITY_REVIEW:\nThe lines are easy to follow aloud.\n"
        "STRUCTURE_REVIEW:\nThe script maintains one main idea.\n"
        "FACTUAL_RESTRAINT:\nClaims stay cautious relative to the evidence.\n"
        "PACING_REVIEW:\nThe pacing fits the short target.\n"
        "ENDING_REVIEW:\nThe ending resolves the promise naturally.\n"
        "ISSUES:\nNone.\n"
        "RECOMMENDATIONS:\nKeep the phrasing concise."
    )

    assert isinstance(parsed, GamingScriptQualityReviewOutput)
    assert parsed.decision == "accept"


def test_invalid_script_review_decision_rejected() -> None:
    """Unsupported script review decisions should fail safely."""

    with pytest.raises(StructuredValueError):
        parse_gaming_script_quality_review(
            "DECISION:\nmaybe\nSUMMARY:\nSummary.\nHOOK_REVIEW:\nHook.\nCLARITY_REVIEW:\nClarity.\n"
            "STRUCTURE_REVIEW:\nStructure.\nFACTUAL_RESTRAINT:\nRestraint.\nPACING_REVIEW:\nPacing.\n"
            "ENDING_REVIEW:\nEnding.\nISSUES:\nNone.\nRECOMMENDATIONS:\nRecommendations."
        )


def test_valid_evidence_review_parses() -> None:
    """Evidence consistency review output should parse successfully."""

    parsed = parse_gaming_evidence_consistency_review(
        "DECISION:\nconsistent\n"
        "SUMMARY:\nThe claims align with supplied evidence.\n"
        "SUPPORTED_CLAIMS:\nThe core mechanic claim is supported.\n"
        "UNSUPPORTED_CLAIMS:\nNone.\n"
        "CONTRADICTIONS:\nNone.\n"
        "UNCERTAINTIES:\nMinor uncertainty remains around edge cases.\n"
        "OVERSTATEMENTS:\nNone.\n"
        "RECOMMENDATIONS:\nKeep cautious wording."
    )

    assert isinstance(parsed, GamingEvidenceConsistencyReviewOutput)
    assert parsed.decision == "consistent"


def test_insufficient_evidence_accepted() -> None:
    """The insufficient_evidence review decision should be accepted."""

    parsed = parse_gaming_evidence_consistency_review(
        "DECISION:\ninsufficient_evidence\n"
        "SUMMARY:\nThe supplied material is too thin for a stronger conclusion.\n"
        "SUPPORTED_CLAIMS:\nVery little is directly supported.\n"
        "UNSUPPORTED_CLAIMS:\nSeveral statements lack support.\n"
        "CONTRADICTIONS:\nNone.\n"
        "UNCERTAINTIES:\nThe main claim remains uncertain.\n"
        "OVERSTATEMENTS:\nThe wording sounds too certain.\n"
        "RECOMMENDATIONS:\nReduce certainty or gather better evidence."
    )

    assert parsed.decision == "insufficient_evidence"


def test_invalid_evidence_decision_rejected() -> None:
    """Unsupported evidence-review decisions should fail safely."""

    with pytest.raises(StructuredValueError):
        parse_gaming_evidence_consistency_review(
            "DECISION:\nunknown\nSUMMARY:\nSummary.\nSUPPORTED_CLAIMS:\nSupported.\nUNSUPPORTED_CLAIMS:\nUnsupported.\n"
            "CONTRADICTIONS:\nNone.\nUNCERTAINTIES:\nSome.\nOVERSTATEMENTS:\nNone.\nRECOMMENDATIONS:\nRecommendations."
        )


def test_valid_storyboard_review_parses() -> None:
    """Storyboard quality review output should parse successfully."""

    parsed = parse_gaming_storyboard_quality_review(
        "DECISION:\nrevise\n"
        "SUMMARY:\nThe storyboard mostly works but needs one fix.\n"
        "SCRIPT_FIDELITY:\nMost scenes match the script.\n"
        "HOOK_SCENE:\nThe opening scene supports the hook.\n"
        "SCENE_SEQUENCE:\nThe order is mostly clear.\n"
        "VISUAL_CLARITY:\nThe visual instructions are readable.\n"
        "PACING:\nThe middle scene runs slightly long.\n"
        "ENDING_SCENE:\nThe final scene supports the ending.\n"
        "UNSUPPORTED_VISUALS:\nOne visual claim needs caution.\n"
        "ISSUES:\nScene two should be tighter.\n"
        "RECOMMENDATIONS:\nTrim the middle scene and simplify one shot."
    )

    assert isinstance(parsed, GamingStoryboardQualityReviewOutput)
    assert parsed.decision == "revise"


def test_invalid_storyboard_decision_rejected() -> None:
    """Unsupported storyboard-review decisions should fail safely."""

    with pytest.raises(StructuredValueError):
        parse_gaming_storyboard_quality_review(
            "DECISION:\nunknown\nSUMMARY:\nSummary.\nSCRIPT_FIDELITY:\nFidelity.\nHOOK_SCENE:\nHook.\n"
            "SCENE_SEQUENCE:\nSequence.\nVISUAL_CLARITY:\nClarity.\nPACING:\nPacing.\nENDING_SCENE:\nEnding.\n"
            "UNSUPPORTED_VISUALS:\nNone.\nISSUES:\nIssues.\nRECOMMENDATIONS:\nRecommendations."
        )


def test_valid_publication_readiness_review_parses() -> None:
    """Publication readiness review output should parse successfully."""

    parsed = parse_gaming_publication_readiness_review(
        "DECISION:\nready_for_human_review\n"
        "SUMMARY:\nThe artifacts are aligned enough for human review.\n"
        "ARTIFACT_ALIGNMENT:\nTitle, script, and storyboard are aligned.\n"
        "EVIDENCE_STATUS:\nThe evidence review does not show unresolved contradictions.\n"
        "MISSING_OR_INCOMPLETE:\nNone.\n"
        "BLOCKERS:\nNone.\n"
        "NON_BLOCKING_IMPROVEMENTS:\nThumbnail text could be shorter.\n"
        "HUMAN_REVIEW_FOCUS:\nCheck branding tone and final phrasing."
    )

    assert isinstance(parsed, GamingPublicationReadinessReviewOutput)
    assert parsed.decision == "ready_for_human_review"


@pytest.mark.parametrize("decision", ["ready_for_human_review", "revise_before_human_review"])
def test_publication_decisions_accepted(decision: str) -> None:
    """Both supported publication-readiness decisions should be accepted."""

    parsed = parse_gaming_publication_readiness_review(
        f"DECISION:\n{decision}\n"
        "SUMMARY:\nSummary.\n"
        "ARTIFACT_ALIGNMENT:\nAligned.\n"
        "EVIDENCE_STATUS:\nEvidence reviewed.\n"
        "MISSING_OR_INCOMPLETE:\nNone.\n"
        "BLOCKERS:\nNone.\n"
        "NON_BLOCKING_IMPROVEMENTS:\nMinor polish only.\n"
        "HUMAN_REVIEW_FOCUS:\nFinal human judgment."
    )

    assert parsed.decision == decision


def test_invalid_publication_decision_rejected() -> None:
    """Unsupported publication-readiness decisions should fail safely."""

    with pytest.raises(StructuredValueError):
        parse_gaming_publication_readiness_review(
            "DECISION:\npublish_now\nSUMMARY:\nSummary.\nARTIFACT_ALIGNMENT:\nAligned.\nEVIDENCE_STATUS:\nReviewed.\n"
            "MISSING_OR_INCOMPLETE:\nNone.\nBLOCKERS:\nNone.\nNON_BLOCKING_IMPROVEMENTS:\nMinor.\nHUMAN_REVIEW_FOCUS:\nHuman check."
        )


def test_blank_required_review_fields_rejected() -> None:
    """Blank required review fields should fail safely."""

    with pytest.raises(StructuredOutputError):
        parse_gaming_script_quality_review(
            "DECISION:\naccept\nSUMMARY:\n   \nHOOK_REVIEW:\nHook.\nCLARITY_REVIEW:\nClarity.\n"
            "STRUCTURE_REVIEW:\nStructure.\nFACTUAL_RESTRAINT:\nRestraint.\nPACING_REVIEW:\nPacing.\n"
            "ENDING_REVIEW:\nEnding.\nISSUES:\nNone.\nRECOMMENDATIONS:\nRecommendations."
        )


def test_missing_review_fields_rejected() -> None:
    """Missing review fields should fail safely."""

    with pytest.raises(StructuredOutputError):
        parse_gaming_script_quality_review(
            "DECISION:\naccept\nSUMMARY:\nSummary.\nHOOK_REVIEW:\nHook.\nCLARITY_REVIEW:\nClarity.\n"
            "STRUCTURE_REVIEW:\nStructure.\nFACTUAL_RESTRAINT:\nRestraint.\nPACING_REVIEW:\nPacing.\n"
            "ENDING_REVIEW:\nEnding.\nISSUES:\nNone."
        )


def test_unknown_review_fields_rejected() -> None:
    """Unknown review fields should not be silently accepted."""

    with pytest.raises(StructuredOutputError):
        parse_gaming_storyboard_quality_review(
            "DECISION:\naccept\nSUMMARY:\nSummary.\nSCRIPT_FIDELITY:\nFidelity.\nHOOK_SCENE:\nHook.\n"
            "SCENE_SEQUENCE:\nSequence.\nVISUAL_CLARITY:\nClarity.\nPACING:\nPacing.\nENDING_SCENE:\nEnding.\n"
            "UNSUPPORTED_VISUALS:\nNone.\nISSUES:\nIssues.\nRECOMMENDATIONS:\nRecommendations.\nEXTRA:\nNope."
        )


def test_review_models_serialize_and_restore() -> None:
    """Review output models should round-trip predictably."""

    script = GamingScriptQualityReviewOutput(
        decision="accept",
        summary="The script is clear and focused.",
        hook_review="The hook creates immediate curiosity.",
        clarity_review="The lines are easy to follow aloud.",
        structure_review="The script maintains one main idea.",
        factual_restraint="Claims stay cautious relative to the evidence.",
        pacing_review="The pacing fits the short target.",
        ending_review="The ending resolves the promise naturally.",
        issues="None.",
        recommendations="Keep the phrasing concise.",
    )
    evidence = GamingEvidenceConsistencyReviewOutput(
        decision="consistent",
        summary="The claims align with supplied evidence.",
        supported_claims="The core mechanic claim is supported.",
        unsupported_claims="None.",
        contradictions="None.",
        uncertainties="Minor uncertainty remains around edge cases.",
        overstatements="None.",
        recommendations="Keep cautious wording.",
    )
    storyboard = GamingStoryboardQualityReviewOutput(
        decision="revise",
        summary="The storyboard mostly works but needs one fix.",
        script_fidelity="Most scenes match the script.",
        hook_scene="The opening scene supports the hook.",
        scene_sequence="The order is mostly clear.",
        visual_clarity="The visual instructions are readable.",
        pacing="The middle scene runs slightly long.",
        ending_scene="The final scene supports the ending.",
        unsupported_visuals="One visual claim needs caution.",
        issues="Scene two should be tighter.",
        recommendations="Trim the middle scene and simplify one shot.",
    )
    publication = GamingPublicationReadinessReviewOutput(
        decision="ready_for_human_review",
        summary="The artifacts are aligned enough for human review.",
        artifact_alignment="Title, script, and storyboard are aligned.",
        evidence_status="The evidence review does not show unresolved contradictions.",
        missing_or_incomplete="None.",
        blockers="None.",
        non_blocking_improvements="Thumbnail text could be shorter.",
        human_review_focus="Check branding tone and final phrasing.",
    )

    assert GamingScriptQualityReviewOutput.model_validate(script.model_dump()) == script
    assert GamingEvidenceConsistencyReviewOutput.model_validate(evidence.model_dump()) == evidence
    assert GamingStoryboardQualityReviewOutput.model_validate(storyboard.model_dump()) == storyboard
    assert GamingPublicationReadinessReviewOutput.model_validate(publication.model_dump()) == publication


def test_review_raw_output_excluded_from_errors() -> None:
    """Review parser errors should not expose raw response text."""

    raw_text = (
        "DECISION:\ninvalid\n"
        "SUMMARY:\nsecret review summary\n"
        "HOOK_REVIEW:\nHook.\n"
        "CLARITY_REVIEW:\nClarity.\n"
        "STRUCTURE_REVIEW:\nStructure.\n"
        "FACTUAL_RESTRAINT:\nRestraint.\n"
        "PACING_REVIEW:\nPacing.\n"
        "ENDING_REVIEW:\nEnding.\n"
        "ISSUES:\nNone.\n"
        "RECOMMENDATIONS:\nRecommendations."
    )

    with pytest.raises(StructuredValueError) as exc_info:
        parse_gaming_script_quality_review(raw_text)

    assert raw_text not in str(exc_info.value)
    assert "secret review summary" not in str(exc_info.value)


def test_review_parser_has_no_workflow_side_effects() -> None:
    """Review parsers should return advisory data only and not mutate workflow state."""

    parsed = parse_gaming_publication_readiness_review(
        "DECISION:\nready_for_human_review\n"
        "SUMMARY:\nThe artifacts are aligned enough for human review.\n"
        "ARTIFACT_ALIGNMENT:\nTitle, script, and storyboard are aligned.\n"
        "EVIDENCE_STATUS:\nThe evidence review does not show unresolved contradictions.\n"
        "MISSING_OR_INCOMPLETE:\nNone.\n"
        "BLOCKERS:\nNone.\n"
        "NON_BLOCKING_IMPROVEMENTS:\nThumbnail text could be shorter.\n"
        "HUMAN_REVIEW_FOCUS:\nCheck branding tone and final phrasing."
    )

    assert parsed.decision == "ready_for_human_review"
    assert not hasattr(parsed, "workflow_state")


def test_review_parsers_require_no_provider_calls() -> None:
    """Review parsers should operate only on supplied text."""

    parsed = parse_gaming_evidence_consistency_review(
        "DECISION:\nrevise\n"
        "SUMMARY:\nSome claims need caution.\n"
        "SUPPORTED_CLAIMS:\nThe core mechanic claim is supported.\n"
        "UNSUPPORTED_CLAIMS:\nOne supporting detail is weak.\n"
        "CONTRADICTIONS:\nNone.\n"
        "UNCERTAINTIES:\nEdge cases remain uncertain.\n"
        "OVERSTATEMENTS:\nOne line sounds too certain.\n"
        "RECOMMENDATIONS:\nUse more cautious wording."
    )

    assert parsed.decision == "revise"
