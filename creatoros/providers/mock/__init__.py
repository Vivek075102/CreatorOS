"""Deterministic mock provider implementations for CreatorOS."""

from creatoros.providers.mock.analytics import MockAnalyticsProvider
from creatoros.providers.mock.base import MockProviderBase
from creatoros.providers.mock.bootstrap import (
    create_mock_asset_hosting_provider_registry,
    create_mock_image_provider_registry,
    create_mock_provider_registry,
    create_mock_render_provider_registry,
    create_mock_tts_provider_registry,
    create_mock_video_provider_registry,
    register_mock_providers,
)
from creatoros.providers.mock.hosting import MockAssetHostingProvider
from creatoros.providers.mock.llm import MockLLMProvider
from creatoros.providers.mock.media import (
    MockImageProvider,
    MockTTSProvider,
    MockVideoProvider,
    MockVoiceProvider,
)
from creatoros.providers.mock.publishing import MockPublishingProvider
from creatoros.providers.mock.render import MockRenderProvider
from creatoros.providers.mock.search import MockSearchProvider
from creatoros.providers.mock.storage import MockStorageProvider
from creatoros.providers.mock.trends import MockTrendProvider

__all__ = [
    "MockAnalyticsProvider",
    "MockAssetHostingProvider",
    "MockImageProvider",
    "MockLLMProvider",
    "MockProviderBase",
    "MockPublishingProvider",
    "MockRenderProvider",
    "MockSearchProvider",
    "MockStorageProvider",
    "MockTTSProvider",
    "MockTrendProvider",
    "MockVideoProvider",
    "MockVoiceProvider",
    "create_mock_asset_hosting_provider_registry",
    "create_mock_image_provider_registry",
    "create_mock_provider_registry",
    "create_mock_render_provider_registry",
    "create_mock_tts_provider_registry",
    "create_mock_video_provider_registry",
    "register_mock_providers",
]
