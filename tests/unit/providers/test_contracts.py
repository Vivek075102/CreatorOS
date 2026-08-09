"""Unit tests for CreatorOS provider protocols."""

from __future__ import annotations

from pydantic import BaseModel

from creatoros.domain import (
    AssetType,
    ContentPlatform,
    GeneratedAsset,
    HostedAsset,
    NarrationTrack,
    PerformanceReport,
    PublishedPost,
    PublishingPackage,
)
from creatoros.providers import (
    AnalyticsProvider,
    AssetHostingProvider,
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ImageGenerationRequest,
    ImageProvider,
    LLMCapabilities,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Provider,
    ProviderCapability,
    ProviderInfo,
    ProviderResult,
    PublishingProvider,
    RenderedVideo,
    RenderProvider,
    SearchProvider,
    ShortRenderRequest,
    StorageProvider,
    TrendProvider,
    TTSGenerationRequest,
    TTSProvider,
    VideoGenerationRequest,
    VideoProvider,
    VoiceProvider,
)


def build_provider_info(capability: ProviderCapability) -> ProviderInfo:
    """Create provider metadata for protocol fakes."""

    return ProviderInfo(name="Fake Provider", provider_type="test", capabilities={capability})


class StructuredOutput(BaseModel):
    """Structured response model used for protocol compatibility tests."""

    summary: str


class FakeProvider:
    """Minimal fake object satisfying the base Provider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.TEXT_GENERATION)

    async def health_check(self) -> bool:
        return True


class FakeLLMProvider(FakeProvider):
    """Minimal fake object satisfying the LLMProvider protocol."""

    @property
    def llm_capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_temperature=True,
            supports_max_output_tokens=True,
            supports_system_messages=True,
            supports_structured_text=True,
        )

    async def generate(self, request: LLMRequest, *, context=None) -> LLMResponse:
        return LLMResponse(
            text=request.messages[0].content,
            provider_name=self.info.name,
            model=request.model,
        )

    async def generate_text(self, prompt: str, *, context=None) -> ProviderResult[str]:
        return ProviderResult[str](data=prompt, provider=self.info)

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[StructuredOutput],
        context=None,
    ) -> ProviderResult[StructuredOutput]:
        return ProviderResult[StructuredOutput](
            data=response_model(summary=prompt),
            provider=self.info,
        )


class FakeTrendProvider(FakeProvider):
    """Minimal fake object satisfying the TrendProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.TREND_RESEARCH)

    async def research_trends(self, query: str, *, context=None) -> ProviderResult[list[dict[str, object]]]:
        return ProviderResult[list[dict[str, object]]](data=[{"query": query}], provider=self.info)


class FakeSearchProvider(FakeProvider):
    """Minimal fake object satisfying the SearchProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.WEB_SEARCH)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        context=None,
    ) -> ProviderResult[list[dict[str, object]]]:
        return ProviderResult[list[dict[str, object]]](data=[{"query": query, "limit": limit}], provider=self.info)


class FakeImageProvider(FakeProvider):
    """Minimal fake object satisfying the ImageProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.IMAGE_GENERATION)

    async def generate(self, request: ImageGenerationRequest, *, context=None) -> ProviderResult[GeneratedImage]:
        return ProviderResult[GeneratedImage](
            data=GeneratedImage(
                artifact=GeneratedAsset(
                    asset_type=AssetType.IMAGE,
                    uri=f"https://example.com/{request.prompt}.png",
                ),
                provider_name=self.info.name,
                model="fake-image-model",
                mime_type="image/png",
                width=request.width,
                height=request.height,
            ),
            provider=self.info,
        )

    async def generate_image(self, prompt: str, *, context=None) -> ProviderResult[GeneratedAsset]:
        return ProviderResult[GeneratedAsset](
            data=GeneratedAsset(asset_type=AssetType.IMAGE, uri=f"https://example.com/{prompt}.png"),
            provider=self.info,
        )


class FakeVideoProvider(FakeProvider):
    """Minimal fake object satisfying the VideoProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.VIDEO_GENERATION)

    async def generate(self, request: VideoGenerationRequest, *, context=None) -> ProviderResult[GeneratedVideo]:
        return ProviderResult[GeneratedVideo](
            data=GeneratedVideo(
                artifact=GeneratedAsset(
                    asset_type=AssetType.VIDEO,
                    uri=f"https://example.com/{request.prompt}.mp4",
                ),
                provider_name=self.info.name,
                model="fake-video-model",
                mime_type="video/mp4",
                duration_seconds=request.duration_seconds,
                width=request.width,
                height=request.height,
                fps=request.fps,
            ),
            provider=self.info,
        )

    async def generate_video(self, prompt: str, *, context=None) -> ProviderResult[GeneratedAsset]:
        return ProviderResult[GeneratedAsset](
            data=GeneratedAsset(asset_type=AssetType.VIDEO, uri=f"https://example.com/{prompt}.mp4"),
            provider=self.info,
        )


class FakeVoiceProvider(FakeProvider):
    """Minimal fake object satisfying the VoiceProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.VOICE_GENERATION)

    async def generate(self, request: TTSGenerationRequest, *, context=None) -> ProviderResult[GeneratedAudio]:
        return ProviderResult[GeneratedAudio](
            data=GeneratedAudio(
                artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="https://example.com/audio.wav"),
                provider_name=self.info.name,
                model="fake-tts-model",
                mime_type="audio/wav",
                voice=request.voice,
                language=request.language,
                estimated_duration_seconds=5.0,
            ),
            provider=self.info,
        )

    async def generate_voice(self, text: str, *, context=None) -> ProviderResult[NarrationTrack]:
        return ProviderResult[NarrationTrack](
            data=NarrationTrack(uri="https://example.com/audio.mp3", duration_seconds=5.0),
            provider=self.info,
        )


