"""Provider protocols that define stable CreatorOS integration boundaries."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from creatoros.domain import (
    GeneratedAsset,
    NarrationTrack,
    PerformanceReport,
    PublishedPost,
    PublishingPackage,
)
from creatoros.providers.base import ProviderInfo, ProviderRequestContext, ProviderResult

TStructured = TypeVar("TStructured", bound=BaseModel)


@runtime_checkable
class Provider(Protocol):
    """Base protocol implemented by all CreatorOS providers."""

    @property
    def info(self) -> ProviderInfo:
        """Return metadata describing the provider implementation."""

    async def health_check(self) -> bool:
        """Return whether the provider is operational."""


@runtime_checkable
class LLMProvider(Provider, Protocol):
    """Provider contract for text and structured generation capabilities."""

    async def generate_text(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[str]:
        """Generate free-form text for a validated prompt."""

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[TStructured],
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[TStructured]:
        """Generate structured output validated against a Pydantic response model."""


@runtime_checkable
class TrendProvider(Provider, Protocol):
    """Provider contract for raw trend-research results at the integration boundary."""

    async def research_trends(
        self,
        query: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[list[dict[str, object]]]:
        """Return provider-shaped trend data for later normalization by domain engines."""


@runtime_checkable
class SearchProvider(Provider, Protocol):
    """Provider contract for raw search results at the integration boundary."""

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[list[dict[str, object]]]:
        """Return provider-shaped search data for later normalization by domain engines."""


@runtime_checkable
class ImageProvider(Provider, Protocol):
    """Provider contract for image generation."""

    async def generate_image(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Generate an image asset."""


@runtime_checkable
class VideoProvider(Provider, Protocol):
    """Provider contract for video generation."""

    async def generate_video(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Generate a video asset."""


@runtime_checkable
class VoiceProvider(Provider, Protocol):
    """Provider contract for narration generation."""

    async def generate_voice(
        self,
        text: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[NarrationTrack]:
        """Generate a narration track."""


@runtime_checkable
class StorageProvider(Provider, Protocol):
    """Provider contract for asset storage and deletion."""

    async def store(
        self,
        asset: GeneratedAsset,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Persist an asset and return the stored representation."""

    async def delete(
        self,
        asset_id: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[bool]:
        """Delete a stored asset by identifier."""


@runtime_checkable
class PublishingProvider(Provider, Protocol):
    """Provider contract for publishing content to external platforms."""

    async def publish(
        self,
        package: PublishingPackage,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[PublishedPost]:
        """Publish a package and return the created external post contract."""

    async def get_status(
        self,
        external_id: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[str]:
        """Return the current external publishing status."""


@runtime_checkable
class AnalyticsProvider(Provider, Protocol):
    """Provider contract for post-publication analytics retrieval."""

    async def fetch_performance(
        self,
        post: PublishedPost,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[PerformanceReport]:
        """Return normalized performance data for a published post."""


__all__ = [
    "AnalyticsProvider",
    "ImageProvider",
    "LLMProvider",
    "Provider",
    "PublishingProvider",
    "SearchProvider",
    "StorageProvider",
    "TrendProvider",
    "VideoProvider",
    "VoiceProvider",
]
