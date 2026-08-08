"""Unit tests for the CreatorOS media generation service."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai.types.image import Image
from openai.types.images_response import ImagesResponse, Usage

from creatoros.config import Settings
from creatoros.core import CreatorOSValidationError, ProviderNotFoundError
from creatoros.providers import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ImageGenerationRequest,
    ProviderCapability,
    ProviderInfo,
    TTSGenerationRequest,
    VideoGenerationRequest,
    create_provider_registry,
)
from creatoros.providers.mock import MockImageProvider, MockTTSProvider, MockVideoProvider
from creatoros.providers.openai import OpenAIImageProvider, OpenAITTSProvider
from creatoros.services import (
    GeneratedMediaPackage,
    MediaGenerationPackageRequest,
    MediaGenerationService,
    MediaProviderSelection,
    create_media_generation_service,
)


def build_settings(
    *,
    default_image_provider: str = "mock",
    default_tts_provider: str = "mock",
    default_video_provider: str = "mock",
) -> Settings:
    """Create isolated settings without reading the live environment."""

    project_root = Path("C:/GamingAIFactory")
    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider="mock",
        default_llm_model="mock-model",
        default_image_provider=default_image_provider,
        default_image_model=None,
        default_tts_provider=default_tts_provider,
        default_tts_model=None,
        default_video_provider=default_video_provider,
        default_render_provider="mock",
        openai_api_key=None,
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        provider_max_retries=3,
        assets_dir=project_root / "assets",
        logs_dir=project_root / "logs",
        prompts_dir=project_root / "prompts",
    )


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute one coroutine in synchronous unit tests."""

    return asyncio.run(coro)


def build_image_request(prompt: str = "Thumbnail prompt") -> ImageGenerationRequest:
    """Create a reusable image request."""

    return ImageGenerationRequest(prompt=prompt, width=1024, height=1024)


def build_tts_request(text: str = "Narrate this line", voice: str = "alloy") -> TTSGenerationRequest:
    """Create a reusable TTS request."""

    return TTSGenerationRequest(text=text, voice=voice)


def build_video_request(prompt: str = "Scene clip", duration_seconds: float = 4.0) -> VideoGenerationRequest:
    """Create a reusable video request."""

    return VideoGenerationRequest(prompt=prompt, duration_seconds=duration_seconds)


class RecordingImageProvider(MockImageProvider):
    """Mock image provider that records service calls."""

    def __init__(self, *, name: str = "mock") -> None:
        super().__init__()
        self._info = ProviderInfo(
            name=name,
            provider_type="image",
            capabilities={ProviderCapability.IMAGE_GENERATION},
        )
        self.calls = 0
        self.last_request: ImageGenerationRequest | None = None

    @property
    def info(self) -> ProviderInfo:
        return self._info

    async def generate(self, request: ImageGenerationRequest, *, context=None):
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        return await super().generate(request, context=context)


class RecordingTTSProvider(MockTTSProvider):
    """Mock TTS provider that records service calls."""

    def __init__(self, *, name: str = "mock") -> None:
        super().__init__()
        self._info = ProviderInfo(
            name=name,
            provider_type="voice",
            capabilities={ProviderCapability.VOICE_GENERATION},
        )
        self.calls = 0
        self.last_request: TTSGenerationRequest | None = None

    @property
    def info(self) -> ProviderInfo:
        return self._info

    async def generate(self, request: TTSGenerationRequest, *, context=None):
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        return await super().generate(request, context=context)


class RecordingVideoProvider(MockVideoProvider):
    """Mock video provider that records service calls."""

    def __init__(self, *, name: str = "mock") -> None:
        super().__init__()
        self._info = ProviderInfo(
            name=name,
            provider_type="video",
            capabilities={ProviderCapability.VIDEO_GENERATION},
        )
        self.calls = 0
        self.last_request: VideoGenerationRequest | None = None

    @property
    def info(self) -> ProviderInfo:
        return self._info

    async def generate(self, request: VideoGenerationRequest, *, context=None):
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        return await super().generate(request, context=context)


class ExplodingImageProvider(RecordingImageProvider):
    """Image provider that fails immediately for fail-fast tests."""

    async def generate(self, request: ImageGenerationRequest, *, context=None):
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        raise ProviderNotFoundError("image", self.info.name.lower())


class ExplodingTTSProvider(RecordingTTSProvider):
    """TTS provider that fails immediately for fail-fast tests."""

    async def generate(self, request: TTSGenerationRequest, *, context=None):
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        raise ProviderNotFoundError("voice", self.info.name.lower())


