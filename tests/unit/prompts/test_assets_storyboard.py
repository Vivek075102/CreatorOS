"""Tests for the builtin gaming storyboard prompt assets."""

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

STORYBOARD_PROMPT_PATHS = [
    Path("storyboard/gaming_scene_motion_prompt.v1.json"),
    Path("storyboard/gaming_scene_visual_prompt.v1.json"),
    Path("storyboard/storyboard_scene_breakdown.v1.json"),
    Path("storyboard/storyboard_timing_review.v1.json"),
    Path("storyboard/storyboard_visual_direction.v1.json"),
]


def _repo_prompts_dir() -> Path:
    """Return the repository prompt root directory."""

    return Path(__file__).resolve().parents[3] / "prompts"


def test_exactly_five_storyboard_prompt_json_files_exist() -> None:
    """The repository should contain exactly the five builtin storyboard prompts."""

    prompts_root = _repo_prompts_dir()
    json_paths = sorted(path.relative_to(prompts_root) for path in (prompts_root / "storyboard").rglob("*.json"))

    assert json_paths == sorted(STORYBOARD_PROMPT_PATHS)


def test_all_five_storyboard_assets_load_as_prompt_definitions() -> None:
    """Each builtin storyboard prompt asset should load as a PromptDefinition."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    loaded = [loader.load_file(path) for path in STORYBOARD_PROMPT_PATHS]

    assert all(isinstance(definition, PromptDefinition) for definition in loaded)


def test_all_five_storyboard_assets_are_active_version_one_assets() -> None:
    """Builtin storyboard prompts should be active version-one assets."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    definitions = [loader.load_file(path) for path in STORYBOARD_PROMPT_PATHS]

    assert [definition.status for definition in definitions] == [PromptStatus.ACTIVE] * 5
    assert [definition.version for definition in definitions] == [1, 1, 1, 1, 1]


def test_storyboard_prompt_names_match_filenames_and_category() -> None:
    """Builtin storyboard prompt names should match filenames and live under storyboard."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in STORYBOARD_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.name == relative_path.name.split(".v", 1)[0]
        assert relative_path.parts[0] == PromptAssetCategory.STORYBOARD.value


def test_storyboard_prompt_metadata_marks_gaming_storyboard_domain() -> None:
    """Builtin storyboard prompts should carry the expected metadata contract."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in STORYBOARD_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.metadata["domain"] == "gaming"
        assert definition.metadata["stage"] == "storyboard"
        assert definition.metadata["owner"] == "creatoros"
        assert definition.metadata["provider_independent"] is True


def test_storyboard_prompt_assets_do_not_include_vendor_model_or_api_language() -> None:
    """Builtin storyboard prompt assets should remain provider-independent and safe."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in STORYBOARD_PROMPT_PATHS).casefold()

    for forbidden in ["openai", "anthropic", "gemini", "ollama", "api_key", "http://", "https://"]:
        assert forbidden not in normalized


def test_storyboard_prompt_assets_do_not_claim_browsing_or_live_internet_access() -> None:
    """Builtin storyboard prompt assets should not pretend they can browse or access live data."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in STORYBOARD_PROMPT_PATHS).casefold()

    assert "live internet access" not in normalized
    assert "browse the web" not in normalized
    assert "browsing" not in normalized


