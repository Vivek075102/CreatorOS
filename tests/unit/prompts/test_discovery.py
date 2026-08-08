"""Unit tests for prompt asset discovery and manifest validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from creatoros.core import PromptLoadError, PromptManifestError
from creatoros.prompts import (
    PromptAssetCategory,
    PromptAssetDiscovery,
    PromptAssetManifest,
    PromptAssetManifestEntry,
    PromptStatus,
)


def write_prompt_asset(
    base_dir: Path,
    *,
    category: str = "research",
    nested_path: str = "gaming",
    name: str = "gaming_discover_trends",
    version: int = 1,
    status: str = "active",
) -> Path:
    """Write a valid prompt asset JSON file under a category directory."""

    relative_path = (
        Path(category) / nested_path / f"{name}.v{version}.json"
        if nested_path
        else Path(category) / f"{name}.v{version}.json"
    )
    target_path = base_dir / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "version": version,
        "status": status,
        "description": "Prompt description.",
        "format": "text",
        "messages": [
            {"role": "system", "content": "You are a prompt."},
            {"role": "user", "content": "Do something about {topic}."},
        ],
        "variables": [{"name": "topic", "variable_type": "string", "required": True}],
        "tags": ["example", category or "root"],
        "metadata": {},
    }
    target_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target_path


def build_entry(
    *,
    name: str = "gaming_discover_trends",
    version: int = 1,
    category: PromptAssetCategory = PromptAssetCategory.RESEARCH,
    path: str = "research/gaming/gaming_discover_trends.v1.json",
    status: PromptStatus = PromptStatus.ACTIVE,
    checksum: str = "a" * 64,
) -> PromptAssetManifestEntry:
    """Build a manifest entry for discovery validation tests."""

    return PromptAssetManifestEntry(
        name=name,
        version=version,
        category=category,
        path=path,
        status=status,
        description="Prompt description.",
        tags=["example"],
        checksum=checksum,
    )


def test_empty_category_structure_discovers_zero_assets(tmp_path: Path) -> None:
    """An empty prompt structure should discover zero prompt assets."""

    for category in PromptAssetCategory:
        (tmp_path / category.value).mkdir(parents=True, exist_ok=True)
        (tmp_path / category.value / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [],
                "metadata": {"description": "CreatorOS version-controlled prompt asset manifest."},
            }
        ),
        encoding="utf-8",
    )
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    assert discovery.discover() == ()


def test_manifest_json_is_ignored(tmp_path: Path) -> None:
    """The root manifest file should not be discovered as a prompt asset."""

    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [],
                "metadata": {"description": "CreatorOS version-controlled prompt asset manifest."},
            }
        ),
        encoding="utf-8",
    )
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    assert discovery.discover() == ()


def test_gitkeep_hidden_and_non_json_files_are_ignored(tmp_path: Path) -> None:
    """Discovery should ignore .gitkeep, hidden files, and non-JSON files."""

    category_dir = tmp_path / "research" / "gaming"
    category_dir.mkdir(parents=True)
    (category_dir / ".gitkeep").write_text("", encoding="utf-8")
    (category_dir / ".hidden.v1.json").write_text("{}", encoding="utf-8")
    (category_dir / "notes.txt").write_text("ignored", encoding="utf-8")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    assert discovery.discover() == ()


def test_valid_prompt_asset_is_discovered(tmp_path: Path) -> None:
    """A valid prompt asset should be discovered with its checksum."""

    asset_path = write_prompt_asset(tmp_path)
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    records = discovery.discover()

    assert len(records) == 1
    assert records[0].definition.name == "gaming_discover_trends"
    assert records[0].relative_path == "research/gaming/gaming_discover_trends.v1.json"
    assert records[0].checksum == hashlib.sha256(asset_path.read_bytes()).hexdigest()


def test_category_is_inferred_correctly(tmp_path: Path) -> None:
    """The prompt asset category should be inferred from the directory."""

    write_prompt_asset(tmp_path, category="script", nested_path="", name="youtube_shorts_script")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    records = discovery.discover()

    assert len(records) == 1
    assert records[0].category is PromptAssetCategory.SCRIPT


def test_filename_definition_name_mismatch_is_rejected(tmp_path: Path) -> None:
    """Discovery should reject filename and definition name mismatches."""

    path = write_prompt_asset(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["name"] = "other_name"
    path.write_text(json.dumps(payload), encoding="utf-8")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        discovery.discover()

    assert exc_info.value.code == "prompt_asset_identity_mismatch"


def test_filename_definition_version_mismatch_is_rejected(tmp_path: Path) -> None:
    """Discovery should reject filename and definition version mismatches."""

    path = write_prompt_asset(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        discovery.discover()

    assert exc_info.value.code == "prompt_asset_identity_mismatch"


def test_json_directly_under_root_is_rejected(tmp_path: Path) -> None:
    """Prompt JSON files under the root prompts directory should be rejected."""

    write_prompt_asset(tmp_path, category="", nested_path="", name="root_prompt")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    with pytest.raises(PromptLoadError) as exc_info:
        discovery.discover()

    assert exc_info.value.code == "prompt_asset_root_json_not_allowed"


def test_unknown_category_directories_are_ignored(tmp_path: Path) -> None:
    """Unknown category directories should be ignored consistently."""

    write_prompt_asset(tmp_path, category="unexpected", nested_path="", name="unexpected_prompt")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    assert discovery.discover() == ()


def test_discovery_order_is_predictable(tmp_path: Path) -> None:
    """Discovered assets should be returned in a stable sorted order."""

    write_prompt_asset(tmp_path, category="script", nested_path="", name="zeta_script")
    write_prompt_asset(tmp_path, category="research", nested_path="common", name="alpha_prompt")
    write_prompt_asset(tmp_path, category="research", nested_path="gaming", name="beta_prompt")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    records = discovery.discover()

    assert [(record.category.value, record.definition.name) for record in records] == [
        ("research", "alpha_prompt"),
        ("research", "beta_prompt"),
        ("script", "zeta_script"),
    ]


def test_build_manifest_creates_correct_entries(tmp_path: Path) -> None:
    """Manifest building should preserve discovered prompt asset identity fields."""

    write_prompt_asset(tmp_path, category="script", nested_path="", name="youtube_shorts_script", version=2)
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    manifest = discovery.build_manifest()

    assert manifest.schema_version == 1
    assert len(manifest.entries) == 1
    assert manifest.entries[0].path == "script/youtube_shorts_script.v2.json"


def test_validate_manifest_accepts_matching_assets(tmp_path: Path) -> None:
    """Manifest validation should pass when discovery matches exactly."""

    asset_path = write_prompt_asset(tmp_path)
    discovery = PromptAssetDiscovery(base_dir=tmp_path)
    manifest = PromptAssetManifest(
        entries=[
            build_entry(
                checksum=hashlib.sha256(asset_path.read_bytes()).hexdigest(),
            )
        ]
    )

    discovery.validate_manifest(manifest)


def test_validate_manifest_detects_missing_manifest_entry(tmp_path: Path) -> None:
    """Manifest validation should reject discovered assets missing from the manifest."""

    write_prompt_asset(tmp_path)
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    with pytest.raises(PromptManifestError) as exc_info:
        discovery.validate_manifest(PromptAssetManifest())

    assert exc_info.value.code == "prompt_manifest_mismatch"


def test_validate_manifest_detects_missing_asset_file(tmp_path: Path) -> None:
    """Manifest validation should reject manifest entries with no matching file."""

    discovery = PromptAssetDiscovery(base_dir=tmp_path)
    manifest = PromptAssetManifest(entries=[build_entry()])

    with pytest.raises(PromptManifestError) as exc_info:
        discovery.validate_manifest(manifest)

    assert exc_info.value.code == "prompt_manifest_mismatch"


def test_validate_manifest_detects_checksum_mismatch(tmp_path: Path) -> None:
    """Manifest validation should reject checksum mismatches."""

    write_prompt_asset(tmp_path)
    discovery = PromptAssetDiscovery(base_dir=tmp_path)
    manifest = PromptAssetManifest(entries=[build_entry(checksum="b" * 64)])

    with pytest.raises(PromptManifestError) as exc_info:
        discovery.validate_manifest(manifest)

    assert exc_info.value.code == "prompt_asset_checksum_mismatch"


def test_validate_manifest_detects_status_mismatch(tmp_path: Path) -> None:
    """Manifest validation should reject identity mismatches such as status drift."""

    asset_path = write_prompt_asset(tmp_path, status="active")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)
    manifest = PromptAssetManifest(
        entries=[
            build_entry(
                status=PromptStatus.DRAFT,
                checksum=hashlib.sha256(asset_path.read_bytes()).hexdigest(),
            )
        ]
    )

    with pytest.raises(PromptManifestError) as exc_info:
        discovery.validate_manifest(manifest)

    assert exc_info.value.code == "prompt_asset_identity_mismatch"


def test_discovery_does_not_modify_files(tmp_path: Path) -> None:
    """Discovery should not mutate prompt asset file contents."""

    asset_path = write_prompt_asset(tmp_path)
    original_contents = asset_path.read_text(encoding="utf-8")
    discovery = PromptAssetDiscovery(base_dir=tmp_path)

    discovery.discover()

    assert asset_path.read_text(encoding="utf-8") == original_contents


def test_required_category_directories_exist() -> None:
    """The repository should contain the required prompt category directories."""

    repo_root = Path(__file__).resolve().parents[3]
    prompts_root = repo_root / "prompts"

    for category in PromptAssetCategory:
        assert (prompts_root / category.value).is_dir()


def test_manifest_json_exists_and_is_valid() -> None:
    """The repository manifest should exist and match the expected initial shape."""

    repo_root = Path(__file__).resolve().parents[3]
    manifest_path = repo_root / "prompts" / "manifest.json"
    manifest = PromptAssetManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))

    assert manifest.schema_version == 1
    assert len(manifest.entries) == 17
    assert [entry.path for entry in manifest.list_entries()] == [
        "narration/gaming_narration_direction.v1.json",
        "research/gaming/gaming_discover_trends.v1.json",
        "research/gaming/gaming_evaluate_opportunity.v1.json",
        "research/gaming/gaming_expand_keywords.v1.json",
        "review/gaming_evidence_consistency_review.v1.json",
        "review/gaming_publication_readiness_review.v1.json",
        "review/gaming_script_quality_review.v1.json",
        "review/gaming_storyboard_quality_review.v1.json",
        "script/gaming_cta.v1.json",
        "script/gaming_hook.v1.json",
        "script/youtube_shorts_script.v1.json",
        "storyboard/gaming_scene_motion_prompt.v1.json",
        "storyboard/gaming_scene_visual_prompt.v1.json",
        "storyboard/storyboard_scene_breakdown.v1.json",
        "storyboard/storyboard_timing_review.v1.json",
        "storyboard/storyboard_visual_direction.v1.json",
        "thumbnail/gaming_thumbnail_concept.v1.json",
    ]


def test_empty_directories_contain_gitkeep_where_needed() -> None:
    """Empty repository prompt directories should include .gitkeep files."""

    repo_root = Path(__file__).resolve().parents[3]
    prompts_root = repo_root / "prompts"
    expected_gitkeep_paths = {
        "research/.gitkeep",
        "research/common/.gitkeep",
        "metadata/.gitkeep",
        "publishing/.gitkeep",
    }

    actual_paths = {
        path.relative_to(prompts_root).as_posix() for path in prompts_root.rglob(".gitkeep")
    }

    assert expected_gitkeep_paths == actual_paths


def test_repository_contains_exactly_seventeen_prompt_definition_json_files() -> None:
    """The repository should contain the research, review, script, storyboard, thumbnail, and narration prompt assets."""

    repo_root = Path(__file__).resolve().parents[3]
    prompts_root = repo_root / "prompts"
    json_paths = sorted(
        path.relative_to(prompts_root).as_posix()
        for path in prompts_root.rglob("*.json")
        if path.name != "manifest.json"
    )

    assert json_paths == [
        "narration/gaming_narration_direction.v1.json",
        "research/gaming/gaming_discover_trends.v1.json",
        "research/gaming/gaming_evaluate_opportunity.v1.json",
        "research/gaming/gaming_expand_keywords.v1.json",
        "review/gaming_evidence_consistency_review.v1.json",
        "review/gaming_publication_readiness_review.v1.json",
        "review/gaming_script_quality_review.v1.json",
        "review/gaming_storyboard_quality_review.v1.json",
        "script/gaming_cta.v1.json",
        "script/gaming_hook.v1.json",
        "script/youtube_shorts_script.v1.json",
        "storyboard/gaming_scene_motion_prompt.v1.json",
        "storyboard/gaming_scene_visual_prompt.v1.json",
        "storyboard/storyboard_scene_breakdown.v1.json",
        "storyboard/storyboard_timing_review.v1.json",
        "storyboard/storyboard_visual_direction.v1.json",
        "thumbnail/gaming_thumbnail_concept.v1.json",
    ]