class ExplodingVideoProvider(RecordingVideoProvider):
    """Video provider that fails immediately for fail-fast tests."""

    async def generate(self, request: VideoGenerationRequest, *, context=None):
        self.calls += 1
        self.last_request = request.model_copy(deep=True)
        raise ProviderNotFoundError("video", self.info.name.lower())


def build_image_response(
    *,
    url: str = "https://example.invalid/generated.png?sig=secret",
    request_id: str = "req_img_service_123",
) -> ImagesResponse:
    """Create a minimal fake OpenAI image SDK response."""

    response = ImagesResponse.model_construct(
        created=1234567890,
        background="auto",
        data=[Image.model_construct(url=url, b64_json=None, revised_prompt="ignored")],
        output_format="png",
        quality="standard",
        size="1024x1024",
        usage=Usage.model_construct(
            input_tokens=1,
            input_tokens_details=None,
            output_tokens=2,
            total_tokens=3,
            output_tokens_details=None,
        ),
    )
    response._request_id = request_id
    return response


@dataclass
class FakeImagesClient:
    """Simple fake OpenAI image client."""

    response: object = field(default_factory=build_image_response)
    calls: list[dict[str, object]] = field(default_factory=list)

    async def generate(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return self.response


@dataclass
class FakeOpenAIImageClient:
    """Simple fake container exposing the images interface."""

    images: FakeImagesClient


class FakeBinaryResponse:
    """Simple fake OpenAI TTS binary response wrapper."""

    def __init__(self) -> None:
        self.response = httpx.Response(
            200,
            headers={"content-type": "audio/mpeg", "x-request-id": "req_tts_service_123"},
            content=b"fake-audio-bytes",
        )
        self._request_id = "req_tts_service_123"

    async def aread(self) -> bytes:
        return self.response.content


@dataclass
class FakeSpeechClient:
    """Simple fake OpenAI speech client."""

    response: object = field(default_factory=FakeBinaryResponse)
    calls: list[dict[str, object]] = field(default_factory=list)

    async def create(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return self.response


@dataclass
class FakeAudioClient:
    """Simple fake audio container exposing the speech interface."""

    speech: FakeSpeechClient


@dataclass
class FakeOpenAITTSClient:
    """Simple fake OpenAI TTS client container."""

    audio: FakeAudioClient


def build_package_request() -> MediaGenerationPackageRequest:
    """Create a bounded package request for happy-path tests."""

    return MediaGenerationPackageRequest(
        thumbnail_request=build_image_request("Thumbnail concept"),
        narration_request=build_tts_request("Narration track", "alloy"),
        scene_image_requests=(
            build_image_request("Scene image one"),
            build_image_request("Scene image two"),
        ),
        scene_video_requests=(build_video_request("Scene clip one"),),
    )


def test_service_accepts_provider_registry_and_settings() -> None:
    """The service should accept valid dependencies."""

    service = MediaGenerationService(create_provider_registry(), build_settings())

    assert isinstance(service, MediaGenerationService)


def test_invalid_dependencies_are_rejected_safely() -> None:
    """Invalid service dependencies should fail with typed validation errors."""

    with pytest.raises(CreatorOSValidationError):
        MediaGenerationService(object(), build_settings())  # type: ignore[arg-type]

    with pytest.raises(CreatorOSValidationError):
        MediaGenerationService(create_provider_registry(), object())  # type: ignore[arg-type]


def test_default_image_provider_is_resolved() -> None:
    """Image generation should use the configured default provider."""

    registry = create_provider_registry()
    provider = RecordingImageProvider(name="mock")
    registry.register(provider)
    service = MediaGenerationService(registry, build_settings(default_image_provider="mock"))

    result = run_async(service.generate_image(build_image_request()))

    assert isinstance(result, GeneratedImage)
    assert provider.calls == 1


def test_explicit_image_provider_overrides_default() -> None:
    """Explicit image provider names should override the default."""

    registry = create_provider_registry()
    default_provider = RecordingImageProvider(name="mock")
    alternate_provider = RecordingImageProvider(name="alternate")
    registry.register(default_provider)
    registry.register(alternate_provider)
    service = MediaGenerationService(registry, build_settings(default_image_provider="mock"))

    result = run_async(service.generate_image(build_image_request(), provider_name="alternate"))

    assert result.provider_name == "alternate"
    assert default_provider.calls == 0
    assert alternate_provider.calls == 1


def test_image_request_is_forwarded_unchanged() -> None:
    """Image requests should be forwarded without mutation."""

    registry = create_provider_registry()
    provider = RecordingImageProvider(name="mock")
    registry.register(provider)
    service = MediaGenerationService(registry, build_settings())
    request = build_image_request("Forward this image request")

    run_async(service.generate_image(request))

    assert provider.last_request == request


def test_unknown_image_provider_fails_safely() -> None:
    """Unknown image providers should raise the typed registry error."""

    service = create_media_generation_service(settings=build_settings())

    with pytest.raises(ProviderNotFoundError):
        run_async(service.generate_image(build_image_request(), provider_name="missing"))


def test_default_tts_provider_is_resolved() -> None:
    """Audio generation should use the configured default TTS provider."""

    registry = create_provider_registry()
    provider = RecordingTTSProvider(name="mock")
    registry.register(provider)
    service = MediaGenerationService(registry, build_settings(default_tts_provider="mock"))

    result = run_async(service.generate_audio(build_tts_request()))

    assert isinstance(result, GeneratedAudio)
    assert provider.calls == 1


def test_explicit_tts_provider_overrides_default() -> None:
    """Explicit TTS provider names should override the default."""

    registry = create_provider_registry()
    default_provider = RecordingTTSProvider(name="mock")
    alternate_provider = RecordingTTSProvider(name="alternate")
    registry.register(default_provider)
    registry.register(alternate_provider)
    service = MediaGenerationService(registry, build_settings(default_tts_provider="mock"))

    result = run_async(service.generate_audio(build_tts_request(), provider_name="alternate"))

    assert result.provider_name == "alternate"
    assert default_provider.calls == 0
    assert alternate_provider.calls == 1


def test_tts_request_is_forwarded_unchanged() -> None:
    """TTS requests should be forwarded without mutation."""

    registry = create_provider_registry()
    provider = RecordingTTSProvider(name="mock")
    registry.register(provider)
    service = MediaGenerationService(registry, build_settings())
    request = build_tts_request("Forward this narration request")

    run_async(service.generate_audio(request))

    assert provider.last_request == request


def test_unknown_tts_provider_fails_safely() -> None:
    """Unknown TTS providers should raise the typed registry error."""

    service = create_media_generation_service(settings=build_settings())

    with pytest.raises(ProviderNotFoundError):
        run_async(service.generate_audio(build_tts_request(), provider_name="missing"))


def test_default_video_provider_is_resolved() -> None:
    """Video generation should use the configured default video provider."""

    registry = create_provider_registry()
    provider = RecordingVideoProvider(name="mock")
    registry.register(provider)
    service = MediaGenerationService(registry, build_settings(default_video_provider="mock"))

    result = run_async(service.generate_video(build_video_request()))

    assert isinstance(result, GeneratedVideo)
    assert provider.calls == 1


def test_explicit_video_provider_override_works() -> None:
    """Explicit video provider names should override the default."""

    registry = create_provider_registry()
    default_provider = RecordingVideoProvider(name="mock")
    alternate_provider = RecordingVideoProvider(name="alternate")
    registry.register(default_provider)
    registry.register(alternate_provider)
    service = MediaGenerationService(registry, build_settings(default_video_provider="mock"))

    result = run_async(service.generate_video(build_video_request(), provider_name="alternate"))

    assert result.provider_name == "alternate"
    assert default_provider.calls == 0
    assert alternate_provider.calls == 1


def test_video_provider_remains_separate_from_render_provider() -> None:
    """Video generation should still use clip-generation providers, not render providers."""

    source = Path("creatoros/services/media_generation.py").read_text(encoding="utf-8")

    assert "RenderProvider" not in source
    assert "MediaRenderService" not in source
    assert ".render(" not in source


def test_valid_package_generation_succeeds_with_mocks() -> None:
    """The service should generate a full bounded media package offline with mocks."""

    service = create_media_generation_service(settings=build_settings())

    result = run_async(service.generate_package(build_package_request()))

    assert isinstance(result, GeneratedMediaPackage)
    assert result.thumbnail is not None
    assert result.narration is not None
    assert len(result.scene_images) == 2
    assert len(result.scene_videos) == 1
    assert isinstance(result.scene_images, tuple)
    assert isinstance(result.scene_videos, tuple)
    assert "ProviderResult" not in str(type(result))
    assert "openai" not in str(result.model_dump()).casefold()


def test_package_call_order_is_deterministic_and_bounded() -> None:
    """Package generation should call providers in a fixed bounded order."""

    order: list[str] = []

    class OrderedImageProvider(RecordingImageProvider):
        async def generate(self, request: ImageGenerationRequest, *, context=None):
            order.append(f"image:{request.prompt}")
            return await super().generate(request, context=context)

    class OrderedTTSProvider(RecordingTTSProvider):
        async def generate(self, request: TTSGenerationRequest, *, context=None):
            order.append(f"tts:{request.text}")
            return await super().generate(request, context=context)

    class OrderedVideoProvider(RecordingVideoProvider):
        async def generate(self, request: VideoGenerationRequest, *, context=None):
            order.append(f"video:{request.prompt}")
            return await super().generate(request, context=context)

    registry = create_provider_registry()
    image_provider = OrderedImageProvider(name="mock")
    tts_provider = OrderedTTSProvider(name="mock")
    video_provider = OrderedVideoProvider(name="mock")
    registry.register(image_provider)
    registry.register(tts_provider)
    registry.register(video_provider)
    service = MediaGenerationService(registry, build_settings())

    run_async(service.generate_package(build_package_request()))

    assert order == [
        "image:Thumbnail concept",
        "tts:Narration track",
        "image:Scene image one",
        "image:Scene image two",
        "video:Scene clip one",
    ]
    assert image_provider.calls == 3
    assert tts_provider.calls == 1
    assert video_provider.calls == 1


def test_empty_optional_scene_request_collections_are_supported() -> None:
    """Package generation should support missing optional scene requests."""

    service = create_media_generation_service(settings=build_settings())
    request = MediaGenerationPackageRequest(
        thumbnail_request=build_image_request("Only thumbnail"),
        narration_request=build_tts_request("Only narration"),
    )

    result = run_async(service.generate_package(request))

    assert result.thumbnail is not None
    assert result.narration is not None
    assert result.scene_images == ()
    assert result.scene_videos == ()


def test_mutable_defaults_are_isolated() -> None:
    """Package request and result collections should not share mutable state."""

    original_scene_requests = [build_image_request("One")]
    first = MediaGenerationPackageRequest(
        thumbnail_request=build_image_request(),
        scene_image_requests=original_scene_requests,
    )
    second = MediaGenerationPackageRequest(
        narration_request=build_tts_request(),
    )
    original_scene_requests[0].prompt = "Mutated prompt"

    assert second.scene_image_requests == ()
    assert first.scene_image_requests[0].prompt == "One"


def test_generator_style_input_is_normalized_safely() -> None:
    """Generator-style bounded inputs should normalize into immutable tuples."""

    request = MediaGenerationPackageRequest(
        thumbnail_request=build_image_request(),
        scene_image_requests=(build_image_request(f"Scene {index}") for index in range(2)),
    )

    assert isinstance(request.scene_image_requests, tuple)
    assert len(request.scene_image_requests) == 2


def test_package_provider_selection_overrides_are_supported() -> None:
    """Package generation should support per-capability provider overrides."""

    registry = create_provider_registry()
    default_image_provider = RecordingImageProvider(name="mock")
    alternate_image_provider = RecordingImageProvider(name="image-alt")
    default_tts_provider = RecordingTTSProvider(name="mock")
    alternate_tts_provider = RecordingTTSProvider(name="tts-alt")
    default_video_provider = RecordingVideoProvider(name="mock")
    alternate_video_provider = RecordingVideoProvider(name="video-alt")
    registry.register(default_image_provider)
    registry.register(alternate_image_provider)
    registry.register(default_tts_provider)
    registry.register(alternate_tts_provider)
    registry.register(default_video_provider)
    registry.register(alternate_video_provider)
    service = MediaGenerationService(registry, build_settings())
    request = MediaGenerationPackageRequest(
        thumbnail_request=build_image_request("Thumbnail override"),
        narration_request=build_tts_request("Narration override", "alloy"),
        scene_video_requests=(build_video_request("Video override"),),
        provider_selection=MediaProviderSelection(
            image_provider_name="image-alt",
            tts_provider_name="tts-alt",
            video_provider_name="video-alt",
        ),
    )

    result = run_async(service.generate_package(request))

    assert result.thumbnail is not None and result.thumbnail.provider_name == "image-alt"
    assert result.narration is not None and result.narration.provider_name == "tts-alt"
    assert result.scene_videos[0].provider_name == "video-alt"
    assert default_image_provider.calls == 0
    assert default_tts_provider.calls == 0
    assert default_video_provider.calls == 0


def test_image_failure_stops_later_required_generation() -> None:
    """A thumbnail-image failure should stop later package generation immediately."""

    registry = create_provider_registry()
    image_provider = ExplodingImageProvider(name="mock")
    tts_provider = RecordingTTSProvider(name="mock")
    video_provider = RecordingVideoProvider(name="mock")
    registry.register(image_provider)
    registry.register(tts_provider)
    registry.register(video_provider)
    service = MediaGenerationService(registry, build_settings())

    with pytest.raises(ProviderNotFoundError):
        run_async(service.generate_package(build_package_request()))

    assert image_provider.calls == 1
    assert tts_provider.calls == 0
    assert video_provider.calls == 0


def test_tts_failure_stops_downstream_calls() -> None:
    """A narration failure should stop subsequent scene generation."""

    registry = create_provider_registry()
    image_provider = RecordingImageProvider(name="mock")
    tts_provider = ExplodingTTSProvider(name="mock")
    video_provider = RecordingVideoProvider(name="mock")
    registry.register(image_provider)
    registry.register(tts_provider)
    registry.register(video_provider)
    service = MediaGenerationService(registry, build_settings())

    with pytest.raises(ProviderNotFoundError):
        run_async(service.generate_package(build_package_request()))

    assert image_provider.calls == 1
    assert tts_provider.calls == 1
    assert video_provider.calls == 0


def test_video_failure_preserves_original_provider_error() -> None:
    """A video-generation failure should surface the original provider error."""

    registry = create_provider_registry()
    image_provider = RecordingImageProvider(name="mock")
    tts_provider = RecordingTTSProvider(name="mock")
    video_provider = ExplodingVideoProvider(name="mock")
    registry.register(image_provider)
    registry.register(tts_provider)
    registry.register(video_provider)
    service = MediaGenerationService(registry, build_settings())

    with pytest.raises(ProviderNotFoundError) as exc_info:
        run_async(service.generate_package(build_package_request()))

    assert exc_info.value.details == {"provider_type": "video", "provider_name": "mock"}


def test_fake_openai_image_adapter_works_through_service() -> None:
    """The service should remain provider-independent for image generation."""

    registry = create_provider_registry()
    image_client = FakeOpenAIImageClient(FakeImagesClient())
    registry.register(
        OpenAIImageProvider(
            client=image_client,
            api_key=None,
            default_model="gpt-image-1",
            timeout_seconds=30.0,
            max_retries=0,
        )
    )
    service = MediaGenerationService(
        registry,
        build_settings(default_image_provider="openai-image"),
    )

    result = run_async(service.generate_image(build_image_request("OpenAI image path")))

    assert isinstance(result, GeneratedImage)
    assert result.provider_name == "openai-image"
    assert image_client.images.calls[0]["prompt"] == "OpenAI image path"


def test_fake_openai_tts_adapter_works_through_service() -> None:
    """The service should remain provider-independent for TTS generation."""

    registry = create_provider_registry()
    tts_client = FakeOpenAITTSClient(FakeAudioClient(FakeSpeechClient()))
    registry.register(
        OpenAITTSProvider(
            client=tts_client,
            api_key=None,
            default_model="gpt-4o-mini-tts",
            timeout_seconds=30.0,
            max_retries=0,
        )
    )
    service = MediaGenerationService(
        registry,
        build_settings(default_tts_provider="openai-tts"),
    )

    result = run_async(service.generate_audio(build_tts_request("OpenAI narration path", "alloy")))

    assert isinstance(result, GeneratedAudio)
    assert result.provider_name == "openai-tts"
    assert tts_client.audio.speech.calls[0]["input"] == "OpenAI narration path"


def test_factory_builds_safe_mock_first_service() -> None:
    """The service factory should create a safe mock-first registry."""

    service = create_media_generation_service(settings=build_settings())

    assert service.provider_registry.contains("image", "mock") is True
    assert service.provider_registry.contains("voice", "mock") is True
    assert service.provider_registry.contains("video", "mock") is True


def test_service_source_contains_no_forbidden_boundaries_or_file_writes() -> None:
    """The service module should stay generation-only and avoid materialization."""

    source = Path("creatoros/services/media_generation.py").read_text(encoding="utf-8")

    assert "GamingMediaAgent" not in source
    assert "LLMExecutionService" not in source
    assert "PromptRegistry" not in source
    assert "ParserRegistry" not in source
    assert "MediaRenderService" not in source
    assert "RenderProvider" not in source
    assert "publish" not in source
    assert "ffmpeg" not in source.lower()
    assert "moviepy" not in source.lower()
    assert "open(" not in source
    assert "write_text" not in source
