"""Unit tests for the CreatorOS FFmpeg render provider."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from creatoros.config import Settings
from creatoros.core import (
    ArtifactAlreadyExistsError,
    ArtifactPathError,
    ProviderNotFoundError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import (
    DEFAULT_FFMPEG_RENDER_PROVIDER_NAME,
    GeneratedAudio,
    ProductionTimeline,
    ProductionTimelineScene,
    ProviderCapability,
    ProviderRequestContext,
    RenderProvider,
    ShortRenderRequest,
    create_provider_registry,
    register_ffmpeg_render_provider,
    resolve_default_render_provider,
    resolve_ffmpeg_binary,
)
from creatoros.providers.ffmpeg import FFmpegCommandResult, FFmpegRenderProvider
from creatoros.providers.mock import MockRenderProvider
from creatoros.providers.render import RenderScene

_USE_DEFAULT_NARRATION_DURATION = object()


def build_settings(
    *,
    artifact_root: Path,
    ffmpeg_path: Path | None = None,
    default_render_provider: str = "mock",
) -> Settings:
    """Create isolated settings for FFmpeg provider registration tests."""

    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider="mock",
        default_llm_model="mock-model",
        default_image_provider="mock",
        default_image_model=None,
        default_tts_provider="mock",
        default_tts_model=None,
        default_video_provider="mock",
        default_render_provider=default_render_provider,
        openai_api_key=None,
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        provider_max_retries=3,
        ffmpeg_path=ffmpeg_path,
        caption_font_name="Arial",
        caption_font_file=None,
        artifact_root=artifact_root,
        assets_dir=artifact_root.parent / "assets",
        logs_dir=artifact_root.parent / "logs",
        prompts_dir=artifact_root.parent / "prompts",
    )


def create_workspace_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create one artifact workspace with local image, video, and narration files."""

    artifact_root = (tmp_path / "artifacts").resolve()
    workspace_dir = artifact_root / "run_001"
    images_dir = workspace_dir / "images"
    audio_dir = workspace_dir / "audio"
    video_dir = workspace_dir / "video"
    images_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    image_path = images_dir / "scene_001.png"
    image_path.write_bytes(b"png-bytes")
    video_path = video_dir / "clip_001.mp4"
    video_path.write_bytes(b"video-bytes")
    narration_path = audio_dir / "narration.wav"
    narration_path.write_bytes(b"audio-bytes")
    return artifact_root, image_path, video_path, narration_path


def build_request(
    *,
    image_path: Path,
    video_path: Path | None = None,
    narration_path: Path | None = None,
    narration_duration: float | None | object = _USE_DEFAULT_NARRATION_DURATION,
    caption_text: str | None = "CreatorOS caption",
) -> ShortRenderRequest:
    """Create a local-file-backed render request for FFmpeg tests."""

    scenes = [
        RenderScene(
            scene_number=1,
            duration_seconds=2.0,
            visual_asset_ref=GeneratedAsset(asset_type=AssetType.IMAGE, uri=str(image_path)),
            caption_text=caption_text,
        )
    ]
    if video_path is not None:
        scenes.append(
            RenderScene(
                scene_number=2,
                duration_seconds=3.0,
                video_asset_ref=GeneratedAsset(asset_type=AssetType.VIDEO, uri=str(video_path)),
                caption_text="Second caption",
            )
        )

    narration = None
    if narration_path is not None:
        narration = GeneratedAudio(
            artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri=str(narration_path)),
            provider_name="mock",
            model="mock-tts-model",
            mime_type="audio/wav",
            estimated_duration_seconds=(
                5.0 if video_path is not None else 2.0
                if narration_duration is _USE_DEFAULT_NARRATION_DURATION
                else narration_duration
            ),
        )

    return ShortRenderRequest(
        scenes=scenes,
        narration=narration,
        width=1080,
        height=1920,
        fps=30.0,
    )


