"""Tests for builtin gaming media-related prompt assets."""

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

THUMBNAIL_PROMPT_PATHS = [Path("thumbnail/gaming_thumbnail_concept.v1.json")]
NARRATION_PROMPT_PATHS = [Path("narration/gaming_narration_direction.v1.json")]
MEDIA_STORYBOARD_PROMPT_PATHS = [
    Path("storyboard/gaming_scene_motion_prompt.v1.json"),
    Path("storyboard/gaming_scene_visual_prompt.v1.json"),
    Path("storyboard/storyboard_scene_breakdown.v1.json"),
    Path("storyboard/storyboard_timing_review.v1.json"),
    Path("storyboard/storyboard_visual_direction.v1.json"),
]
NEW_MEDIA_PROMPT_PATHS = [
    Path("thumbnail/gaming_thumbnail_concept.v1.json"),
    Path("storyboard/gaming_scene_motion_prompt.v1.json"),
    Path("storyboard/gaming_scene_visual_prompt.v1.json"),
    Path("narration/gaming_narration_direction.v1.json"),
]


def _repo_prompts_dir() -> Path:
    """Return the repository prompt root directory."""

    return Path(__file__).resolve().parents[3] / "prompts"


def test_exactly_one_thumbnail_prompt_json_exists() -> None:
    """The repository should contain exactly one thumbnail prompt JSON asset."""

    prompts_root = _repo_prompts_dir()
    json_paths = sorted(path.relative_to(prompts_root) for path in (prompts_root / "thumbnail").rglob("*.json"))

    assert json_paths == THUMBNAIL_PROMPT_PATHS


def test_exactly_one_narration_prompt_json_exists() -> None:
    """The repository should contain exactly one narration prompt JSON asset."""

    prompts_root = _repo_prompts_dir()
    json_paths = sorted(path.relative_to(prompts_root) for path in (prompts_root / "narration").rglob("*.json"))

    assert json_paths == NARRATION_PROMPT_PATHS


def test_exactly_five_storyboard_prompt_json_assets_exist() -> None:
    """The repository should now contain five storyboard prompt JSON assets."""

    prompts_root = _repo_prompts_dir()
    json_paths = sorted(path.relative_to(prompts_root) for path in (prompts_root / "storyboard").rglob("*.json"))

    assert json_paths == sorted(MEDIA_STORYBOARD_PROMPT_PATHS)


def test_new_media_prompt_assets_load_successfully() -> None:
    """The newly added media-related prompt assets should load as PromptDefinition objects."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    loaded = [loader.load_file(path) for path in NEW_MEDIA_PROMPT_PATHS]

    assert all(isinstance(definition, PromptDefinition) for definition in loaded)


def test_new_media_prompt_assets_are_active_version_one_assets() -> None:
    """The newly added media-related prompt assets should be active version-one assets."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    definitions = [loader.load_file(path) for path in NEW_MEDIA_PROMPT_PATHS]

    assert [definition.status for definition in definitions] == [PromptStatus.ACTIVE] * 4
    assert [definition.version for definition in definitions] == [1, 1, 1, 1]


def test_new_media_prompt_names_match_filenames_and_categories() -> None:
    """The new media prompt names should match filenames and live in the correct categories."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in NEW_MEDIA_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        assert definition.name == relative_path.name.split(".v", 1)[0]

    assert THUMBNAIL_PROMPT_PATHS[0].parts[0] == PromptAssetCategory.THUMBNAIL.value
    assert NARRATION_PROMPT_PATHS[0].parts[0] == PromptAssetCategory.NARRATION.value
    assert Path("storyboard/gaming_scene_visual_prompt.v1.json").parts[0] == PromptAssetCategory.STORYBOARD.value
    assert Path("storyboard/gaming_scene_motion_prompt.v1.json").parts[0] == PromptAssetCategory.STORYBOARD.value


def test_new_media_prompt_metadata_stage_values_are_correct() -> None:
    """The new media prompt metadata should use the expected stage values."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    thumbnail = loader.load_file(THUMBNAIL_PROMPT_PATHS[0])
    narration = loader.load_file(NARRATION_PROMPT_PATHS[0])
    visual = loader.load_file(Path("storyboard/gaming_scene_visual_prompt.v1.json"))
    motion = loader.load_file(Path("storyboard/gaming_scene_motion_prompt.v1.json"))

    assert thumbnail.metadata["stage"] == "thumbnail"
    assert narration.metadata["stage"] == "narration"
    assert visual.metadata["stage"] == "storyboard"
    assert motion.metadata["stage"] == "storyboard"


