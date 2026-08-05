"""Filesystem loading for validated provider-independent CreatorOS prompt assets."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from creatoros.config import get_settings
from creatoros.core import CreatorOSValidationError, PromptLoadError
from creatoros.prompts.models import PromptDefinition
from creatoros.prompts.registry import PromptRegistry


class PromptLoader:
    """Load JSON prompt definitions from the configured prompts directory."""

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
    ) -> None:
        configured_base_dir = get_settings().prompts_dir if base_dir is None else Path(base_dir)
        self.base_dir = configured_base_dir.resolve()

    def load_file(self, path: Path) -> PromptDefinition:
        """Load one JSON prompt definition file from the prompt assets directory."""

        resolved_path = self._resolve_path(path)
        if resolved_path.suffix.lower() != ".json":
            raise PromptLoadError(
                "only JSON prompt definition files are supported",
                code="prompt_load_invalid_file_type",
                details={"path": self._safe_path_display(resolved_path)},
            )
        if not resolved_path.exists() or not resolved_path.is_file():
            raise PromptLoadError(
                "prompt definition file was not found",
                code="prompt_load_file_not_found",
                details={"path": self._safe_path_display(resolved_path)},
            )

        try:
            raw_contents = resolved_path.read_text(encoding="utf-8")
        except OSError as error:
            raise PromptLoadError(
                "prompt definition file could not be read",
                code="prompt_load_file_read_failed",
                details={"path": self._safe_path_display(resolved_path)},
            ) from error

        try:
            payload = json.loads(raw_contents)
        except json.JSONDecodeError as error:
            raise PromptLoadError(
                "prompt definition file contains invalid JSON",
                code="prompt_load_invalid_json",
                details={"path": self._safe_path_display(resolved_path)},
            ) from error

        try:
            return PromptDefinition.model_validate(payload)
        except ValidationError as error:
            raise CreatorOSValidationError(
                "prompt definition is invalid",
                code="prompt_definition_invalid",
                details={"path": self._safe_path_display(resolved_path)},
            ) from error

    def load_directory(
        self,
        path: Path | None = None,
        *,
        recursive: bool = True,
    ) -> tuple[PromptDefinition, ...]:
        """Load all JSON prompt definition files from a directory."""

        resolved_directory = self._resolve_path(self.base_dir if path is None else path)
        if not resolved_directory.exists():
            return ()
        if not resolved_directory.is_dir():
            raise PromptLoadError(
                "prompt directory path is not a directory",
                code="prompt_load_invalid_directory",
                details={"path": self._safe_path_display(resolved_directory)},
            )

        pattern = "**/*.json" if recursive else "*.json"
        file_paths = sorted(
            (candidate for candidate in resolved_directory.glob(pattern) if candidate.is_file()),
            key=lambda candidate: self._safe_path_display(candidate),
        )

        loaded_definitions: list[PromptDefinition] = []
        for file_path in file_paths:
            try:
                loaded_definitions.append(self.load_file(file_path))
            except CreatorOSValidationError as error:
                raise PromptLoadError(
                    "prompt directory loading failed because one definition is invalid",
                    code="prompt_load_directory_failed",
                    details={"path": self._safe_path_display(file_path)},
                ) from error
            except PromptLoadError as error:
                raise PromptLoadError(
                    "prompt directory loading failed",
                    code="prompt_load_directory_failed",
                    details={"path": self._safe_path_display(file_path)},
                ) from error

        return tuple(definition.model_copy(deep=True) for definition in loaded_definitions)

    def load_into_registry(
        self,
        registry: PromptRegistry,
        *,
        path: Path | None = None,
        recursive: bool = True,
        replace: bool = False,
    ) -> tuple[PromptDefinition, ...]:
        """Load prompt definitions from disk and register them."""

        definitions = self.load_directory(path, recursive=recursive)
        for definition in definitions:
            registry.register(definition, replace=replace)
        return tuple(definition.model_copy(deep=True) for definition in definitions)

    def _resolve_path(self, path: Path) -> Path:
        """Resolve a path safely inside the prompt base directory."""

        candidate = Path(path)
        resolved_path = (self.base_dir / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if not resolved_path.is_relative_to(self.base_dir):
            raise PromptLoadError(
                "prompt path must stay within the configured prompt base directory",
                code="prompt_load_outside_base_dir",
                details={"path": str(candidate)},
            )
        return resolved_path

    def _safe_path_display(self, path: Path) -> str:
        """Return a safe display path relative to the prompt base directory when possible."""

        try:
            return path.resolve().relative_to(self.base_dir).as_posix()
        except ValueError:
            return path.name


__all__ = ["PromptLoader"]