@dataclass
class RecordingFFmpegRunner:
    """Fake FFmpeg runner that records argv calls and writes fake outputs."""

    fail_at_call: int | None = None
    timeout_at_call: int | None = None
    error_at_call: int | None = None
    write_empty_output_at_call: int | None = None
    calls: list[tuple[str, ...]] = field(default_factory=list)
    timeouts: list[float | None] = field(default_factory=list)
    concat_file_contents: list[str] = field(default_factory=list)
    subtitle_file_contents: list[str] = field(default_factory=list)
    final_filters: list[str] = field(default_factory=list)
    filter_complex_values: list[str] = field(default_factory=list)

    async def __call__(
        self,
        argv: tuple[str, ...],
        timeout_seconds: float | None,
    ) -> FFmpegCommandResult:
        self.calls.append(argv)
        self.timeouts.append(timeout_seconds)
        call_index = len(self.calls)

        if "-f" in argv and "concat" in argv:
            concat_path = Path(argv[argv.index("-i") + 1])
            self.concat_file_contents.append(concat_path.read_text(encoding="utf-8"))
            captions_path = concat_path.parent / "captions.ass"
            if captions_path.exists():
                self.subtitle_file_contents.append(captions_path.read_text(encoding="utf-8"))

        if "-vf" in argv:
            self.final_filters.append(argv[argv.index("-vf") + 1])
        if "-filter_complex" in argv:
            self.filter_complex_values.append(argv[argv.index("-filter_complex") + 1])

        if self.timeout_at_call == call_index:
            raise TimeoutError("timed out")
        if self.error_at_call == call_index:
            raise OSError("binary failed to start")

        output_path = Path(argv[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.write_empty_output_at_call == call_index:
            output_path.write_bytes(b"")
        elif self.fail_at_call != call_index:
            output_path.write_bytes(f"output-{call_index}".encode())

        exit_code = 1 if self.fail_at_call == call_index else 0
        return FFmpegCommandResult(exit_code=exit_code, stderr="simulated stderr")


def build_provider(
    *,
    artifact_root: Path,
    ffmpeg_path: Path,
    command_runner: RecordingFFmpegRunner | None = None,
    timeout_seconds: float = 30.0,
) -> FFmpegRenderProvider:
    """Create an FFmpeg provider with explicit local test defaults."""

    return FFmpegRenderProvider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_path,
        command_runner=command_runner,
        timeout_seconds=timeout_seconds,
    )


def run_async(coro):
    """Run one provider coroutine without async pytest plugins."""

    return asyncio.run(coro)


def test_ffmpeg_provider_satisfies_runtime_render_protocol(tmp_path: Path) -> None:
    """The local FFmpeg provider should satisfy the runtime render protocol."""

    artifact_root, _image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary)

    assert isinstance(provider, RenderProvider)


def test_provider_identity_is_ffmpeg_render_without_credentials(tmp_path: Path) -> None:
    """Provider metadata should expose only local render identity."""

    artifact_root, _image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary)

    assert provider.info.name == DEFAULT_FFMPEG_RENDER_PROVIDER_NAME
    assert provider.info.provider_type == "render"
    assert provider.info.capabilities == {ProviderCapability.RENDERING}
    assert "ffmpeg_path" not in provider.info.metadata


def test_configured_ffmpeg_path_is_preferred() -> None:
    """Explicit configured FFmpeg paths should be returned directly."""

    configured_path = Path("C:/tools/ffmpeg/bin/ffmpeg.exe")

    assert resolve_ffmpeg_binary(configured_path) == configured_path.resolve()


