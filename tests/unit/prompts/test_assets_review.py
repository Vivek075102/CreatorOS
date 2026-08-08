"""Tests for builtin gaming review prompt assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from creatoros.prompts import (
    PromptAssetCategory,
    PromptDefinition,
    PromptLoader,
    PromptManifestLoader,
    PromptStatus,
)

REVIEW_PROMPT_PATHS = [
    Path("review/gaming_evidence_consistency_review.v1.json"),
    Path("review/gaming_publication_readiness_review.v1.json"),
    Path("review/gaming_script_quality_review.v1.json"),
    Path("review/gaming_storyboard_quality_review.v1.json"),
]


def _repo_prompts_dir() -> Path:
    """Return the repository prompt root directory."""

    return Path(__file__).resolve().parents[3] / "prompts"


def test_exactly_four_review_prompt_json_files_exist() -> None:
    """The repository should contain exactly four review prompt JSON assets."""

    prompts_root = _repo_prompts_dir()
    json_paths = sorted(path.relative_to(prompts_root) for path in (prompts_root / "review").rglob("*.json"))

    assert json_paths == REVIEW_PROMPT_PATHS


def test_all_four_review_assets_load_as_prompt_definitions() -> None:
    """Each review prompt asset should load as a PromptDefinition."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    loaded = [loader.load_file(path) for path in REVIEW_PROMPT_PATHS]

    assert all(isinstance(definition, PromptDefinition) for definition in loaded)


def test_all_four_review_assets_are_active_version_one_assets() -> None:
    """Review prompt assets should be active version-one assets."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    definitions = [loader.load_file(path) for path in REVIEW_PROMPT_PATHS]

    assert [definition.status for definition in definitions] == [PromptStatus.ACTIVE] * 4
    assert [definition.version for definition in definitions] == [1, 1, 1, 1]


def test_review_prompt_names_match_filenames_and_category() -> None:
    """Review prompt names should match filenames and belong to the review category."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in REVIEW_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.name == relative_path.name.split(".v", 1)[0]
        assert relative_path.parts[0] == PromptAssetCategory.REVIEW.value


def test_review_prompt_metadata_marks_gaming_review_domain() -> None:
    """Review prompts should carry the expected metadata contract."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in REVIEW_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.metadata["domain"] == "gaming"
        assert definition.metadata["stage"] == "review"
        assert definition.metadata["owner"] == "creatoros"
        assert definition.metadata["provider_independent"] is True


def test_review_prompt_assets_do_not_include_vendor_model_api_or_url_references() -> None:
    """Review prompt assets should remain provider-independent and safe."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in REVIEW_PROMPT_PATHS).casefold()

    for forbidden in ["openai", "anthropic", "gemini", "ollama", "api_key", "http://", "https://", "model id"]:
        assert forbidden not in normalized


def test_review_prompt_assets_do_not_claim_live_browsing_or_external_research() -> None:
    """Review prompt assets should not imply browsing or external fact-checking."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in REVIEW_PROMPT_PATHS).casefold()

    for forbidden in ["live internet access", "browse the web", "internet access", "external research"]:
        assert forbidden not in normalized


def test_review_prompt_assets_do_not_request_hidden_chain_of_thought() -> None:
    """Review prompt assets should not request hidden reasoning traces."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in REVIEW_PROMPT_PATHS).casefold()

    for forbidden in ["chain-of-thought", "chain of thought", "hidden reasoning", "show your reasoning step by step"]:
        assert forbidden not in normalized


