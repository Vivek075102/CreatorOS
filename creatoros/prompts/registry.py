"""Registry for versioned provider-independent CreatorOS prompt assets."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from creatoros.core import (
    PromptAlreadyRegisteredError,
    PromptNotFoundError,
    PromptRegistryError,
)
from creatoros.prompts.enums import PromptStatus
from creatoros.prompts.models import PromptDefinition


def _normalize_prompt_name(name: str, *, field_name: str = "name") -> str:
    """Normalize and validate prompt names used for registry lookup."""

    normalized_name = name.strip()
    if not normalized_name:
        raise PromptRegistryError(
            f"{field_name} must not be blank",
            code="prompt_registry_invalid_name",
            details={"field_name": field_name},
        )
    return normalized_name.casefold()


def _validate_version(version: int) -> int:
    """Validate a prompt version used for registry lookup."""

    if version < 1:
        raise PromptRegistryError(
            "version must be greater than or equal to 1",
            code="prompt_registry_invalid_version",
            details={"version": version},
        )
    return version


class PromptRegistry:
    """Store prompt definitions by normalized name and version."""

    def __init__(self) -> None:
        self._definitions: dict[str, dict[int, PromptDefinition]] = {}

    def register(
        self,
        definition: PromptDefinition,
        *,
        replace: bool = False,
    ) -> None:
        """Register a prompt definition in the registry."""

        normalized_name = _normalize_prompt_name(definition.name)
        version = _validate_version(definition.version)
        versions = self._definitions.setdefault(normalized_name, {})
        if version in versions and not replace:
            raise PromptAlreadyRegisteredError(definition.name, version)
        versions[version] = definition.model_copy(deep=True)

    def unregister(
        self,
        name: str,
        version: int,
    ) -> PromptDefinition:
        """Remove and return a registered prompt definition."""

        normalized_name = _normalize_prompt_name(name)
        normalized_version = _validate_version(version)
        versions = self._definitions.get(normalized_name)
        if versions is None or normalized_version not in versions:
            raise PromptNotFoundError(name, normalized_version)

        removed = versions.pop(normalized_version)
        if not versions:
            self._definitions.pop(normalized_name, None)
        return removed.model_copy(deep=True)

    def get(
        self,
        name: str,
        version: int | None = None,
    ) -> PromptDefinition:
        """Return a prompt definition by exact version or highest active version."""

        normalized_name = _normalize_prompt_name(name)
        versions = self._definitions.get(normalized_name)
        if not versions:
            raise PromptNotFoundError(name, version)

        if version is not None:
            normalized_version = _validate_version(version)
            definition = versions.get(normalized_version)
            if definition is None:
                raise PromptNotFoundError(name, normalized_version)
            return definition.model_copy(deep=True)

        active_versions = [
            definition
            for definition in versions.values()
            if definition.status is PromptStatus.ACTIVE
        ]
        if not active_versions:
            raise PromptNotFoundError(name, None, active_only=True)

        definition = max(active_versions, key=lambda item: item.version)
        return definition.model_copy(deep=True)

    def list_prompts(
        self,
        *,
        name: str | None = None,
        status: PromptStatus | None = None,
    ) -> tuple[PromptDefinition, ...]:
        """Return immutable deep copies of registered prompt definitions."""

        definitions: Iterable[PromptDefinition]
        if name is None:
            definitions = (
                definition
                for versions in self._definitions.values()
                for definition in versions.values()
            )
        else:
            versions = self._definitions.get(_normalize_prompt_name(name), {})
            definitions = versions.values()

        filtered_definitions = [
            definition.model_copy(deep=True)
            for definition in definitions
            if status is None or definition.status is status
        ]
        filtered_definitions.sort(
            key=lambda definition: (definition.name.strip().casefold(), definition.version)
        )
        return tuple(filtered_definitions)

    def contains(
        self,
        name: str,
        version: int,
    ) -> bool:
        """Return whether a prompt definition is registered."""

        normalized_name = _normalize_prompt_name(name)
        normalized_version = _validate_version(version)
        versions = self._definitions.get(normalized_name)
        return versions is not None and normalized_version in versions

    def clear(self) -> None:
        """Remove all prompt definitions from the registry."""

        self._definitions.clear()


def create_prompt_registry() -> PromptRegistry:
    """Return a fresh empty prompt registry."""

    return PromptRegistry()


@lru_cache(maxsize=1)
def get_prompt_registry() -> PromptRegistry:
    """Return the cached application-level prompt registry."""

    return create_prompt_registry()


__all__ = [
    "PromptRegistry",
    "create_prompt_registry",
    "get_prompt_registry",
]