def test_path_discovery_uses_shutil_which(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """PATH-based discovery should use shutil.which when no explicit path is configured."""

    discovered_binary = tmp_path / "ffmpeg.exe"
    discovered_binary.write_text("binary", encoding="utf-8")
    monkeypatch.setattr("creatoros.providers.ffmpeg.render.shutil.which", lambda name: str(discovered_binary))

    assert resolve_ffmpeg_binary() == discovered_binary.resolve()


def test_unavailable_ffmpeg_fails_safely(tmp_path: Path) -> None:
    """Missing FFmpeg discovery should fail with a typed provider error."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=tmp_path / "missing_ffmpeg.exe",
        command_runner=RecordingFFmpegRunner(),
    )

    with pytest.raises(ProviderUnavailableError):
        run_async(provider.render(build_request(image_path=image_path)))


def test_registration_makes_no_subprocess_call_and_keeps_mock_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit FFmpeg registration should avoid discovery side effects and preserve mock default."""

    artifact_root, _image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    registry = create_provider_registry()
    registry.register(MockRenderProvider())

    stub_settings = SimpleNamespace(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        provider_timeout_seconds=30.0,
        default_render_provider="mock",
    )
    monkeypatch.setattr("creatoros.providers.ffmpeg.bootstrap.get_settings", lambda: stub_settings)
    monkeypatch.setattr("creatoros.providers.registry.get_settings", lambda: stub_settings)
    provider = register_ffmpeg_render_provider(registry)

    assert provider is registry.get("render", "ffmpeg")
    assert resolve_default_render_provider(registry).info.name == "mock"


def test_missing_input_path_is_rejected(tmp_path: Path) -> None:
    """Missing local input paths should fail before any runner call."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    image_path.unlink()
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    with pytest.raises(ArtifactPathError):
        run_async(provider.render(build_request(image_path=image_path)))

    assert runner.calls == []


def test_non_local_input_uri_is_rejected(tmp_path: Path) -> None:
    """Provider-owned or remote URIs should not reach FFmpeg."""

    artifact_root, _image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=RecordingFFmpegRunner())
    request = ShortRenderRequest(
        scenes=[
            RenderScene(
                scene_number=1,
                duration_seconds=2.0,
                visual_asset_ref=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/example.png"),
            )
        ]
    )

    with pytest.raises(ArtifactPathError):
        run_async(provider.render(request))


def test_outside_root_input_path_is_rejected(tmp_path: Path) -> None:
    """Local files outside the configured artifact root should be rejected safely."""

    artifact_root, _image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    outside_file = tmp_path / "outside.png"
    outside_file.write_bytes(b"outside")
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=RecordingFFmpegRunner())

    with pytest.raises(ArtifactPathError):
        run_async(provider.render(build_request(image_path=outside_file)))


def test_output_path_remains_inside_workspace_video_directory(tmp_path: Path) -> None:
    """Successful renders should write the final MP4 into the workspace video directory."""

    artifact_root, image_path, _video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(),
    )

    result = run_async(provider.render(build_request(image_path=image_path, narration_path=narration_path)))

    assert result.data.artifact.uri == str(artifact_root / "run_001" / "video" / "final_short.mp4")


def test_image_scene_command_uses_loop_duration_filter_and_separate_argv(tmp_path: Path) -> None:
    """Static image scenes should render through looped deterministic segment commands."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path)))

    first_call = runner.calls[0]
    assert first_call[0] == str(ffmpeg_binary)
    assert "-loop" in first_call
    assert "1" in first_call
    assert "-t" in first_call and "2" in first_call
    assert "-r" in first_call and "30" in first_call
    assert "-vf" in first_call
    assert "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1" in first_call
    assert str(image_path) in first_call


def test_video_scene_command_normalizes_video_without_looping(tmp_path: Path) -> None:
    """Video scenes should normalize duration, FPS, and dimensions without image looping flags."""

    artifact_root, image_path, video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path, video_path=video_path)))

    second_call = runner.calls[1]
    assert "-loop" not in second_call
    assert str(video_path) in second_call
    assert "-t" in second_call and "3" in second_call
    assert "-r" in second_call and "30" in second_call
    assert "-vf" in second_call


def test_concat_preserves_scene_order_and_uses_controlled_intermediates(tmp_path: Path) -> None:
    """Intermediate scene ordering should remain deterministic through concat composition."""

    artifact_root, image_path, video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path, video_path=video_path, narration_path=narration_path)))

    concat_contents = runner.concat_file_contents[0]
    assert "scene_001.mp4" in concat_contents
    assert "scene_002.mp4" in concat_contents
    assert concat_contents.index("scene_001.mp4") < concat_contents.index("scene_002.mp4")


def test_narration_is_added_when_present_and_not_looped(tmp_path: Path) -> None:
    """Narration should be muxed once when present and omitted otherwise."""

    artifact_root, image_path, _video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path, narration_path=narration_path)))

    final_call = runner.calls[-1]
    assert str(narration_path) in final_call
    assert "-filter_complex" in final_call
    assert "-t" in final_call and "2" in final_call
    assert "-stream_loop" not in final_call


