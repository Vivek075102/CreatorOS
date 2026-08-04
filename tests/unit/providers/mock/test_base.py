"""Unit tests for the shared CreatorOS mock provider base."""

import asyncio

from creatoros.providers import ProviderCapability
from creatoros.providers.mock import MockProviderBase


def test_info_is_valid_and_stable() -> None:
    """Mock provider base should expose stable provider metadata."""

    provider = MockProviderBase(
        name="mock",
        provider_type="llm",
        capabilities={ProviderCapability.TEXT_GENERATION},
    )

    info = provider.info
    assert info.name == "mock"
    assert info.provider_type == "llm"


def test_health_check_reflects_configured_health() -> None:
    """Health checks should return the configured deterministic value."""

    healthy = MockProviderBase(
        name="mock",
        provider_type="llm",
        capabilities={ProviderCapability.TEXT_GENERATION},
        is_healthy=True,
    )
    unhealthy = MockProviderBase(
        name="mock",
        provider_type="llm",
        capabilities={ProviderCapability.TEXT_GENERATION},
        is_healthy=False,
    )

    assert asyncio.run(healthy.health_check()) is True
    assert asyncio.run(unhealthy.health_check()) is False


def test_provider_metadata_is_not_mutable_through_callers() -> None:
    """Callers should not be able to mutate the provider's stored metadata."""

    provider = MockProviderBase(
        name="mock",
        provider_type="llm",
        capabilities={ProviderCapability.TEXT_GENERATION},
    )

    info = provider.info
    info.metadata["changed"] = True

    assert provider.info.metadata == {}
