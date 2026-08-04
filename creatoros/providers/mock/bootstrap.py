"""Bootstrap helpers for deterministic CreatorOS mock providers."""

from __future__ import annotations

from creatoros.providers.mock.analytics import MockAnalyticsProvider
from creatoros.providers.mock.llm import MockLLMProvider
from creatoros.providers.mock.media import MockImageProvider, MockVideoProvider, MockVoiceProvider
from creatoros.providers.mock.publishing import MockPublishingProvider
from creatoros.providers.mock.search import MockSearchProvider
from creatoros.providers.mock.storage import MockStorageProvider
from creatoros.providers.mock.trends import MockTrendProvider
from creatoros.providers.registry import ProviderRegistry, create_provider_registry


def register_mock_providers(
    registry: ProviderRegistry,
    *,
    replace: bool = False,
) -> None:
    """Register one deterministic instance of every mock provider."""

    for provider in (
        MockLLMProvider(),
        MockTrendProvider(),
        MockSearchProvider(),
        MockImageProvider(),
        MockVideoProvider(),
        MockVoiceProvider(),
        MockStorageProvider(),
        MockPublishingProvider(),
        MockAnalyticsProvider(),
    ):
        registry.register(provider, replace=replace)


def create_mock_provider_registry() -> ProviderRegistry:
    """Return a fresh populated registry containing all mock providers."""

    registry = create_provider_registry()
    register_mock_providers(registry)
    return registry


__all__ = [
    "create_mock_provider_registry",
    "register_mock_providers",
]