def test_narration_is_omitted_when_absent(tmp_path: Path) -> None:
    """Final composition should not inject narration flags when no narration exists."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path)))

    final_call = runner.calls[-1]
    assert "-shortest" not in final_call
    assert "-an" in final_call


def test_no_caption_request_preserves_existing_final_command_path(tmp_path: Path) -> None:
    """Final composition should not add subtitle filtering when scenes have no captions."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path, caption_text=None)))

    final_call = runner.calls[-1]
    assert "-vf" not in final_call
    assert runner.subtitle_file_contents == []


def test_caption_request_adds_subtitle_filter_and_deterministic_ass_file(tmp_path: Path) -> None:
    """Captioned renders should add one ASS subtitle filter at final composition time."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path, caption_text="Roblox: Funny Myths")))

    final_call = runner.calls[-1]
    assert "-vf" in final_call
    assert runner.final_filters[-1].startswith("subtitles='")
    assert "fontsdir=" not in runner.final_filters[-1]
    assert runner.subtitle_file_contents
    assert "PlayResX: 1080" in runner.subtitle_file_contents[-1]
    assert r"{\an2}Roblox: Funny Myths" in runner.subtitle_file_contents[-1]


def test_caption_filter_and_narration_can_coexist(tmp_path: Path) -> None:
    """Caption overlays should coexist with optional narration muxing."""

    artifact_root, image_path, _video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(
        provider.render(
            build_request(
                image_path=image_path,
                narration_path=narration_path,
                caption_text="CreatorOS caption test",
            )
        )
    )

    final_call = runner.calls[-1]
    concat_input_flag_index = final_call.index("-i")
    narration_input_flag_index = final_call.index("-i", concat_input_flag_index + 1)
    vf_index = final_call.index("-vf")
    filter_complex_index = final_call.index("-filter_complex")

    assert final_call[concat_input_flag_index + 1].endswith("concat_list.txt")
    assert final_call[narration_input_flag_index + 1] == str(narration_path)
    assert concat_input_flag_index < narration_input_flag_index
    assert narration_input_flag_index < vf_index
    assert narration_input_flag_index < filter_complex_index
    assert "-vf" in final_call
    assert str(narration_path) in final_call
    assert "-filter_complex" in final_call
    assert "0:v:0" in final_call
    assert "[narration_out]" in final_call


def test_narration_audio_is_normalized_to_aac_48khz_stereo(tmp_path: Path) -> None:
    """Narration should be normalized to a deterministic output audio policy."""

    artifact_root, image_path, _video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path, narration_path=narration_path)))

    final_call = runner.calls[-1]
    assert "-c:a" in final_call and "aac" in final_call
    assert "-ar" in final_call and "48000" in final_call
    assert "-ac" in final_call and "2" in final_call
    assert "-b:a" in final_call and "192k" in final_call


def test_shorter_narration_uses_silence_padding_without_looping(tmp_path: Path) -> None:
    """Short narration should be padded with silence to match the video timeline."""

    artifact_root, image_path, video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(
        provider.render(
            build_request(
                image_path=image_path,
                video_path=video_path,
                narration_path=narration_path,
                narration_duration=2.5,
            )
        )
    )

    filter_complex = runner.filter_complex_values[-1]
    final_call = runner.calls[-1]
    assert "apad" in filter_complex
    assert "atrim=duration=5" in filter_complex
    assert "-stream_loop" not in final_call


def test_longer_narration_is_trimmed_to_video_timeline(tmp_path: Path) -> None:
    """Long narration should be trimmed to the authoritative video duration."""

    artifact_root, image_path, video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(
        provider.render(
            build_request(
                image_path=image_path,
                video_path=video_path,
                narration_path=narration_path,
                narration_duration=5.5,
            )
        )
    )

    filter_complex = runner.filter_complex_values[-1]
    final_call = runner.calls[-1]
    assert "atrim=duration=5" in filter_complex
    assert "-t" in final_call and "5" in final_call


def test_unknown_narration_duration_remains_accepted_without_fake_values(tmp_path: Path) -> None:
    """Missing narration duration metadata should still use the bounded audio path."""

    artifact_root, image_path, _video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(
        provider.render(
            build_request(
                image_path=image_path,
                narration_path=narration_path,
                narration_duration=None,
            )
        )
    )

    assert runner.filter_complex_values[-1] == (
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration=2[narration_out]"
    )


def test_caption_filter_preserves_multiple_scene_order(tmp_path: Path) -> None:
    """Multiple captioned scenes should remain ordered in the ASS subtitle timeline."""

    artifact_root, image_path, video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    run_async(provider.render(build_request(image_path=image_path, video_path=video_path)))

    subtitle_contents = runner.subtitle_file_contents[-1]
    assert "0:00:00.00,0:00:02.00" in subtitle_contents
    assert "0:00:02.00,0:00:05.00" in subtitle_contents
    assert subtitle_contents.index("CreatorOS caption") < subtitle_contents.index("Second caption")


def test_ffmpeg_render_uses_explicit_production_timeline_when_supplied(tmp_path: Path) -> None:
    """Explicit production timeline timing should drive segment and caption timing."""

    artifact_root, image_path, video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner()
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)
    request = build_request(image_path=image_path, video_path=video_path)
    request.production_timeline = ProductionTimeline(
        scenes=[
            ProductionTimelineScene(
                scene_number=1,
                start_seconds=0.0,
                end_seconds=1.25,
                duration_seconds=1.25,
                source_asset_ref=GeneratedAsset(asset_type=AssetType.IMAGE, uri=str(image_path)),
                caption_text="CreatorOS caption",
            ),
            ProductionTimelineScene(
                scene_number=2,
                start_seconds=1.25,
                end_seconds=5.0,
                duration_seconds=3.75,
                source_asset_ref=GeneratedAsset(asset_type=AssetType.VIDEO, uri=str(video_path)),
                caption_text="Second caption",
            ),
        ],
        target_duration_seconds=5.0,
    )

    run_async(provider.render(request))

    first_scene_call = runner.calls[0]
    second_scene_call = runner.calls[1]
    subtitle_contents = runner.subtitle_file_contents[-1]
    assert "-t" in first_scene_call and "1.25" in first_scene_call
    assert "-t" in second_scene_call and "3.75" in second_scene_call
    assert "0:00:00.00,0:00:01.25" in subtitle_contents
    assert "0:00:01.25,0:00:05.00" in subtitle_contents


def test_invalid_caption_font_file_fails_safely_before_final_render(tmp_path: Path) -> None:
    """Missing configured caption font files should fail with a safe provider error."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(),
    )
    provider.caption_font_file = tmp_path / "missing_font.ttf"

    with pytest.raises(ProviderUnavailableError) as exc_info:
        run_async(provider.render(build_request(image_path=image_path)))

    assert exc_info.value.code == "provider_invalid_configuration"


