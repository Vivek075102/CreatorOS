"""Deterministic mock media providers for CreatorOS."""

from __future__ import annotations

import hashlib

from creatoros.core import CreatorOSValidationError
from creatoros.domain import AssetType, GeneratedAsset, NarrationTrack
from creatoros.providers.base import (
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.media import (
    GeneratedAudio,
    GeneratedImage,
    GeneratedVideo,
    ImageGenerationRequest,
    TTSGenerationRequest,
    VideoGenerationRequest,
)
from creatoros.providers.mock.base import MockProviderBase

MOCK_IMAGE_MODEL = "mock-image-model"
MOCK_TTS_MODEL = "mock-tts-model"
MOCK_VIDEO_MODEL = "mock-video-model"
_MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01H\xaf\xa4q"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
_MINIMAL_WAV_BYTES = (
    b"RIFF(\x00\x00\x00WAVEfmt "
    b"\x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00"
    b"\x01\x00\x08\x00data\x04\x00\x00\x00\x80\x80\x80\x80"
)


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name},
        )
    return normalized_value


def _zero_cost_usage() -> ProviderUsage:
    """Return deterministic zero-cost usage metadata."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


def _build_digest(parts: tuple[object, ...]) -> str:
    """Create one stable mock artifact digest from provider-neutral request fields."""

    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _estimate_mock_audio_duration_seconds(text: str) -> float:
    """Return a deterministic mock duration estimate for compatibility-only narration output."""

    word_count = max(len(text.split()), 1)
    return round(max(word_count / 2.5, 1.0), 2)


class MockImageProvider(MockProviderBase):
    """Deterministic mock image provider using provider-neutral request contracts."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="image",
            capabilities={ProviderCapability.IMAGE_GENERATION},
            is_healthy=is_healthy,
        )

    async def generate(
        self,
        request: ImageGenerationRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedImage]:
        """Return one deterministic mock image result without network or files."""

        del context
        digest = _build_digest(
            (
                request.prompt,
                request.width,
                request.height,
                request.negative_prompt,
                request.seed,
            )
        )
        artifact = GeneratedAsset(
            asset_type=AssetType.IMAGE,
            uri=f"mock://generated/image/{digest}.png",
            metadata={"mock_artifact_id": digest},
        )
        result = GeneratedImage(
            artifact=artifact,
            provider_name=self.info.name,
            model=MOCK_IMAGE_MODEL,
            mime_type="image/png",
            width=request.width,
            height=request.height,
            request_id=f"mock_image_request_{digest}",
            metadata={"mock": True},
            payload_bytes=_MINIMAL_PNG_BYTES,
        )
        return ProviderResult[GeneratedImage](
            data=result,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=result.request_id,
        )

    async def generate_image(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Return the legacy demo-compatible image asset contract."""

        request = ImageGenerationRequest(prompt=_validate_non_blank(prompt, field_name="prompt"))
        result = await self.generate(request, context=context)
        return ProviderResult[GeneratedAsset](
            data=result.data.artifact.model_copy(deep=True),
            provider=self.info,
            usage=result.usage.model_copy(deep=True) if result.usage is not None else None,
            request_id=result.request_id,
            metadata={"mock": True},
        )


class MockVideoProvider(MockProviderBase):
    """Deterministic mock video provider using provider-neutral request contracts."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="video",
            capabilities={ProviderCapability.VIDEO_GENERATION},
            is_healthy=is_healthy,
        )

    async def generate(
        self,
        request: VideoGenerationRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedVideo]:
        """Return one deterministic mock video result without rendering or FFmpeg."""

        del context
        digest = _build_digest(
            (
                request.prompt,
                request.duration_seconds,
                request.width,
                request.height,
                request.fps,
                request.negative_prompt,
                request.seed,
            )
        )
        artifact = GeneratedAsset(
            asset_type=AssetType.VIDEO,
            uri=f"mock://generated/video/{digest}.mp4",
            metadata={"mock_artifact_id": digest},
        )
        result = GeneratedVideo(
            artifact=artifact,
            provider_name=self.info.name,
            model=MOCK_VIDEO_MODEL,
            mime_type="video/mp4",
            duration_seconds=request.duration_seconds,
            width=request.width,
            height=request.height,
            fps=request.fps,
            request_id=f"mock_video_request_{digest}",
            metadata={"mock": True},
        )
        return ProviderResult[GeneratedVideo](
            data=result,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=result.request_id,
        )

    async def generate_video(
        self,
        prompt: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAsset]:
        """Return the legacy demo-compatible video asset contract."""

        request = VideoGenerationRequest(
            prompt=_validate_non_blank(prompt, field_name="prompt"),
            duration_seconds=6.0,
        )
        result = await self.generate(request, context=context)
        return ProviderResult[GeneratedAsset](
            data=result.data.artifact.model_copy(deep=True),
            provider=self.info,
            usage=result.usage.model_copy(deep=True) if result.usage is not None else None,
            request_id=result.request_id,
            metadata={"mock": True},
        )


class MockTTSProvider(MockProviderBase):
    """Deterministic mock TTS provider using provider-neutral request contracts."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="voice",
            capabilities={ProviderCapability.VOICE_GENERATION},
            is_healthy=is_healthy,
        )

    async def generate(
        self,
        request: TTSGenerationRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[GeneratedAudio]:
        """Return one deterministic mock audio result without speech synthesis."""

        del context
        digest = _build_digest(
            (
                request.text,
                request.voice,
                request.language,
                request.speed,
            )
        )
        estimated_duration_seconds = _estimate_mock_audio_duration_seconds(request.text)
        artifact = GeneratedAsset(
            asset_type=AssetType.AUDIO,
            uri=f"mock://generated/audio/{digest}.wav",
            metadata={"mock_artifact_id": digest},
        )
        result = GeneratedAudio(
            artifact=artifact,
            provider_name=self.info.name,
            model=MOCK_TTS_MODEL,
            mime_type="audio/wav",
            voice=request.voice,
            language=request.language,
            estimated_duration_seconds=estimated_duration_seconds,
            request_id=f"mock_tts_request_{digest}",
            metadata={"mock": True, "duration_is_estimated": True},
            payload_bytes=_MINIMAL_WAV_BYTES,
        )
        return ProviderResult[GeneratedAudio](
            data=result,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=result.request_id,
        )

    async def generate_voice(
        self,
        text: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[NarrationTrack]:
        """Return the legacy demo-compatible narration contract."""

        request = TTSGenerationRequest(text=_validate_non_blank(text, field_name="text"))
        result = await self.generate(request, context=context)
        estimated_duration_seconds = result.data.estimated_duration_seconds
        assert estimated_duration_seconds is not None
        narration = NarrationTrack(
            uri=result.data.artifact.uri,
            duration_seconds=estimated_duration_seconds,
            metadata={
                "mock": True,
                "duration_is_estimated": True,
                "provider_name": result.data.provider_name,
                "model": result.data.model,
            },
        )
        return ProviderResult[NarrationTrack](
            data=narration,
            provider=self.info,
            usage=result.usage.model_copy(deep=True) if result.usage is not None else None,
            request_id=result.request_id,
            metadata={"mock": True},
        )


class MockVoiceProvider(MockTTSProvider):
    """Backward-compatible alias for the deterministic mock TTS provider."""


__all__ = [
    "MockImageProvider",
    "MockTTSProvider",
    "MockVideoProvider",
    "MockVoiceProvider",
]
