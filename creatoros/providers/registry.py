"""Provider registry for CreatorOS provider contract resolution."""

from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from creatoros.config import get_settings
from creatoros.core import (
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
    ProviderRegistryError,
    ProviderTypeMismatchError,
)
from creatoros.providers.base import ProviderInfo
from creatoros.providers.contracts import LLMProvider, Provider

TProvider = TypeVar("TProvider")


def _normalize_key(value: str, *, field_name: str) -> str:
    """Normalize provider lookup keys to lowercase and reject blank values."""

    normalized_value = value.strip().lower()
    if not normalized_value:
        raise ProviderRegistryError(
            f"{field_name} must not be blank",
            code="provider_registry_invalid_identifier",
            details={"field_name": field_name},
        )
    return normalized_value


class ProviderRegistry:
    """Store and resolve provider implementations by normalized type and name."""

    def __init__(self) -> None:
        self._providers: dict[str, dict[str, Provider]] = {}

    def register(self, provider: Provider, *, replace: bool = False) -> None:
        """Register a provider implementation without performing network checks."""

        if not isinstance(provider, Provider):
            raise ProviderRegistryError(
                "provider must satisfy the Provider protocol",
                code="provider_registry_invalid_provider",
                details={"required_protocol": "Provider"},
            )

        provider_info = provider.info
        provider_type_key = _normalize_key(provider_info.provider_type, field_name="provider_type")
        provider_name_key = _normalize_key(provider_info.name, field_name="name")

        provider_group = self._providers.setdefault(provider_type_key, {})
        if provider_name_key in provider_group and not replace:
            raise ProviderAlreadyRegisteredError(provider_type_key, provider_name_key)

        provider_group[provider_name_key] = provider

    def unregister(self, provider_type: str, name: str) -> Provider:
        """Remove and return a registered provider."""

        provider_type_key = _normalize_key(provider_type, field_name="provider_type")
        provider_name_key = _normalize_key(name, field_name="name")
        provider_group = self._providers.get(provider_type_key)
        if provider_group is None or provider_name_key not in provider_group:
            raise ProviderNotFoundError(provider_type_key, provider_name_key)

        provider = provider_group.pop(provider_name_key)
        if not provider_group:
            self._providers.pop(provider_type_key, None)
        return provider

    def get(self, provider_type: str, name: str) -> Provider:
        """Return a registered provider by normalized type and name."""

        provider_type_key = _normalize_key(provider_type, field_name="provider_type")
        provider_name_key = _normalize_key(name, field_name="name")
        provider_group = self._providers.get(provider_type_key)
        if provider_group is None or provider_name_key not in provider_group:
            raise ProviderNotFoundError(provider_type_key, provider_name_key)
        return provider_group[provider_name_key]

    def get_typed(
        self,
        provider_type: str,
        name: str,
        expected_type: type[TProvider],
    ) -> TProvider:
        """Return a provider and validate that it satisfies the expected contract."""

        provider = self.get(provider_type, name)
        if not isinstance(provider, expected_type):
            expected_type_name = getattr(expected_type, "__name__", str(expected_type))
            raise ProviderTypeMismatchError(
                _normalize_key(provider_type, field_name="provider_type"),
                _normalize_key(name, field_name="name"),
                expected_type_name,
            )
        return provider

    def contains(self, provider_type: str, name: str) -> bool:
        """Return whether a provider registration exists."""

        provider_type_key = _normalize_key(provider_type, field_name="provider_type")
        provider_name_key = _normalize_key(name, field_name="name")
        provider_group = self._providers.get(provider_type_key)
        return provider_group is not None and provider_name_key in provider_group

    def list_providers(self, provider_type: str | None = None) -> tuple[ProviderInfo, ...]:
        """Return immutable provider metadata sorted predictably by type and name."""

        if provider_type is not None:
            provider_type_key = _normalize_key(provider_type, field_name="provider_type")
            provider_group = self._providers.get(provider_type_key)
            if provider_group is None:
                return ()
            sorted_providers = sorted(
                provider_group.values(),
                key=lambda provider: provider.info.name.strip().lower(),
            )
            return tuple(provider.info for provider in sorted_providers)

        sorted_providers = sorted(
            (
                provider
                for provider_group in self._providers.values()
                for provider in provider_group.values()
            ),
            key=lambda provider: (
                provider.info.provider_type.strip().lower(),
                provider.info.name.strip().lower(),
            ),
        )
        return tuple(provider.info for provider in sorted_providers)

    def clear(self) -> None:
        """Remove all registered providers."""

        self._providers.clear()


def create_provider_registry() -> ProviderRegistry:
    """Create a new empty provider registry."""

    return ProviderRegistry()


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    """Return the cached application-level provider registry."""

    return create_provider_registry()


def resolve_default_llm_provider(registry: ProviderRegistry) -> LLMProvider:
    """Resolve the configured default LLM provider from the supplied registry."""

    settings = get_settings()
    provider = registry.get("llm", settings.default_llm_provider)
    if not isinstance(provider, LLMProvider):
        raise ProviderTypeMismatchError("llm", settings.default_llm_provider.strip().lower(), "LLMProvider")
    return provider


__all__ = [
    "ProviderRegistry",
    "create_provider_registry",
    "get_provider_registry",
    "resolve_default_llm_provider",
]