def test_successful_render_returns_local_rendered_video(tmp_path: Path) -> None:
    """A successful fake render should return a typed local rendered-video result."""

    artifact_root, image_path, video_path, narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(),
    )

    result = run_async(provider.render(build_request(image_path=image_path, video_path=video_path, narration_path=narration_path)))

    assert result.data.provider_name == "ffmpeg"
    assert result.data.mime_type == "video/mp4"
    assert result.data.width == 1080
    assert result.data.height == 1920
    assert result.data.fps == 30.0
    assert result.data.duration_seconds == 5.0
    assert Path(result.data.artifact.uri).is_file()


def test_zero_sized_output_is_rejected(tmp_path: Path) -> None:
    """Empty final output files should fail validation safely."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner(write_empty_output_at_call=2)
    provider = build_provider(artifact_root=artifact_root, ffmpeg_path=ffmpeg_binary, command_runner=runner)

    with pytest.raises(ProviderResponseError) as exc_info:
        run_async(provider.render(build_request(image_path=image_path)))

    assert exc_info.value.code == "render_output_empty"


def test_missing_output_file_is_rejected(tmp_path: Path) -> None:
    """Successful exit without a final output file should fail safely."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")

    @dataclass
    class MissingFinalOutputRunner(RecordingFFmpegRunner):
        async def __call__(self, argv: tuple[str, ...], timeout_seconds: float | None) -> FFmpegCommandResult:
            result = await super().__call__(argv, timeout_seconds)
            if "-f" in argv and "concat" in argv:
                Path(argv[-1]).unlink(missing_ok=True)
            return result

    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=MissingFinalOutputRunner(),
    )

    with pytest.raises(ProviderResponseError) as exc_info:
        run_async(provider.render(build_request(image_path=image_path)))

    assert exc_info.value.code == "render_output_missing"