def test_review_prompt_variables_match_exact_contracts() -> None:
    """Review prompt variable definitions should match the documented contracts."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    evidence = loader.load_file(REVIEW_PROMPT_PATHS[0])
    publication = loader.load_file(REVIEW_PROMPT_PATHS[1])
    script = loader.load_file(REVIEW_PROMPT_PATHS[2])
    storyboard = loader.load_file(REVIEW_PROMPT_PATHS[3])

    assert [variable.name for variable in script.variables] == [
        "title",
        "game",
        "topic",
        "angle",
        "source_summary",
        "script_text",
        "platform",
        "target_duration_seconds",
    ]
    assert [variable.name for variable in evidence.variables] == [
        "game",
        "source_summary",
        "research_notes",
        "content_text",
        "content_stage",
    ]
    assert [variable.name for variable in storyboard.variables] == [
        "title",
        "game",
        "script_text",
        "storyboard_text",
        "platform",
        "target_duration_seconds",
    ]
    assert [variable.name for variable in publication.variables] == [
        "title",
        "game",
        "script_text",
        "storyboard_summary",
        "thumbnail_summary",
        "narration_summary",
        "evidence_review",
        "platform",
    ]


def test_review_prompt_contents_include_required_output_labels() -> None:
    """Review prompt bodies should contain the required output labels."""

    prompts_root = _repo_prompts_dir()
    evidence_payload = json.loads((prompts_root / REVIEW_PROMPT_PATHS[0]).read_text(encoding="utf-8"))
    publication_payload = json.loads((prompts_root / REVIEW_PROMPT_PATHS[1]).read_text(encoding="utf-8"))
    script_payload = json.loads((prompts_root / REVIEW_PROMPT_PATHS[2]).read_text(encoding="utf-8"))
    storyboard_payload = json.loads((prompts_root / REVIEW_PROMPT_PATHS[3]).read_text(encoding="utf-8"))

    evidence_content = "\n".join(message["content"] for message in evidence_payload["messages"])
    publication_content = "\n".join(message["content"] for message in publication_payload["messages"])
    script_content = "\n".join(message["content"] for message in script_payload["messages"])
    storyboard_content = "\n".join(message["content"] for message in storyboard_payload["messages"])

    for label in ["DECISION:", "SUMMARY:", "HOOK_REVIEW:", "CLARITY_REVIEW:", "STRUCTURE_REVIEW:", "FACTUAL_RESTRAINT:", "PACING_REVIEW:", "ENDING_REVIEW:", "ISSUES:", "RECOMMENDATIONS:"]:
        assert label in script_content
    for label in ["DECISION:", "SUMMARY:", "SUPPORTED_CLAIMS:", "UNSUPPORTED_CLAIMS:", "CONTRADICTIONS:", "UNCERTAINTIES:", "OVERSTATEMENTS:", "RECOMMENDATIONS:"]:
        assert label in evidence_content
    for label in ["DECISION:", "SUMMARY:", "SCRIPT_FIDELITY:", "HOOK_SCENE:", "SCENE_SEQUENCE:", "VISUAL_CLARITY:", "PACING:", "ENDING_SCENE:", "UNSUPPORTED_VISUALS:", "ISSUES:", "RECOMMENDATIONS:"]:
        assert label in storyboard_content
    for label in ["DECISION:", "SUMMARY:", "ARTIFACT_ALIGNMENT:", "EVIDENCE_STATUS:", "MISSING_OR_INCOMPLETE:", "BLOCKERS:", "NON_BLOCKING_IMPROVEMENTS:", "HUMAN_REVIEW_FOCUS:"]:
        assert label in publication_content


def test_script_review_safeguards_are_present() -> None:
    """The script review prompt should include its required safeguards."""

    text = (_repo_prompts_dir() / REVIEW_PROMPT_PATHS[2]).read_text(encoding="utf-8")

    assert "Check whether the hook is clear." in text
    assert "Check spoken clarity and natural phrasing." in text
    assert "Identify unsupported statements only relative to SOURCE_SUMMARY." in text
    assert "Consider whether script length and pacing appear reasonable for TARGET_DURATION_SECONDS." in text
    assert "Do not independently verify facts." in text
    assert "Do not rewrite the complete script." in text


def test_evidence_review_safeguards_are_present() -> None:
    """The evidence review prompt should preserve supplied-evidence boundaries."""

    text = (_repo_prompts_dir() / REVIEW_PROMPT_PATHS[0]).read_text(encoding="utf-8")

    assert "Supplied evidence is the only evidence source." in text
    assert "Identify claims not supported by supplied evidence." in text
    assert "Distinguish unsupported from contradicted." in text
    assert "Do not convert uncertainty into certainty." in text
    assert "consistent | revise | insufficient_evidence" in text
    assert "Do not fabricate citations." in text
    assert "Do not fabricate sources." in text


def test_storyboard_review_safeguards_are_present() -> None:
    """The storyboard review prompt should enforce fidelity and media-preparation constraints."""

    text = (_repo_prompts_dir() / REVIEW_PROMPT_PATHS[3]).read_text(encoding="utf-8")

    assert "Check storyboard fidelity to script." in text
    assert "Check that the first scene supports the hook." in text
    assert "Check that the final scene supports the ending or call to action." in text
    assert "Check whether estimated pacing reasonably fits TARGET_DURATION_SECONDS." in text
    assert "Check unsupported visual claims." in text
    assert "Do not assume images or videos have been generated." in text


def test_publication_review_safeguards_are_present() -> None:
    """The publication-readiness review prompt should preserve human authority."""

    text = (_repo_prompts_dir() / REVIEW_PROMPT_PATHS[1]).read_text(encoding="utf-8")

    assert "Do not bypass human approval." in text
    assert "ready_for_human_review does not mean approved for publication." in text
    assert "Check obvious cross-artifact inconsistencies." in text
    assert "Identify unresolved evidence concerns." in text
    assert "Distinguish blockers from non-blocking improvements." in text
    assert "Never state that content is guaranteed safe, compliant, accurate, or platform-approved." in text


def test_manifest_contains_exactly_seventeen_entries_with_four_review_entries() -> None:
    """The manifest should include the current prompt inventory with four review entries."""

    manifest = PromptManifestLoader(base_dir=_repo_prompts_dir()).load()

    assert len(manifest.entries) == 17
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.REVIEW]) == 4


def test_manifest_review_checksums_match_current_file_contents() -> None:
    """Manifest checksums for review prompts should match exact file bytes."""

    prompts_root = _repo_prompts_dir()
    manifest = PromptManifestLoader(base_dir=prompts_root).load()
    manifest_by_path = {entry.path: entry for entry in manifest.entries}

    for relative_path in REVIEW_PROMPT_PATHS:
        path_text = relative_path.as_posix()
        assert manifest_by_path[path_text].checksum == hashlib.sha256((prompts_root / relative_path).read_bytes()).hexdigest()


def test_review_directory_has_no_gitkeep_entry() -> None:
    """The review prompt directory should no longer need a .gitkeep placeholder."""

    assert not (_repo_prompts_dir() / "review" / ".gitkeep").exists()


def test_review_prompt_assets_serialize_and_restore_predictably() -> None:
    """Review prompt definitions should round-trip predictably."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in REVIEW_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        restored = PromptDefinition.model_validate(definition.model_dump(mode="python"))
        assert restored == definition
