"""Application-layer service for provider-independent media generation."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field, field_validator, model_validator

from creatoros.config import Settings, get_settings
from creatoros.core import CreatorOSValidationError, ProviderTypeMismatchError
from creatoros.domain import CreatorOSModel
from creatoros.observability import get_logger
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ImageGenerationRequest,
    ImageProvider,
    ProviderRegistry,
    ProviderRequestContext,
    TTSGenerationRequest,
    TTSProvider,
    VideoGenerationRequest,
    VideoProvider,
)
from creatoros.providers.mock import create_mock_provider_registry


def _normalize_optional_string(value: str | None, *, field_name: str) -> str | None:
    """Normalize optional identifiers to stripped values or ``None``."""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


def _copy_requests[TRequest: CreatorOSModel](value: Iterable[TRequest] | None) -> tuple[TRequest, ...]:
    """Return one immutable deep-copied tuple of request models."""

    if value is None:
        return ()
    return tuple(item.model_copy(deep=True) for item in value)


class MediaProviderSelection(CreatorOSModel):
    """Optional provider overrides for bounded media-package generation."""

    image_provider_name: str | None = None
    tts_provider_name: str | None = None
    video_provider_name: str | None = None
    hosting_provider_name: str | None = None

    @field_validator(
        "image_provider_name",
        "tts_provider_name",
        "video_provider_name",
        "hosting_provider_name",
    )
    @classmethod
    def normalize_provider_names(cls, value: str | None, info) -> str | None:
        """Normalize optional provider override identifiers."""

        return _normalize_optional_string(value, field_name=info.field_name)


class MediaGenerationPackageRequest(CreatorOSModel):
    """Bounded service-level request for media generation without rendering."""

    thumbnail_request: ImageGenerationRequest | None = None
    narration_request: TTSGenerationRequest | None = None
    scene_image_requests: tuple[ImageGenerationRequest, ...] = Field(default_factory=tuple)
    scene_video_requests: tuple[VideoGenerationRequest, ...] = Field(default_factory=tuple)
    provider_selection: MediaProviderSelection | None = None

    @field_validator("scene_image_requests", "scene_video_requests", mode="before")
    @classmethod
    def copy_request_collections(cls, value: object, info) -> tuple[CreatorOSModel, ...]:
        """Normalize bounded request collections into immutable tuples."""

        if value is None:
            return ()
        if not isinstance(value, Iterable) or isinstance(value, str | bytes):
            raise TypeError(f"{info.field_name} must be an iterable of request models")
        return _copy_requests(value)

    @model_validator(mode="after")
    def validate_not_empty(self) -> MediaGenerationPackageRequest:
        """Require at least one media generation request."""

        if (
            self.thumbnail_request is None
            and self.narration_request is None
            and not self.scene_image_requests
            and not self.scene_video_requests
        ):
            raise ValueError("at least one media request must be supplied")
        return self


class GeneratedMediaPackage(CreatorOSModel):
    """Aggregate generated media references without rendering or materialization."""

    thumbnail: GeneratedImage | None = None
    narration: GeneratedAudio | None = None
    scene_images: tuple[GeneratedImage, ...] = Field(default_factory=tuple)
    scene_videos: tuple[GeneratedVideo, ...] = Field(default_factory=tuple)

    @field_validator("scene_images", "scene_videos", mode="before")
    @classmethod
    def copy_generated_collections(cls, value: object, info) -> tuple[CreatorOSModel, ...]:
        """Normalize generated result collections into immutable tuples."""

        if value is None:
            return ()
        if not isinstance(value, Iterable) or isinstance(value, str | bytes):
            raise TypeError(f"{info.field_name} must be an iterable of generated models")
        return _copy_requests(value)


class MediaGenerationService:
    """Coordinate bounded media-generation provider calls without rendering."""

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        settings: Settings,
    ) -> None:
        if not isinstance(provider_registry, ProviderRegistry):
            raise CreatorOSValidationError(
                "provider_registry must be a ProviderRegistry",
                code="service_invalid_dependency",
                details={"dependency": "provider_registry"},
            )
        if not isinstance(settings, Settings):
            raise CreatorOSValidationError(
                "settings must be a Settings instance",
                code="service_invalid_dependency",
                details={"dependency": "settings"},
            )
        self.provider_registry = provider_registry
        self.settings = settings
        self.logger = get_logger("services.media_generation")

    async def generate_image(
        self,
        request: ImageGenerationRequest,
        *,
        provider_name: str | None = None,
        context: ProviderRequestContext | None = None,
    ) -> GeneratedImage:
        """Generate one image through the resolved image provider."""

        provider = self._resolve_image_provider(provider_name)
        self.logger.info(
            "media_generation_started",
            operation="generate_image",
            provider_name=provider.info.name,
            asset_count=1,
        )
        result = await provider.generate(request, context=context)
        self.logger.info(
            "media_generation_completed",
            operation="generate_image",
            provider_name=result.data.provider_name,
            asset_count=1,
            success=True,
        )
        return result.data.model_copy(deep=True)

    async def generate_audio(
        self,
        request: TTSGenerationRequest,
        *,
        provider_name: str | None = None,
        context: ProviderRequestContext | None = None,
    ) -> GeneratedAudio:
        """Generate one audio artifact through the resolved TTS provider."""

        provider = self._resolve_tts_provider(provider_name)
        self.logger.info(
            "media_generation_started",
            operation="generate_audio",
            provider_name=provider.info.name,
            asset_count=1,
        )
        result = await provider.generate(request, context=context)
        self.logger.info(
            "media_generation_completed",
            operation="generate_audio",
            provider_name=result.data.provider_name,
            asset_count=1,
            success=True,
        )
        return result.data.model_copy(deep=True)

    async def generate_video(
        self,
        request: VideoGenerationRequest,
        *,
        provider_name: str | None = None,
        context: ProviderRequestContext | None = None,
    ) -> GeneratedVideo:
        """Generate one video clip through the resolved video provider."""

        provider = self._resolve_video_provider(provider_name)
        self.logger.info(
            "media_generation_started",
            operation="generate_video",
            provider_name=provider.info.name,
            asset_count=1,
        )
        result = await provider.generate(request, context=context)
        self.logger.info(
            "media_generation_completed",
            operation="generate_video",
            provider_name=result.data.provider_name,
            asset_count=1,
            success=True,
        )
        return result.data.model_copy(deep=True)

    async def generate_package(
        self,
        request: MediaGenerationPackageRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> GeneratedMediaPackage:
        """Generate a bounded media package in deterministic order and fail fast."""

        selection = (
            MediaProviderSelection()
            if request.provider_selection is None
            else request.provider_selection
        )
        thumbnail: GeneratedImage | None = None
        narration: GeneratedAudio | None = None
        scene_images: list[GeneratedImage] = []
        scene_videos: list[GeneratedVideo] = []

        self.logger.info(
            "media_package_generation_started",
            operation="generate_package",
            asset_count=(
                (1 if request.thumbnail_request is not None else 0)
                + (1 if request.narration_request is not None else 0)
                + len(request.scene_image_requests)
                + len(request.scene_video_requests)
            ),
        )

        if request.thumbnail_request is not None:
            thumbnail = await self.generate_image(
                request.thumbnail_request,
                provider_name=selection.image_provider_name,
                context=context,
            )

        if request.narration_request is not None:
            narration = await self.generate_audio(
                request.narration_request,
                provider_name=selection.tts_provider_name,
                context=context,
            )

        for scene_image_request in request.scene_image_requests:
            scene_images.append(
                await self.generate_image(
                    scene_image_request,
                    provider_name=selection.image_provider_name,
                    context=context,
                )
            )

        for scene_video_request in request.scene_video_requests:
            scene_videos.append(
                await self.generate_video(
                    scene_video_request,
                    provider_name=selection.video_provider_name,
                    context=context,
                )
            )

        package = GeneratedMediaPackage(
            thumbnail=thumbnail,
            narration=narration,
            scene_images=tuple(scene_images),
            scene_videos=tuple(scene_videos),
        )
        self.logger.info(
            "media_package_generation_completed",
            operation="generate_package",
            asset_count=len(package.scene_images) + len(package.scene_videos),
            success=True,
        )
        return package

    def _resolve_image_provider(self, provider_name: str | None) -> ImageProvider:
        """Resolve either an explicit or configured default image provider."""

        resolved_provider_name = self.settings.default_image_provider if provider_name is None else provider_name
        provider = self.provider_registry.get("image", resolved_provider_name)
        if not isinstance(provider, ImageProvider):
            raise ProviderTypeMismatchError(
                "image",
                resolved_provider_name.strip().lower(),
                "ImageProvider",
            )
        return provider

    def _resolve_tts_provider(self, provider_name: str | None) -> TTSProvider:
        """Resolve either an explicit or configured default TTS provider."""

        resolved_provider_name = self.settings.default_tts_provider if provider_name is None else provider_name
        provider = self.provider_registry.get("voice", resolved_provider_name)
        if not isinstance(provider, TTSProvider):
            raise ProviderTypeMismatchError(
                "voice",
                resolved_provider_name.strip().lower(),
                "TTSProvider",
            )
        return provider

    def _resolve_video_provider(self, provider_name: str | None) -> VideoProvider:
        """Resolve either an explicit or configured default video provider."""

        resolved_provider_name = self.settings.default_video_provider if provider_name is None else provider_name
        provider = self.provider_registry.get("video", resolved_provider_name)
        if not isinstance(provider, VideoProvider):
            raise ProviderTypeMismatchError(
                "video",
                resolved_provider_name.strip().lower(),
                "VideoProvider",
            )
        return provider


def create_media_generation_service(
    *,
    provider_registry: ProviderRegistry | None = None,
    settings: Settings | None = None,
) -> MediaGenerationService:
    """Create a safe default media-generation service using mock providers."""

    resolved_settings = get_settings() if settings is None else settings
    resolved_provider_registry = (
        create_mock_provider_registry()
        if provider_registry is None
        else provider_registry
    )
    return MediaGenerationService(resolved_provider_registry, resolved_settings)


__all__ = [
    "GeneratedMediaPackage",
    "MediaGenerationPackageRequest",
    "MediaGenerationService",
    "MediaProviderSelection",
    "create_media_generation_service",
]