def test_non_zero_ffmpeg_exit_is_translated_safely(tmp_path: Path) -> None:
    """Non-zero FFmpeg exits should become typed provider response errors."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(fail_at_call=2),
    )

    with pytest.raises(ProviderResponseError) as exc_info:
        run_async(provider.render(build_request(image_path=image_path)))

    assert exc_info.value.code == "render_output_failed"
    assert "simulated stderr" not in str(exc_info.value)


def test_timeout_is_translated_and_forwards_context_timeout(tmp_path: Path) -> None:
    """Context timeouts should reach the runner and timeout errors should normalize safely."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    runner = RecordingFFmpegRunner(timeout_at_call=1)
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=runner,
        timeout_seconds=45.0,
    )

    with pytest.raises(ProviderTimeoutError):
        run_async(
            provider.render(
                build_request(image_path=image_path),
                context=ProviderRequestContext(timeout_seconds=12.5),
            )
        )

    assert runner.timeouts == [12.5]


def test_command_runner_os_error_is_translated(tmp_path: Path) -> None:
    """Runner startup failures should become provider unavailable errors."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(error_at_call=1),
    )

    with pytest.raises(ProviderUnavailableError):
        run_async(provider.render(build_request(image_path=image_path)))


def test_successful_run_cleans_intermediates_and_failed_run_cleans_safely(tmp_path: Path) -> None:
    """Intermediate working directories should not remain after success or failure."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path / "success_case")
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    success_provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(),
    )

    run_async(success_provider.render(build_request(image_path=image_path)))
    workspace_video_dir = artifact_root / "run_001" / "video"
    assert list(workspace_video_dir.glob(".ffmpeg_render_*")) == []

    failed_artifact_root, failed_image_path, _failed_video_path, _failed_narration_path = create_workspace_files(
        tmp_path / "failure_case"
    )
    failed_provider = build_provider(
        artifact_root=failed_artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(fail_at_call=2),
    )
    with pytest.raises(ProviderResponseError):
        run_async(failed_provider.render(build_request(image_path=failed_image_path)))
    failed_workspace_video_dir = failed_artifact_root / "run_001" / "video"
    assert list(failed_workspace_video_dir.glob(".ffmpeg_render_*")) == []


def test_final_output_is_not_silently_overwritten_and_preexisting_files_survive(tmp_path: Path) -> None:
    """Existing final outputs should block rendering without deleting pre-existing files."""

    artifact_root, image_path, _video_path, _narration_path = create_workspace_files(tmp_path)
    ffmpeg_binary = tmp_path / "ffmpeg.exe"
    ffmpeg_binary.write_text("binary", encoding="utf-8")
    workspace_video_dir = artifact_root / "run_001" / "video"
    existing_output = workspace_video_dir / "final_short.mp4"
    existing_output.write_bytes(b"preexisting")
    unrelated_file = workspace_video_dir / "keep.txt"
    unrelated_file.write_text("keep", encoding="utf-8")
    provider = build_provider(
        artifact_root=artifact_root,
        ffmpeg_path=ffmpeg_binary,
        command_runner=RecordingFFmpegRunner(),
    )

    with pytest.raises(ArtifactAlreadyExistsError):
        run_async(provider.render(build_request(image_path=image_path)))

    assert existing_output.read_bytes() == b"preexisting"
    assert unrelated_file.read_text(encoding="utf-8") == "keep"


def test_explicit_missing_provider_does_not_fallback() -> None:
    """Registry resolution should not silently fall back when FFmpeg is requested explicitly."""

    registry = create_provider_registry()
    registry.register(MockRenderProvider())

    with pytest.raises(ProviderNotFoundError):
        registry.get("render", "ffmpeg")


def test_ffmpeg_render_module_stays_local_only_and_avoids_moviepy() -> None:
    """The FFmpeg provider should remain a local subprocess adapter only."""

    module_source = Path("creatoros/providers/ffmpeg/render.py").read_text(encoding="utf-8")

    assert "httpx" not in module_source
    assert "requests" not in module_source
    assert "moviepy" not in module_source.lower()
    assert "openai" not in module_source.lower()
    assert "publish(" not in module_source
    assert "shell=True" not in module_source
