"""Prompt asset discovery and manifest validation for CreatorOS."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import field_validator

from creatoros.config import get_settings
from creatoros.core import CreatorOSValidationError, PromptLoadError, PromptManifestError
from creatoros.domain import CreatorOSModel
from creatoros.prompts.assets import (
    PromptAssetCategory,
    PromptAssetManifest,
    PromptAssetManifestEntry,
)
from creatoros.prompts.loader import PromptLoader
from creatoros.prompts.models import PromptDefinition
from creatoros.prompts.naming import parse_prompt_asset_filename


class PromptAssetRecord(CreatorOSModel):
    """Discovered prompt asset information derived from disk."""

    definition: PromptDefinition
    category: PromptAssetCategory
    relative_path: str
    checksum: str

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        """Require forward-slash relative discovery paths."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("relative_path must not be blank")
        if "\\" in normalized_value or normalized_value.startswith("/") or ".." in normalized_value.split("/"):
            raise ValueError("relative_path must be a relative forward-slash path")
        return normalized_value

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        """Require lowercase SHA-256 checksums."""

        normalized_value = value.strip()
        if len(normalized_value) != 64 or any(character not in "0123456789abcdef" for character in normalized_value):
            raise ValueError("checksum must be a lowercase 64-character SHA-256 hexadecimal string")
        return normalized_value


class PromptAssetDiscovery:
    """Discover prompt assets under the configured prompt directory."""

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
    ) -> None:
        configured_base_dir = get_settings().prompts_dir if base_dir is None else Path(base_dir)
        self.base_dir = configured_base_dir.resolve()
        self.loader = PromptLoader(base_dir=self.base_dir)

    def discover(
        self,
        *,
        recursive: bool = True,
    ) -> tuple[PromptAssetRecord, ...]:
        """Discover and validate prompt assets under known category directories."""

        self._validate_root_files()

        records: list[PromptAssetRecord] = []
        for category in PromptAssetCategory:
            category_directory = self.base_dir / category.value
            if not category_directory.exists():
                continue
            if not category_directory.is_dir():
                raise PromptLoadError(
                    "prompt category path is not a directory",
                    code="prompt_asset_invalid_category_directory",
                    details={"path": category.value},
                )

            pattern = "**/*" if recursive else "*"
            for candidate in sorted(category_directory.glob(pattern), key=lambda path: path.as_posix()):
                if not candidate.is_file() or self._should_ignore_file(candidate):
                    continue
                if candidate.suffix.lower() != ".json":
                    continue

                relative_path = candidate.relative_to(self.base_dir).as_posix()
                try:
                    parsed_filename = parse_prompt_asset_filename(candidate.name)
                    definition = self.loader.load_file(candidate)
                except PromptLoadError as error:
                    raise PromptLoadError(
                        "prompt asset discovery failed",
                        code="prompt_asset_discovery_failed",
                        details={"path": relative_path},
                    ) from error
                except (CreatorOSValidationError, OSError) as error:
                    raise PromptLoadError(
                        "prompt asset discovery failed",
                        code="prompt_asset_discovery_failed",
                        details={"path": relative_path},
                    ) from error

                if definition.name != parsed_filename.name:
                    raise PromptLoadError(
                        "prompt asset filename and definition name do not match",
                        code="prompt_asset_identity_mismatch",
                        details={"path": relative_path},
                    )
                if definition.version != parsed_filename.version:
                    raise PromptLoadError(
                        "prompt asset filename and definition version do not match",
                        code="prompt_asset_identity_mismatch",
                        details={"path": relative_path},
                    )

                records.append(
                    PromptAssetRecord(
                        definition=definition.model_copy(deep=True),
                        category=category,
                        relative_path=relative_path,
                        checksum=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    )
                )

        records.sort(
            key=lambda record: (
                record.category.value,
                record.definition.name,
                record.definition.version,
                record.relative_path,
            )
        )
        return tuple(record.model_copy(deep=True) for record in records)

    def build_manifest(
        self,
        *,
        recursive: bool = True,
    ) -> PromptAssetManifest:
        """Build a manifest from currently discovered prompt assets."""

        entries = [
            PromptAssetManifestEntry(
                name=record.definition.name,
                version=record.definition.version,
                category=record.category,
                path=record.relative_path,
                status=record.definition.status,
                description=record.definition.description,
                tags=list(record.definition.tags),
                checksum=record.checksum,
                metadata=dict(record.definition.metadata),
            )
            for record in self.discover(recursive=recursive)
        ]
        return PromptAssetManifest(
            schema_version=1,
            entries=entries,
            metadata={"description": "CreatorOS version-controlled prompt asset manifest."},
        )

    def validate_manifest(
        self,
        manifest: PromptAssetManifest,
        *,
        recursive: bool = True,
    ) -> None:
        """Ensure a manifest matches the currently discovered prompt assets."""

        discovered_records = self.discover(recursive=recursive)
        manifest_entries = manifest.list_entries()

        discovered_by_identity = {
            (record.definition.name.casefold(), record.definition.version): record for record in discovered_records
        }
        manifest_by_identity = {(entry.name.casefold(), entry.version): entry for entry in manifest_entries}

        for identity, record in discovered_by_identity.items():
            entry = manifest_by_identity.get(identity)
            if entry is None:
                raise PromptManifestError(
                    "discovered prompt asset is missing from the manifest",
                    code="prompt_manifest_mismatch",
                    details={"path": record.relative_path},
                )
            self._validate_identity_match(entry, record)

        for identity, entry in manifest_by_identity.items():
            discovered_record = discovered_by_identity.get(identity)
            if discovered_record is None:
                raise PromptManifestError(
                    "manifest entry does not have a matching prompt asset file",
                    code="prompt_manifest_mismatch",
                    details={"path": entry.path},
                )
            self._validate_identity_match(entry, discovered_record)

    def _validate_identity_match(
        self,
        entry: PromptAssetManifestEntry,
        record: PromptAssetRecord,
    ) -> None:
        """Validate manifest and discovered asset identity fields."""

        if (
            entry.category is not record.category
            or entry.path != record.relative_path
            or entry.status is not record.definition.status
        ):
            raise PromptManifestError(
                "manifest entry does not match the discovered prompt asset identity",
                code="prompt_asset_identity_mismatch",
                details={"path": record.relative_path},
            )
        if entry.checksum != record.checksum:
            raise PromptManifestError(
                "manifest entry checksum does not match the discovered prompt asset",
                code="prompt_asset_checksum_mismatch",
                details={"path": record.relative_path},
            )

    def _validate_root_files(self) -> None:
        """Reject unsupported JSON prompt files directly under the prompt root."""

        if not self.base_dir.exists():
            return

        for candidate in self.base_dir.iterdir():
            if not candidate.is_file():
                continue
            if self._should_ignore_file(candidate):
                continue
            if candidate.name == "manifest.json":
                continue
            if candidate.suffix.lower() == ".json":
                raise PromptLoadError(
                    "prompt JSON files must live under a known category directory",
                    code="prompt_asset_root_json_not_allowed",
                    details={"path": candidate.relative_to(self.base_dir).as_posix()},
                )

    def _should_ignore_file(self, path: Path) -> bool:
        """Return whether a filesystem entry should be ignored during discovery."""

        return path.name == ".gitkeep" or any(part.startswith(".") for part in path.relative_to(self.base_dir).parts)


__all__ = [
    "PromptAssetDiscovery",
    "PromptAssetRecord",
]
