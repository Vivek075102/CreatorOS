"""Unit tests for prompt manifest loading and writing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from creatoros.core import CreatorOSValidationError, PromptLoadError
from creatoros.prompts import (
    PromptAssetCategory,
    PromptAssetManifest,
    PromptAssetManifestEntry,
    PromptManifestLoader,
    PromptStatus,
)


def build_manifest_with_entry() -> PromptAssetManifest:
    """Build a manifest with entries out of order for deterministic write checks."""

    return PromptAssetManifest(
        entries=[
            PromptAssetManifestEntry(
                name="youtube_shorts_script",
                version=2,
                category=PromptAssetCategory.SCRIPT,
                path="script/youtube_shorts_script.v2.json",
                status=PromptStatus.DRAFT,
                description="Script prompt.",
                tags=["script"],
                checksum="b" * 64,
            ),
            PromptAssetManifestEntry(
                name="gaming_discover_trends",
                version=1,
                category=PromptAssetCategory.RESEARCH,
                path="research/gaming/gaming_discover_trends.v1.json",
                status=PromptStatus.ACTIVE,
                description="Research prompt.",
                tags=["research"],
                checksum="a" * 64,
            ),
        ],
        metadata={"description": "CreatorOS version-controlled prompt asset manifest."},
    )


def test_initial_repository_manifest_loads() -> None:
    """The repository manifest should load successfully."""

    repo_root = Path(__file__).resolve().parents[3]
    loader = PromptManifestLoader(base_dir=repo_root / "prompts")

    manifest = loader.load()

    assert manifest.schema_version == 1
    assert [entry.name for entry in manifest.list_entries()] == [
        "gaming_narration_direction",
        "gaming_discover_trends",
        "gaming_evaluate_opportunity",
        "gaming_expand_keywords",
        "gaming_evidence_consistency_review",
        "gaming_publication_readiness_review",
        "gaming_script_quality_review",
        "gaming_storyboard_quality_review",
        "gaming_cta",
        "gaming_hook",
        "youtube_shorts_script",
        "gaming_scene_motion_prompt",
        "gaming_scene_visual_prompt",
        "storyboard_scene_breakdown",
        "storyboard_timing_review",
        "storyboard_visual_direction",
        "gaming_thumbnail_concept",
    ]


def test_missing_manifest_raises_prompt_load_error(tmp_path: Path) -> None:
    """Missing manifest files should raise PromptLoadError."""

    loader = PromptManifestLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load()

    assert exc_info.value.code == "prompt_manifest_file_not_found"


def test_invalid_json_raises_prompt_load_error(tmp_path: Path) -> None:
    """Invalid manifest JSON should raise PromptLoadError."""

    (tmp_path / "manifest.json").write_text("{invalid", encoding="utf-8")
    loader = PromptManifestLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load()

    assert exc_info.value.code == "prompt_manifest_invalid_json"


def test_invalid_manifest_schema_fails_safely(tmp_path: Path) -> None:
    """Invalid manifest content should fail without exposing file contents."""

    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": 2, "entries": [], "metadata": {"description": "SECRET"}}),
        encoding="utf-8",
    )
    loader = PromptManifestLoader(base_dir=tmp_path)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        loader.load()

    assert exc_info.value.code == "prompt_manifest_invalid"
    assert "SECRET" not in str(exc_info.value)


def test_paths_outside_base_dir_are_rejected(tmp_path: Path) -> None:
    """Manifest loader paths should stay within base_dir."""

    outside_path = tmp_path.parent / "manifest.json"
    loader = PromptManifestLoader(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        loader.load(outside_path)

    assert exc_info.value.code == "prompt_manifest_outside_base_dir"


def test_write_produces_deterministic_json(tmp_path: Path) -> None:
    """Manifest writes should sort entries deterministically."""

    loader = PromptManifestLoader(base_dir=tmp_path)
    manifest = build_manifest_with_entry()

    target_path = loader.write(manifest)
    contents = target_path.read_text(encoding="utf-8")

    assert '"schema_version": 1' in contents
    assert contents.index('"gaming_discover_trends"') < contents.index('"youtube_shorts_script"')


def test_write_adds_trailing_newline(tmp_path: Path) -> None:
    """Manifest writes should end with a trailing newline."""

    loader = PromptManifestLoader(base_dir=tmp_path)

    target_path = loader.write(PromptAssetManifest(metadata={"description": "CreatorOS version-controlled prompt asset manifest."}))

    assert target_path.read_text(encoding="utf-8").endswith("\n")


def test_write_is_atomic_at_public_behavior_level(tmp_path: Path) -> None:
    """Manifest write should not leave temporary sibling files behind."""

    loader = PromptManifestLoader(base_dir=tmp_path)
    target_path = loader.write(build_manifest_with_entry())

    sibling_names = {path.name for path in target_path.parent.iterdir()}

    assert sibling_names == {"manifest.json"}


def test_write_does_not_mutate_supplied_manifest(tmp_path: Path) -> None:
    """Writing a manifest should not mutate the caller's object."""

    loader = PromptManifestLoader(base_dir=tmp_path)
    manifest = build_manifest_with_entry()
    original_dump = manifest.model_dump(mode="python")

    loader.write(manifest)

    assert manifest.model_dump(mode="python") == original_dump


def test_load_write_round_trip_succeeds(tmp_path: Path) -> None:
    """Writing and then loading a manifest should preserve its content."""

    loader = PromptManifestLoader(base_dir=tmp_path)
    manifest = build_manifest_with_entry()
    loader.write(manifest)

    loaded = loader.load()

    assert loaded == PromptAssetManifest.model_validate(manifest.to_serializable_dict())
