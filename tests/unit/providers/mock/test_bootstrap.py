"""Unit tests for CreatorOS mock provider bootstrap helpers."""

import pytest

from creatoros.core import ProviderAlreadyRegisteredError
from creatoros.providers import (
    AnalyticsProvider,
    ImageProvider,
    LLMProvider,
    Provider,
    PublishingProvider,
    SearchProvider,
    StorageProvider,
    TrendProvider,
    TTSProvider,
    VideoProvider,
    VoiceProvider,
    create_provider_registry,
)
from creatoros.providers.mock import (
    MockAnalyticsProvider,
    MockImageProvider,
    MockLLMProvider,
    MockPublishingProvider,
    MockSearchProvider,
    MockStorageProvider,
    MockTrendProvider,
    MockTTSProvider,
    MockVideoProvider,
    MockVoiceProvider,
    create_mock_image_provider_registry,
    create_mock_provider_registry,
    create_mock_tts_provider_registry,
    create_mock_video_provider_registry,
    register_mock_providers,
)


def test_register_mock_providers_registers_all_expected_provider_types() -> None:
    """Bootstrap registration should populate all expected provider groups."""

    registry = create_provider_registry()

    register_mock_providers(registry)

    assert {info.provider_type for info in registry.list_providers()} == {
        "analytics",
        "image",
        "llm",
        "publishing",
        "search",
        "storage",
        "trend",
        "video",
        "voice",
    }


def test_duplicate_registration_is_rejected_when_replace_false() -> None:
    """Bootstrap registration should reject duplicates unless replacement is allowed."""

    registry = create_provider_registry()
    register_mock_providers(registry)

    with pytest.raises(ProviderAlreadyRegisteredError):
        register_mock_providers(registry, replace=False)


def test_replace_true_replaces_registrations_safely() -> None:
    """Bootstrap replacement should safely overwrite existing mock providers."""

    registry = create_provider_registry()
    register_mock_providers(registry)
    first_provider = registry.get("llm", "mock")

    register_mock_providers(registry, replace=True)
    second_provider = registry.get("llm", "mock")

    assert first_provider is not second_provider
    assert registry.contains("analytics", "mock")


def test_create_mock_provider_registry_returns_independent_populated_registries() -> None:
    """Fresh mock registries should be populated and independent."""

    first = create_mock_provider_registry()
    second = create_mock_provider_registry()

    assert first is not second
    assert first.list_providers() != ()
    assert second.list_providers() != ()


def test_every_mock_provider_satisfies_declared_runtime_protocol() -> None:
    """Every mock provider should satisfy the runtime protocol it declares."""

    llm = MockLLMProvider()
    trend = MockTrendProvider()
    search = MockSearchProvider()
    image = MockImageProvider()
    tts = MockTTSProvider()
    video = MockVideoProvider()
    voice = MockVoiceProvider()
    storage = MockStorageProvider()
    publishing = MockPublishingProvider()
    analytics = MockAnalyticsProvider()

    assert isinstance(llm, Provider)
    assert isinstance(llm, LLMProvider)
    assert isinstance(trend, TrendProvider)
    assert isinstance(search, SearchProvider)
    assert isinstance(image, ImageProvider)
    assert isinstance(tts, TTSProvider)
    assert isinstance(video, VideoProvider)
    assert isinstance(voice, VoiceProvider)
    assert isinstance(storage, StorageProvider)
    assert isinstance(publishing, PublishingProvider)
    assert isinstance(analytics, AnalyticsProvider)


def test_no_external_api_or_vendor_sdk_is_required() -> None:
    """The mock registry should be fully usable without external dependencies."""

    registry = create_mock_provider_registry()

    assert registry.contains("llm", "mock")
    assert registry.contains("publishing", "mock")


def test_capability_specific_mock_registry_factories_return_isolated_registries() -> None:
    """Capability-specific mock registry factories should stay isolated and minimal."""

    image_registry = create_mock_image_provider_registry()
    tts_registry = create_mock_tts_provider_registry()
    video_registry = create_mock_video_provider_registry()

    assert image_registry.contains("image", "mock") is True
    assert tts_registry.contains("voice", "mock") is True
    assert video_registry.contains("video", "mock") is True
    assert image_registry.list_providers("voice") == ()
    assert tts_registry.list_providers("image") == ()
    assert video_registry.list_providers("llm") == ()