def test_storyboard_prompt_variables_match_the_documented_contracts() -> None:
    """Builtin storyboard prompt variables should match the documented contracts."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    motion = loader.load_file(STORYBOARD_PROMPT_PATHS[0])
    scene_visual = loader.load_file(STORYBOARD_PROMPT_PATHS[1])
    breakdown = loader.load_file(STORYBOARD_PROMPT_PATHS[2])
    timing = loader.load_file(STORYBOARD_PROMPT_PATHS[3])
    visual = loader.load_file(STORYBOARD_PROMPT_PATHS[4])

    assert [variable.name for variable in breakdown.variables] == [
        "title",
        "game",
        "platform",
        "hook",
        "body",
        "ending",
        "call_to_action",
        "target_duration_seconds",
    ]
    assert [variable.name for variable in motion.variables] == [
        "game",
        "scene_number",
        "scene_purpose",
        "visual_summary",
        "script_beat",
        "duration_seconds",
        "platform",
    ]
    assert [variable.name for variable in scene_visual.variables] == [
        "game",
        "scene_number",
        "scene_purpose",
        "script_beat",
        "visual_direction",
        "on_screen_text",
        "platform",
    ]
    assert [variable.name for variable in visual.variables] == [
        "game",
        "scene_number",
        "scene_purpose",
        "script_beat",
        "visual_summary",
        "platform",
        "duration_seconds",
    ]
    assert [variable.name for variable in timing.variables] == [
        "title",
        "scene_summary",
        "target_duration_seconds",
        "platform",
    ]


def test_storyboard_prompt_contents_include_required_output_labels() -> None:
    """Builtin storyboard prompt bodies should contain the required output labels."""

    prompts_root = _repo_prompts_dir()
    motion_payload = json.loads((prompts_root / STORYBOARD_PROMPT_PATHS[0]).read_text(encoding="utf-8"))
    scene_visual_payload = json.loads((prompts_root / STORYBOARD_PROMPT_PATHS[1]).read_text(encoding="utf-8"))
    breakdown_payload = json.loads((prompts_root / STORYBOARD_PROMPT_PATHS[2]).read_text(encoding="utf-8"))
    timing_payload = json.loads((prompts_root / STORYBOARD_PROMPT_PATHS[3]).read_text(encoding="utf-8"))
    visual_payload = json.loads((prompts_root / STORYBOARD_PROMPT_PATHS[4]).read_text(encoding="utf-8"))

    motion_content = "\n".join(message["content"] for message in motion_payload["messages"])
    scene_visual_content = "\n".join(message["content"] for message in scene_visual_payload["messages"])
    breakdown_content = "\n".join(message["content"] for message in breakdown_payload["messages"])
    timing_content = "\n".join(message["content"] for message in timing_payload["messages"])
    visual_content = "\n".join(message["content"] for message in visual_payload["messages"])

    for label in [
        "STORYBOARD_TITLE:",
        "SCENE_1:",
        "PURPOSE:",
        "SCRIPT_BEAT:",
        "VISUAL:",
        "ON_SCREEN_TEXT:",
        "DURATION_SECONDS:",
        "FINAL_SCENE_COUNT:",
        "TOTAL_ESTIMATED_DURATION_SECONDS:",
    ]:
        assert label in breakdown_content
    for label in ["SCENE_NUMBER:", "PRIMARY_MOTION:", "SUBJECT_MOVEMENT:", "CAMERA_DIRECTION:", "TRANSITION_GUIDANCE:", "PACING:", "DURATION_SECONDS:", "AVOID:"]:
        assert label in motion_content
    for label in ["SCENE_NUMBER:", "SUBJECT:", "ENVIRONMENT:", "ACTION:", "COMPOSITION:", "MOOD:", "ON_SCREEN_TEXT:", "STYLE_DIRECTION:", "NEGATIVE_GUIDANCE:"]:
        assert label in scene_visual_content
    for label in ["SCENE_NUMBER:", "PRIMARY_VISUAL:", "COMPOSITION:", "MOTION:", "ON_SCREEN_TEXT:", "STYLE_NOTES:", "AVOID:"]:
        assert label in visual_content
    for label in ["DECISION:", "TOTAL_DURATION_ASSESSMENT:", "PACING:", "SCENE_ISSUES:", "RECOMMENDATIONS:"]:
        assert label in timing_content


def test_storyboard_scene_breakdown_safeguards_are_present() -> None:
    """The scene breakdown prompt should include the expected sequencing and timing safeguards."""

    text = (_repo_prompts_dir() / "storyboard/storyboard_scene_breakdown.v1.json").read_text(encoding="utf-8")

    assert "Scene numbers must remain sequential." in text
    assert "No individual scene duration may be zero or negative." in text
    assert "Preserve the script's core meaning." in text
    assert "Do not invent factual claims." in text
    assert "Total scene duration should approximately match TARGET_DURATION_SECONDS." in text
    assert "The first scene must support the hook." in text
    assert "The final scene must support the ending or CTA." in text


def test_storyboard_visual_direction_safeguards_are_present() -> None:
    """The visual direction prompt should remain provider-independent and scene-stable."""

    text = (_repo_prompts_dir() / "storyboard/storyboard_visual_direction.v1.json").read_text(encoding="utf-8")

    assert "Describe visual composition rather than provider settings." in text
    assert "Do not use model-specific keywords" in text
    assert "Distinguish optional stylistic direction from factual scene content." in text
    assert "SCENE_NUMBER must remain the same as supplied." in text
    assert "AVOID:" in text


def test_storyboard_timing_review_safeguards_are_present() -> None:
    """The timing review prompt should stay bounded to supplied timing information."""

    text = (_repo_prompts_dir() / "storyboard/storyboard_timing_review.v1.json").read_text(encoding="utf-8")

    assert "Do not invent missing durations." in text
    assert "Consider hook pacing and ending clarity." in text
    assert "accept | revise" in text
    assert "Recommendations must be concise." in text


def test_storyboard_prompt_assets_serialize_and_restore_predictably() -> None:
    """Builtin storyboard prompt definitions should round-trip predictably."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in STORYBOARD_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        restored = PromptDefinition.model_validate(definition.model_dump(mode="python"))
        assert restored == definition


def test_manifest_contains_exactly_thirteen_entries_with_five_storyboard_entries() -> None:
    """The manifest should include the current prompt inventory with five storyboard entries."""

    manifest = PromptManifestLoader(base_dir=_repo_prompts_dir()).load()

    assert len(manifest.entries) == 13
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.STORYBOARD]) == 5


def test_manifest_storyboard_checksums_match_current_file_contents() -> None:
    """Manifest checksums for storyboard prompts should match exact file bytes."""

    prompts_root = _repo_prompts_dir()
    manifest = PromptManifestLoader(base_dir=prompts_root).load()
    manifest_by_path = {entry.path: entry for entry in manifest.entries}

    for relative_path in STORYBOARD_PROMPT_PATHS:
        path_text = relative_path.as_posix()
        assert manifest_by_path[path_text].checksum == hashlib.sha256((prompts_root / relative_path).read_bytes()).hexdigest()


def test_storyboard_directory_has_no_gitkeep_entry() -> None:
    """The storyboard prompt directory should no longer need a .gitkeep placeholder."""

    assert not (_repo_prompts_dir() / "storyboard" / ".gitkeep").exists()
