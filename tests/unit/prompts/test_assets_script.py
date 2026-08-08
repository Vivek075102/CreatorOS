"""Tests for the builtin gaming script prompt assets."""

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

SCRIPT_PROMPT_PATHS = [
    Path("script/gaming_cta.v1.json"),
    Path("script/gaming_hook.v1.json"),
    Path("script/youtube_shorts_script.v1.json"),
]


def _repo_prompts_dir() -> Path:
    """Return the repository prompt root directory."""

    return Path(__file__).resolve().parents[3] / "prompts"


def test_exactly_three_script_prompt_json_files_exist() -> None:
    """The repository should contain exactly the three builtin script prompts."""

    prompts_root = _repo_prompts_dir()
    json_paths = sorted(path.relative_to(prompts_root) for path in (prompts_root / "script").rglob("*.json"))

    assert json_paths == sorted(SCRIPT_PROMPT_PATHS)


def test_all_three_script_assets_load_as_prompt_definitions() -> None:
    """Each builtin script prompt asset should load as a PromptDefinition."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    loaded = [loader.load_file(path) for path in SCRIPT_PROMPT_PATHS]

    assert all(isinstance(definition, PromptDefinition) for definition in loaded)


def test_all_three_script_assets_are_active_version_one_assets() -> None:
    """Builtin script prompts should be active version-one assets."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    definitions = [loader.load_file(path) for path in SCRIPT_PROMPT_PATHS]

    assert [definition.status for definition in definitions] == [PromptStatus.ACTIVE] * 3
    assert [definition.version for definition in definitions] == [1, 1, 1]


def test_script_prompt_names_match_filenames_and_category() -> None:
    """Builtin script prompt names should match filenames and live under script."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in SCRIPT_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.name == relative_path.name.split(".v", 1)[0]
        assert relative_path.parts[0] == PromptAssetCategory.SCRIPT.value


def test_script_prompt_metadata_marks_gaming_script_domain() -> None:
    """Builtin script prompts should carry the expected metadata contract."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in SCRIPT_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.metadata["domain"] == "gaming"
        assert definition.metadata["stage"] == "script"
        assert definition.metadata["owner"] == "creatoros"
        assert definition.metadata["provider_independent"] is True


def test_script_prompt_assets_do_not_include_vendor_model_or_api_language() -> None:
    """Builtin script prompt assets should remain provider-independent and safe."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in SCRIPT_PROMPT_PATHS).casefold()

    for forbidden in ["openai", "anthropic", "gemini", "ollama", "api", "api_key", "http://", "https://", "model"]:
        assert forbidden not in normalized


def test_script_prompt_assets_do_not_claim_browsing_or_live_internet_access() -> None:
    """Builtin script prompts should not pretend they can browse or access live data."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in SCRIPT_PROMPT_PATHS).casefold()

    assert "live internet access" not in normalized
    assert "browse the web" not in normalized
    assert "browsing" not in normalized


def test_script_prompt_variables_match_the_documented_contracts() -> None:
    """Builtin script prompt variables should match the documented contracts."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    cta = loader.load_file(SCRIPT_PROMPT_PATHS[0])
    hook = loader.load_file(SCRIPT_PROMPT_PATHS[1])
    script = loader.load_file(SCRIPT_PROMPT_PATHS[2])

    assert [variable.name for variable in script.variables] == [
        "title",
        "game",
        "topic",
        "angle",
        "hook_direction",
        "platform",
        "target_duration_seconds",
        "source_summary",
    ]
    assert [variable.name for variable in hook.variables] == [
        "game",
        "title",
        "topic",
        "angle",
        "source_summary",
        "platform",
    ]
    assert [variable.name for variable in cta.variables] == [
        "game",
        "topic",
        "platform",
        "tone",
    ]


def test_script_prompt_contents_include_required_output_labels() -> None:
    """Builtin script prompt bodies should contain the required output labels."""

    prompts_root = _repo_prompts_dir()
    cta_payload = json.loads((prompts_root / SCRIPT_PROMPT_PATHS[0]).read_text(encoding="utf-8"))
    hook_payload = json.loads((prompts_root / SCRIPT_PROMPT_PATHS[1]).read_text(encoding="utf-8"))
    script_payload = json.loads((prompts_root / SCRIPT_PROMPT_PATHS[2]).read_text(encoding="utf-8"))

    cta_content = "\n".join(message["content"] for message in cta_payload["messages"])
    hook_content = "\n".join(message["content"] for message in hook_payload["messages"])
    script_content = "\n".join(message["content"] for message in script_payload["messages"])

    for label in ["TITLE:", "HOOK:", "BODY:", "ENDING:", "CALL_TO_ACTION:", "ESTIMATED_DURATION_SECONDS:", "EVIDENCE_NOTE:"]:
        assert label in script_content
    for label in ["HOOK_1:", "HOOK_2:", "HOOK_3:", "BEST_HOOK:", "WHY:"]:
        assert label in hook_content
    for label in ["CTA:", "ALTERNATIVE:"]:
        assert label in cta_content


def test_script_prompt_content_safeguards_are_present() -> None:
    """Builtin script prompts should include the expected evidence and safety instructions."""

    prompts_root = _repo_prompts_dir()
    script_text = (prompts_root / SCRIPT_PROMPT_PATHS[2]).read_text(encoding="utf-8")
    hook_text = (prompts_root / SCRIPT_PROMPT_PATHS[1]).read_text(encoding="utf-8")
    cta_text = (prompts_root / SCRIPT_PROMPT_PATHS[0]).read_text(encoding="utf-8")

    assert "Do not invent statistics." in script_text
    assert "Do not invent quotes." in script_text
    assert "Do not fabricate patch notes, release dates, developer statements, or player counts." in script_text
    assert "No fake urgency." in hook_text
    assert "Do not use misleading certainty." in hook_text
    assert "No begging for likes or subscriptions." in cta_text
    assert "No manipulative pressure." in cta_text


def test_script_prompt_assets_serialize_and_restore_predictably() -> None:
    """Builtin script prompt definitions should round-trip predictably."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in SCRIPT_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        restored = PromptDefinition.model_validate(definition.model_dump(mode="python"))
        assert restored == definition


def test_manifest_contains_nine_entries_with_three_script_entries() -> None:
    """The manifest should include the research, script, and storyboard builtin prompts."""

    manifest = PromptManifestLoader(base_dir=_repo_prompts_dir()).load()

    assert len(manifest.entries) == 9
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.RESEARCH]) == 3
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.SCRIPT]) == 3


def test_manifest_script_checksums_match_current_file_contents() -> None:
    """Manifest checksums for script prompts should match exact file bytes."""

    prompts_root = _repo_prompts_dir()
    manifest = PromptManifestLoader(base_dir=prompts_root).load()
    manifest_by_path = {entry.path: entry for entry in manifest.entries}

    for relative_path in SCRIPT_PROMPT_PATHS:
        path_text = relative_path.as_posix()
        assert manifest_by_path[path_text].checksum == hashlib.sha256((prompts_root / relative_path).read_bytes()).hexdigest()


def test_script_directory_has_no_gitkeep_entry() -> None:
    """The script prompt directory should no longer need a .gitkeep placeholder."""

    assert not (_repo_prompts_dir() / "script" / ".gitkeep").exists()
