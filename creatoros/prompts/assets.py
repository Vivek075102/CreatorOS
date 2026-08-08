"""Prompt asset categories and manifest contracts for CreatorOS."""

from __future__ import annotations

import re
from copy import deepcopy
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import Field, field_validator, model_validator

from creatoros.core import PromptNotFoundError
from creatoros.domain import CreatorOSModel
from creatoros.prompts.enums import PromptStatus
from creatoros.prompts.naming import parse_prompt_asset_filename

_ASSET_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PromptAssetCategory(StrEnum):
    """Top-level prompt asset categories supported by CreatorOS."""

    RESEARCH = "research"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    NARRATION = "narration"
    THUMBNAIL = "thumbnail"
    METADATA = "metadata"
    REVIEW = "review"
    PUBLISHING = "publishing"


class PromptAssetManifestEntry(CreatorOSModel):
    """One manifest entry describing a versioned prompt asset on disk."""

    name: str
    version: int
    category: PromptAssetCategory
    path: str
    status: PromptStatus
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    checksum: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require stable lowercase snake_case prompt asset names."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("name must not be blank")
        if not _ASSET_NAME_PATTERN.fullmatch(normalized_value):
            raise ValueError("name must use lowercase snake_case")
        return normalized_value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        """Require positive integer prompt asset versions."""

        if value < 1:
            raise ValueError("version must be greater than or equal to 1")
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Validate relative forward-slash manifest paths."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("path must not be blank")
        if "\\" in normalized_value:
            raise ValueError("path must use forward slashes")
        if normalized_value.startswith(("/", "./")) or ":" in normalized_value:
            raise ValueError("path must be relative")

        path_parts = PurePosixPath(normalized_value).parts
        if not path_parts:
            raise ValueError("path must not be blank")
        if ".." in path_parts:
            raise ValueError("path must not contain parent traversal")
        return normalized_value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        """Trim and reject blank descriptions when supplied."""

        if value is None:
            return None
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("description must not be blank")
        return normalized_value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        """Trim tag values and require normalized uniqueness."""

        normalized_tags = []
        normalized_keys: set[str] = set()
        for tag in value:
            normalized_tag = tag.strip()
            if not normalized_tag:
                raise ValueError("tags must not contain blank values")
            normalized_key = normalized_tag.casefold()
            if normalized_key in normalized_keys:
                raise ValueError("tags must be unique after case normalization")
            normalized_keys.add(normalized_key)
            normalized_tags.append(normalized_tag)
        return normalized_tags

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, value: str | None) -> str | None:
        """Validate optional lowercase SHA-256 checksums."""

        if value is None:
            return None
        normalized_value = value.strip()
        if not _SHA256_PATTERN.fullmatch(normalized_value):
            raise ValueError("checksum must be a lowercase 64-character SHA-256 hexadecimal string")
        return normalized_value

    @model_validator(mode="after")
    def validate_identity(self) -> PromptAssetManifestEntry:
        """Ensure the manifest path matches the declared entry identity."""

        parsed_path = PurePosixPath(self.path)
        path_parts = parsed_path.parts
        if len(path_parts) < 2:
            raise ValueError("path must include a category directory and filename")

        category_from_path = path_parts[0]
        if category_from_path != self.category.value:
            raise ValueError("category must match the first path directory")

        parsed_filename = parse_prompt_asset_filename(parsed_path.name)
        if parsed_filename.name != self.name:
            raise ValueError("filename asset name must match name")
        if parsed_filename.version != self.version:
            raise ValueError("filename version must match version")

        return self

    @property
    def qualified_name(self) -> str:
        """Return the stable qualified manifest entry name."""

        return f"{self.name}:v{self.version}"


class PromptAssetManifest(CreatorOSModel):
    """Versioned prompt asset manifest."""

    schema_version: int = 1
    entries: list[PromptAssetManifestEntry] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        """Require the currently supported schema version."""

        if value != 1:
            raise ValueError("schema_version must be 1")
        return value

    @model_validator(mode="after")
    def validate_entries(self) -> PromptAssetManifest:
        """Reject duplicate identities and duplicate normalized paths."""

        identity_keys: set[tuple[str, int]] = set()
        normalized_paths: set[str] = set()
        for entry in self.entries:
            identity_key = (entry.name.casefold(), entry.version)
            if identity_key in identity_keys:
                raise ValueError("duplicate prompt asset name/version combinations are not allowed")
            identity_keys.add(identity_key)

            normalized_path = entry.path.casefold()
            if normalized_path in normalized_paths:
                raise ValueError("duplicate prompt asset paths are not allowed")
            normalized_paths.add(normalized_path)
        return self

    def get_entry(self, name: str, version: int) -> PromptAssetManifestEntry:
        """Return a deep copy of one manifest entry by identity."""

        for entry in self.entries:
            if entry.name.casefold() == name.strip().casefold() and entry.version == version:
                return entry.model_copy(deep=True)
        raise PromptNotFoundError(name, version)

    def list_entries(
        self,
        *,
        category: PromptAssetCategory | None = None,
        status: PromptStatus | None = None,
    ) -> tuple[PromptAssetManifestEntry, ...]:
        """Return sorted immutable deep copies of matching manifest entries."""

        filtered_entries = [
            entry.model_copy(deep=True)
            for entry in self.entries
            if (category is None or entry.category is category) and (status is None or entry.status is status)
        ]
        filtered_entries.sort(key=lambda entry: (entry.category.value, entry.name, entry.version))
        return tuple(filtered_entries)

    def to_serializable_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-serializable representation of the manifest."""

        return {
            "schema_version": self.schema_version,
            "entries": [
                {
                    "name": entry.name,
                    "version": entry.version,
                    "category": entry.category.value,
                    "path": entry.path,
                    "status": entry.status.value,
                    "description": entry.description,
                    "tags": list(entry.tags),
                    "checksum": entry.checksum,
                    "metadata": deepcopy(entry.metadata),
                }
                for entry in self.list_entries()
            ],
            "metadata": deepcopy(self.metadata),
        }


__all__ = [
    "PromptAssetCategory",
    "PromptAssetManifest",
    "PromptAssetManifestEntry",
]