def test_new_media_prompt_assets_contain_no_vendor_model_api_references() -> None:
    """The new media prompt assets should remain provider-independent and safe."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in NEW_MEDIA_PROMPT_PATHS).casefold()

    for forbidden in ["openai", "anthropic", "gemini", "ollama", "api_key", "http://", "https://"]:
        assert forbidden not in normalized


def test_new_media_prompt_assets_contain_no_live_browsing_claims() -> None:
    """The new media prompt assets should not imply internet access or browsing."""

    prompts_root = _repo_prompts_dir()
    normalized = "\n".join((prompts_root / path).read_text(encoding="utf-8") for path in NEW_MEDIA_PROMPT_PATHS).casefold()

    assert "live internet access" not in normalized
    assert "browse the web" not in normalized
    assert "internet access" not in normalized


def test_new_media_prompt_variables_match_exact_specifications() -> None:
    """The new media prompt variable contracts should match the documented specifications."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())
    thumbnail = loader.load_file(THUMBNAIL_PROMPT_PATHS[0])
    visual = loader.load_file(Path("storyboard/gaming_scene_visual_prompt.v1.json"))
    motion = loader.load_file(Path("storyboard/gaming_scene_motion_prompt.v1.json"))
    narration = loader.load_file(NARRATION_PROMPT_PATHS[0])

    assert [variable.name for variable in thumbnail.variables] == [
        "title",
        "game",
        "topic",
        "angle",
        "hook",
        "platform",
        "visual_context",
    ]
    assert [variable.name for variable in visual.variables] == [
        "game",
        "scene_number",
        "scene_purpose",
        "script_beat",
        "visual_direction",
        "on_screen_text",
        "platform",
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
    assert [variable.name for variable in narration.variables] == [
        "title",
        "game",
        "script_text",
        "target_duration_seconds",
        "tone",
        "platform",
    ]


def test_new_media_prompt_contents_include_required_output_labels() -> None:
    """The new media prompt bodies should contain the required output labels."""

    prompts_root = _repo_prompts_dir()
    thumbnail_payload = json.loads((prompts_root / THUMBNAIL_PROMPT_PATHS[0]).read_text(encoding="utf-8"))
    visual_payload = json.loads((prompts_root / Path("storyboard/gaming_scene_visual_prompt.v1.json")).read_text(encoding="utf-8"))
    motion_payload = json.loads((prompts_root / Path("storyboard/gaming_scene_motion_prompt.v1.json")).read_text(encoding="utf-8"))
    narration_payload = json.loads((prompts_root / NARRATION_PROMPT_PATHS[0]).read_text(encoding="utf-8"))

    thumbnail_content = "\n".join(message["content"] for message in thumbnail_payload["messages"])
    visual_content = "\n".join(message["content"] for message in visual_payload["messages"])
    motion_content = "\n".join(message["content"] for message in motion_payload["messages"])
    narration_content = "\n".join(message["content"] for message in narration_payload["messages"])

    for label in ["CONCEPT:", "FOCAL_SUBJECT:", "BACKGROUND:", "COMPOSITION:", "EXPRESSION_OR_ACTION:", "ON_IMAGE_TEXT:", "STYLE_DIRECTION:", "AVOID:", "EVIDENCE_NOTE:"]:
        assert label in thumbnail_content
    for label in ["SCENE_NUMBER:", "SUBJECT:", "ENVIRONMENT:", "ACTION:", "COMPOSITION:", "MOOD:", "ON_SCREEN_TEXT:", "STYLE_DIRECTION:", "NEGATIVE_GUIDANCE:"]:
        assert label in visual_content
    for label in ["SCENE_NUMBER:", "PRIMARY_MOTION:", "SUBJECT_MOVEMENT:", "CAMERA_DIRECTION:", "TRANSITION_GUIDANCE:", "PACING:", "DURATION_SECONDS:", "AVOID:"]:
        assert label in motion_content
    for label in ["NARRATION_TEXT:", "TONE:", "PACE:", "EMPHASIS:", "PAUSE_GUIDANCE:", "PRONUNCIATION_NOTES:", "TARGET_DURATION_SECONDS:"]:
        assert label in narration_content


def test_thumbnail_prompt_safeguards_are_present() -> None:
    """The thumbnail concept prompt should include its expected safety instructions."""

    text = (_repo_prompts_dir() / THUMBNAIL_PROMPT_PATHS[0]).read_text(encoding="utf-8")

    assert "Avoid misleading visuals." in text
    assert "Do not imply events not supported by supplied content." in text
    assert "Avoid excessive text." in text
    assert "AVOID:" in text


def test_scene_visual_prompt_safeguards_are_present() -> None:
    """The scene visual prompt should preserve scene identity and remain provider-neutral."""

    text = (_repo_prompts_dir() / Path("storyboard/gaming_scene_visual_prompt.v1.json")).read_text(encoding="utf-8")

    assert "Preserve the supplied scene number." in text
    assert "Do not include resolution, sampler, seed, model ID, API arguments, or vendor syntax." in text
    assert "Separate visual content from stylistic direction." in text
    assert "NEGATIVE_GUIDANCE:" in text
    assert "Do not invent gameplay facts." in text


def test_scene_motion_prompt_safeguards_are_present() -> None:
    """The scene motion prompt should preserve timing and remain provider-neutral."""

    text = (_repo_prompts_dir() / Path("storyboard/gaming_scene_motion_prompt.v1.json")).read_text(encoding="utf-8")

    assert "Preserve scene number." in text
    assert "Treat DURATION_SECONDS as the target scene duration." in text
    assert "Prefer one primary motion idea." in text
    assert "No provider-specific camera commands." in text
    assert "PACING:" in text


def test_narration_prompt_safeguards_are_present() -> None:
    """The narration direction prompt should preserve meaning and avoid provider-specific voice behavior."""

    text = (_repo_prompts_dir() / NARRATION_PROMPT_PATHS[0]).read_text(encoding="utf-8")

    assert "Do not add facts." in text
    assert "Do not request imitation of a real person's voice." in text
    assert "Do not specify a vendor voice ID." in text
    assert "PRONUNCIATION_NOTES:" in text
    assert "TARGET_DURATION_SECONDS:" in text


def test_manifest_contains_exactly_thirteen_entries_with_expected_category_counts() -> None:
    """The manifest should include the research, script, storyboard, thumbnail, and narration prompt assets."""

    manifest = PromptManifestLoader(base_dir=_repo_prompts_dir()).load()

    assert len(manifest.entries) == 13
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.RESEARCH]) == 3
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.SCRIPT]) == 3
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.STORYBOARD]) == 5
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.THUMBNAIL]) == 1
    assert len([entry for entry in manifest.entries if entry.category is PromptAssetCategory.NARRATION]) == 1


