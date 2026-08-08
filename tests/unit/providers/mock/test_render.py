"""Unit tests for the CreatorOS mock render provider."""

from __future__ import annotations

import asyncio
from pathlib import Path

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import GeneratedAudio, RenderedVideo, RenderProvider, ShortRenderRequest
from creatoros.providers.mock import MockRenderProvider
from creatoros.providers.render import RenderScene


def build_request() -> ShortRenderRequest:
    """Create a deterministic render request for mock-provider tests."""

    return ShortRenderRequest(
        scenes=[
            RenderScene(
                scene_number=1,
                duration_seconds=3.0,
                visual_asset_ref=GeneratedAsset(
                    asset_type=AssetType.IMAGE,
                    uri="mock://generated/image/1.png",
                ),
                caption_text=" Myth one ",
            ),
            RenderScene(
                scene_number=2,
                duration_seconds=4.0,
                video_asset_ref=GeneratedAsset(
                    asset_type=AssetType.VIDEO,
                    uri="mock://generated/video/2.mp4",
                ),
                transition="fade",
            ),
        ],
        narration=GeneratedAudio(
            artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/narration.wav"),
            provider_name="mock",
            model="mock-tts-model",
            mime_type="audio/wav",
            estimated_duration_seconds=7.0,
        ),
        fps=30.0,
    )


def test_mock_render_provider_returns_rendered_video() -> None:
    """Mock render should return a typed rendered-video result."""

    result = asyncio.run(MockRenderProvider().render(build_request()))

    assert isinstance(result.data, RenderedVideo)
    assert result.data.artifact.asset_type is AssetType.VIDEO
    assert result.data.artifact.uri.startswith("mock://rendered/video/")


def test_same_request_produces_same_artifact_reference() -> None:
    """Mock render should be deterministic for identical requests."""

    provider = MockRenderProvider()
    first = asyncio.run(provider.render(build_request()))
    second = asyncio.run(provider.render(build_request()))

    assert first.data.artifact.uri == second.data.artifact.uri
    assert first.request_id == second.request_id


def test_mock_render_preserves_duration_dimensions_and_fps() -> None:
    """Mock render should preserve safe timeline and format fields."""

    request = build_request()
    result = asyncio.run(MockRenderProvider().render(request))

    assert result.data.duration_seconds == request.total_duration_seconds
    assert result.data.width == request.width
    assert result.data.height == request.height
    assert result.data.fps == request.fps


def test_mock_render_provider_satisfies_runtime_protocol() -> None:
    """Mock render provider should satisfy the render protocol."""

    assert isinstance(MockRenderProvider(), RenderProvider)


def test_mock_render_creates_no_local_files() -> None:
    """Mock render should not create local files while composing results."""

    temp_dir = Path("tests/unit/providers/mock")
    before = tuple(temp_dir.iterdir())

    asyncio.run(MockRenderProvider().render(build_request()))

    assert tuple(temp_dir.iterdir()) == before


def test_mock_render_module_contains_no_network_or_ffmpeg_or_moviepy_usage() -> None:
    """The mock render module should stay offline and avoid real rendering tools."""

    module_source = Path("creatoros/providers/mock/render.py").read_text(encoding="utf-8")

    assert "httpx" not in module_source
    assert "requests" not in module_source
    assert "subprocess" not in module_source
    assert "ffmpeg" not in module_source.lower()
    assert "moviepy" not in module_source.lower()
