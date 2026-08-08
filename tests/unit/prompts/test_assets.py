"""Unit tests for prompt asset manifest models."""

from __future__ import annotations

import pytest

from creatoros.core import PromptNotFoundError
from creatoros.prompts import (
    PromptAssetCategory,
    PromptAssetManifest,
    PromptAssetManifestEntry,
    PromptStatus,
)


def build_entry(
    *,
    name: str = "gaming_discover_trends",
    version: int = 1,
    category: PromptAssetCategory = PromptAssetCategory.RESEARCH,
    path: str = "research/gaming/gaming_discover_trends.v1.json",
    status: PromptStatus = PromptStatus.ACTIVE,
    checksum: str | None = "a" * 64,
) -> PromptAssetManifestEntry:
    """Build a valid manifest entry for tests."""

    return PromptAssetManifestEntry(
        name=name,
        version=version,
        category=category,
        path=path,
        status=status,
        description="Discover trend opportunities.",
        tags=["gaming", "research"],
        checksum=checksum,
        metadata={"team": "creatoros"},
    )


def test_valid_entries_are_accepted() -> None:
    """A valid manifest entry should be accepted."""

    entry = build_entry()

    assert entry.qualified_name == "gaming_discover_trends:v1"


@pytest.mark.parametrize("name", ["GamingDiscoverTrends", "gaming-discover-trends", "gaming discover trends"])
def test_name_must_be_lowercase_snake_case(name: str) -> None:
    """Entry names should require lowercase snake_case."""

    with pytest.raises(ValueError):
        build_entry(name=name)


def test_paths_must_be_relative() -> None:
    """Entry paths must be relative to the prompt root."""

    with pytest.raises(ValueError):
        build_entry(path="/research/gaming/gaming_discover_trends.v1.json")


def test_backslashes_are_rejected() -> None:
    """Entry paths should require forward slashes."""

    with pytest.raises(ValueError):
        build_entry(path=r"research\gaming\gaming_discover_trends.v1.json")


def test_parent_traversal_is_rejected() -> None:
    """Entry paths must not allow parent traversal."""

    with pytest.raises(ValueError):
        build_entry(path="research/../gaming_discover_trends.v1.json")


def test_category_must_match_path() -> None:
    """The first directory in the path should match the declared category."""

    with pytest.raises(ValueError):
        build_entry(category=PromptAssetCategory.SCRIPT)


def test_filename_name_must_match_entry_name() -> None:
    """The filename prompt name should match the manifest entry name."""

    with pytest.raises(ValueError):
        build_entry(path="research/gaming/other_name.v1.json")


def test_filename_version_must_match_entry_version() -> None:
    """The filename version should match the manifest entry version."""

    with pytest.raises(ValueError):
        build_entry(version=2)


def test_invalid_checksum_is_rejected() -> None:
    """Checksums should require lowercase 64-character SHA-256 values."""

    with pytest.raises(ValueError):
        build_entry(checksum="invalid")


def test_duplicate_entry_identity_is_rejected() -> None:
    """Manifest entries must not duplicate the same name and version."""

    with pytest.raises(ValueError):
        PromptAssetManifest(entries=[build_entry(), build_entry()])


def test_duplicate_paths_are_rejected() -> None:
    """Manifest entries must not duplicate the same normalized path."""

    with pytest.raises(ValueError):
        PromptAssetManifest(
            entries=[
                build_entry(),
                build_entry(name="gaming_discover_trends_v2", version=2, path="research/gaming/gaming_discover_trends.v1.json"),
            ]
        )


def test_get_entry_returns_a_copy() -> None:
    """Fetching a manifest entry should return a deep copy."""

    manifest = PromptAssetManifest(entries=[build_entry()])

    returned = manifest.get_entry("gaming_discover_trends", 1)
    returned.tags.append("changed")

    assert manifest.entries[0].tags == ["gaming", "research"]


def test_missing_entry_raises_prompt_not_found() -> None:
    """Missing manifest entries should raise PromptNotFoundError."""

    manifest = PromptAssetManifest()

    with pytest.raises(PromptNotFoundError):
        manifest.get_entry("missing_prompt", 1)


def test_list_entries_filters_and_sorts() -> None:
    """Manifest list_entries should filter and sort predictably."""

    manifest = PromptAssetManifest(
        entries=[
            build_entry(name="zeta_prompt", path="research/gaming/zeta_prompt.v1.json"),
            build_entry(
                name="alpha_script",
                category=PromptAssetCategory.SCRIPT,
                path="script/alpha_script.v1.json",
                status=PromptStatus.DRAFT,
            ),
            build_entry(name="alpha_prompt", path="research/common/alpha_prompt.v1.json"),
        ]
    )

    filtered = manifest.list_entries(category=PromptAssetCategory.RESEARCH, status=PromptStatus.ACTIVE)

    assert [(entry.category.value, entry.name, entry.version) for entry in filtered] == [
        ("research", "alpha_prompt", 1),
        ("research", "zeta_prompt", 1),
    ]


def test_mutable_defaults_are_isolated() -> None:
    """Manifest metadata and tags defaults should not be shared."""

    first = PromptAssetManifestEntry(
        name="gaming_discover_trends",
        version=1,
        category=PromptAssetCategory.RESEARCH,
        path="research/gaming/gaming_discover_trends.v1.json",
        status=PromptStatus.ACTIVE,
    )
    second = PromptAssetManifestEntry(
        name="youtube_shorts_script",
        version=1,
        category=PromptAssetCategory.SCRIPT,
        path="script/youtube_shorts_script.v1.json",
        status=PromptStatus.DRAFT,
    )
    first.tags.append("tagged")
    first.metadata["owner"] = "one"

    assert second.tags == []
    assert second.metadata == {}


def test_manifest_serializes_and_restores() -> None:
    """The manifest should serialize and restore predictably."""

    manifest = PromptAssetManifest(entries=[build_entry()])

    restored = PromptAssetManifest.model_validate(manifest.model_dump(mode="python"))

    assert restored == manifest