def test_manifest_new_media_checksums_match_current_file_contents() -> None:
    """Manifest checksums for the new media prompt assets should match exact file bytes."""

    prompts_root = _repo_prompts_dir()
    manifest = PromptManifestLoader(base_dir=prompts_root).load()
    manifest_by_path = {entry.path: entry for entry in manifest.entries}

    for relative_path in NEW_MEDIA_PROMPT_PATHS:
        path_text = relative_path.as_posix()
        assert manifest_by_path[path_text].checksum == hashlib.sha256((prompts_root / relative_path).read_bytes()).hexdigest()


def test_removed_media_placeholder_gitkeeps_do_not_remain() -> None:
    """The thumbnail and narration prompt directories should no longer need .gitkeep placeholders."""

    prompts_root = _repo_prompts_dir()
    assert not (prompts_root / "thumbnail" / ".gitkeep").exists()
    assert not (prompts_root / "narration" / ".gitkeep").exists()


def test_new_media_prompt_assets_serialize_and_restore_predictably() -> None:
    """The new media prompt definitions should round-trip predictably."""

    loader = PromptLoader(base_dir=_repo_prompts_dir())

    for relative_path in NEW_MEDIA_PROMPT_PATHS:
        definition = loader.load_file(relative_path)
        restored = PromptDefinition.model_validate(definition.model_dump(mode="python"))
        assert restored == definition
