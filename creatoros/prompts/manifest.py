"""Loading and writing for the CreatorOS prompt asset manifest."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from creatoros.config import get_settings
from creatoros.core import CreatorOSValidationError, PromptLoadError
from creatoros.prompts.assets import PromptAssetManifest


class PromptManifestLoader:
    """Load and write the prompt asset manifest within the configured prompts directory."""

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
    ) -> None:
        configured_base_dir = get_settings().prompts_dir if base_dir is None else Path(base_dir)
        self.base_dir = configured_base_dir.resolve()

    def load(self, path: Path | None = None) -> PromptAssetManifest:
        """Load and validate a prompt asset manifest JSON file."""

        resolved_path = self._resolve_path(self.base_dir / "manifest.json" if path is None else path)
        if resolved_path.suffix.lower() != ".json":
            raise PromptLoadError(
                "only JSON manifest files are supported",
                code="prompt_manifest_invalid_file_type",
                details={"path": self._safe_path_display(resolved_path)},
            )
        if not resolved_path.exists() or not resolved_path.is_file():
            raise PromptLoadError(
                "prompt manifest file was not found",
                code="prompt_manifest_file_not_found",
                details={"path": self._safe_path_display(resolved_path)},
            )

        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise PromptLoadError(
                "prompt manifest file could not be read",
                code="prompt_manifest_read_failed",
                details={"path": self._safe_path_display(resolved_path)},
            ) from error
        except json.JSONDecodeError as error:
            raise PromptLoadError(
                "prompt manifest file contains invalid JSON",
                code="prompt_manifest_invalid_json",
                details={"path": self._safe_path_display(resolved_path)},
            ) from error

        try:
            return PromptAssetManifest.model_validate(payload)
        except ValidationError as error:
            raise CreatorOSValidationError(
                "prompt manifest is invalid",
                code="prompt_manifest_invalid",
                details={"path": self._safe_path_display(resolved_path)},
            ) from error

    def write(self, manifest: PromptAssetManifest, path: Path | None = None) -> Path:
        """Write a manifest deterministically and atomically inside the prompt base directory."""

        resolved_path = self._resolve_path(self.base_dir / "manifest.json" if path is None else path)
        if resolved_path.suffix.lower() != ".json":
            raise PromptLoadError(
                "only JSON manifest files are supported",
                code="prompt_manifest_invalid_file_type",
                details={"path": self._safe_path_display(resolved_path)},
            )

        payload = manifest.model_copy(deep=True).to_serializable_dict()
        serialized = json.dumps(payload, indent=2) + "\n"

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=resolved_path.parent,
                prefix=f"{resolved_path.name}.",
                suffix=".tmp",
                delete=False,
                newline="\n",
            ) as handle:
                handle.write(serialized)
                temp_path = Path(handle.name)

            os.replace(temp_path, resolved_path)
        except OSError as error:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise PromptLoadError(
                "prompt manifest file could not be written",
                code="prompt_manifest_write_failed",
                details={"path": self._safe_path_display(resolved_path)},
            ) from error

        return resolved_path

    def _resolve_path(self, path: Path) -> Path:
        """Resolve a manifest path safely inside the configured base directory."""

        candidate = Path(path)
        resolved_path = (self.base_dir / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if not resolved_path.is_relative_to(self.base_dir):
            raise PromptLoadError(
                "prompt manifest path must stay within the configured prompt base directory",
                code="prompt_manifest_outside_base_dir",
                details={"path": str(candidate)},
            )
        return resolved_path

    def _safe_path_display(self, path: Path) -> str:
        """Return a safe display path relative to base_dir when possible."""

        try:
            return path.resolve().relative_to(self.base_dir).as_posix()
        except ValueError:
            return path.name


__all__ = ["PromptManifestLoader"]