class FakeRenderProvider(FakeProvider):
    """Minimal fake object satisfying the RenderProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.RENDERING)

    async def render(self, request: ShortRenderRequest, *, context=None) -> ProviderResult[RenderedVideo]:
        return ProviderResult[RenderedVideo](
            data=RenderedVideo(
                artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri="https://example.com/final.mp4"),
                provider_name=self.info.name,
                mime_type="video/mp4",
                duration_seconds=request.total_duration_seconds,
                width=request.width,
                height=request.height,
                fps=request.fps,
            ),
            provider=self.info,
        )


class FakeStorageProvider(FakeProvider):
    """Minimal fake object satisfying the StorageProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.STORAGE)

    async def store(self, asset: GeneratedAsset, *, context=None) -> ProviderResult[GeneratedAsset]:
        return ProviderResult[GeneratedAsset](data=asset, provider=self.info)

    async def delete(self, asset_id: str, *, context=None) -> ProviderResult[bool]:
        return ProviderResult[bool](data=bool(asset_id), provider=self.info)


class FakeAssetHostingProvider(FakeProvider):
    """Minimal fake object satisfying the AssetHostingProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.ASSET_HOSTING)

    async def host(self, asset: GeneratedAsset, *, context=None) -> ProviderResult[HostedAsset]:
        return ProviderResult[HostedAsset](
            data=HostedAsset(
                source_asset=asset,
                public_url="https://example.com/public/image.png",
                provider_name=self.info.name,
                provider_asset_id="creatoros/run_001/asset_123",
            ),
            provider=self.info,
        )

    async def delete(self, hosted_asset: HostedAsset, *, context=None) -> ProviderResult[bool]:
        return ProviderResult[bool](data=bool(hosted_asset.provider_asset_id), provider=self.info)


class FakePublishingProvider(FakeProvider):
    """Minimal fake object satisfying the PublishingProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.PUBLISHING)

    async def publish(self, package: PublishingPackage, *, context=None) -> ProviderResult[PublishedPost]:
        return ProviderResult[PublishedPost](
            data=PublishedPost(
                platform=package.platform,
                external_id="external_123",
                url="https://example.com/post/external_123",
            ),
            provider=self.info,
        )

    async def get_status(self, external_id: str, *, context=None) -> ProviderResult[str]:
        return ProviderResult[str](data=f"status:{external_id}", provider=self.info)


class FakeAnalyticsProvider(FakeProvider):
    """Minimal fake object satisfying the AnalyticsProvider protocol."""

    @property
    def info(self) -> ProviderInfo:
        return build_provider_info(ProviderCapability.ANALYTICS)

    async def fetch_performance(self, post: PublishedPost, *, context=None) -> ProviderResult[PerformanceReport]:
        return ProviderResult[PerformanceReport](
            data=PerformanceReport(post_id=post.id, metrics={"views": 100}),
            provider=self.info,
        )


def test_provider_protocol_is_runtime_checkable() -> None:
    """A minimal structural provider should satisfy the Provider protocol."""

    assert isinstance(FakeProvider(), Provider)


def test_llm_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural LLM provider should satisfy the protocol."""

    assert isinstance(FakeLLMProvider(), LLMProvider)


def test_trend_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural trend provider should satisfy the protocol."""

    assert isinstance(FakeTrendProvider(), TrendProvider)


def test_search_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural search provider should satisfy the protocol."""

    assert isinstance(FakeSearchProvider(), SearchProvider)


def test_image_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural image provider should satisfy the protocol."""

    assert isinstance(FakeImageProvider(), ImageProvider)


def test_video_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural video provider should satisfy the protocol."""

    assert isinstance(FakeVideoProvider(), VideoProvider)


def test_voice_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural voice provider should satisfy the protocol."""

    assert isinstance(FakeVoiceProvider(), VoiceProvider)


def test_tts_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural TTS provider should satisfy the protocol."""

    assert isinstance(FakeVoiceProvider(), TTSProvider)


def test_render_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural render provider should satisfy the protocol."""

    assert isinstance(FakeRenderProvider(), RenderProvider)


def test_storage_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural storage provider should satisfy the protocol."""

    assert isinstance(FakeStorageProvider(), StorageProvider)


def test_asset_hosting_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural asset-hosting provider should satisfy the protocol."""

    assert isinstance(FakeAssetHostingProvider(), AssetHostingProvider)


def test_publishing_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural publishing provider should satisfy the protocol."""

    assert isinstance(FakePublishingProvider(), PublishingProvider)


def test_analytics_provider_protocol_accepts_minimal_fake() -> None:
    """A minimal structural analytics provider should satisfy the protocol."""

    assert isinstance(FakeAnalyticsProvider(), AnalyticsProvider)


def test_protocols_do_not_require_vendor_sdk_types() -> None:
    """Provider protocols should remain satisfiable with plain Python and project types."""

    package = PublishingPackage(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        title="Boss Guide",
        description="Fast strategy breakdown.",
    )

    assert isinstance(FakeLLMProvider(), Provider)
    assert isinstance(FakePublishingProvider(), Provider)
    assert package.platform is ContentPlatform.YOUTUBE_SHORTS
