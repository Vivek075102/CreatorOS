"""Local FFmpeg-backed render provider for CreatorOS Short composition."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from creatoros.core import (
    ArtifactAlreadyExistsError,
    ArtifactPathError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.observability import get_logger
from creatoros.providers.base import (
    ProviderCapability,
    ProviderInfo,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.ffmpeg.audio import build_audio_render_plan
from creatoros.providers.ffmpeg.captions import (
    build_ass_subtitle_document,
    build_subtitles_filter_arg,
    build_timed_captions,
)
from creatoros.providers.render import RenderedVideo, RenderScene, ShortRenderRequest

DEFAULT_FFMPEG_RENDER_PROVIDER_NAME = "ffmpeg"
_LOGGER = get_logger("providers.ffmpeg.render")


@dataclass(frozen=True)
class FFmpegCommandResult:
    """Normalized local FFmpeg command result."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


type FFmpegCommandRunner = Callable[[tuple[str, ...], float | None], Awaitable[FFmpegCommandResult]]


def resolve_ffmpeg_binary(ffmpeg_path: str | Path | None = None) -> Path | None:
    """Resolve the local FFmpeg executable path without starting a subprocess."""

    if ffmpeg_path is not None:
        return Path(ffmpeg_path).expanduser().resolve()

    discovered_path = shutil.which("ffmpeg")
    if discovered_path is None:
        return None
    return Path(discovered_path).resolve()


async def _run_ffmpeg_command(
    argv: tuple[str, ...],
    timeout_seconds: float | None,
) -> FFmpegCommandResult:
    """Execute one FFmpeg argv command without invoking a shell."""

    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise

    return FFmpegCommandResult(
        exit_code=0 if process.returncode is None else process.returncode,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )


class FFmpegRenderProvider:
    """Render a local Short MP4 from materialized local scene assets using FFmpeg."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        ffmpeg_path: Path | str | None = None,
        timeout_seconds: float = 30.0,
        caption_font_name: str = "Arial",
        caption_font_file: Path | str | None = None,
        command_runner: FFmpegCommandRunner | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.ffmpeg_path = ffmpeg_path
        self.timeout_seconds = timeout_seconds
        self.caption_font_name = caption_font_name.strip()
        self.caption_font_file = None if caption_font_file is None else Path(caption_font_file).expanduser().resolve()
        self.command_runner = _run_ffmpeg_command if command_runner is None else command_runner
        self._info = ProviderInfo(
            name=DEFAULT_FFMPEG_RENDER_PROVIDER_NAME,
            provider_type="render",
            capabilities={ProviderCapability.RENDERING},
            metadata={"runtime": "local"},
        )

    @property
    def info(self) -> ProviderInfo:
        """Return metadata describing the local FFmpeg render provider."""

        return self._info

    async def health_check(self) -> bool:
        """Return whether a usable local FFmpeg binary is discoverable."""

        ffmpeg_binary = resolve_ffmpeg_binary(self.ffmpeg_path)
        return ffmpeg_binary is not None and ffmpeg_binary.is_file()

    async def render(
        self,
        request: ShortRenderRequest,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[RenderedVideo]:
        """Render a local MP4 from materialized scene files and optional narration."""

        ffmpeg_binary = self._require_ffmpeg_binary()
        run_id, workspace_video_dir, scene_sources, narration_path = self._resolve_inputs(request)
        output_path = self._build_output_path(workspace_video_dir)
        working_directory = Path(
            tempfile.mkdtemp(prefix=".ffmpeg_render_", dir=workspace_video_dir),
        ).resolve()
        created_output = False

        try:
            scene_segments = await self._render_scene_segments(
                request,
                ffmpeg_binary=ffmpeg_binary,
                scene_sources=scene_sources,
                working_directory=working_directory,
                timeout_seconds=self._resolve_timeout_seconds(context),
            )
            concat_list_path = self._write_concat_list(
                scene_segments,
                working_directory=working_directory,
            )
            caption_subtitle_path = self._write_caption_subtitle_file(
                request,
                working_directory=working_directory,
            )
            await self._compose_final_video(
                request=request,
                ffmpeg_binary=ffmpeg_binary,
                concat_list_path=concat_list_path,
                narration_path=narration_path,
                caption_subtitle_path=caption_subtitle_path,
                output_path=output_path,
                timeout_seconds=self._resolve_timeout_seconds(context),
            )
            created_output = output_path.exists()
            self._validate_output_file(output_path)
        except Exception:
            if (created_output or output_path.exists()) and output_path.exists():
                output_path.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(working_directory, ignore_errors=True)

        request_digest = self._build_request_digest(request)
        rendered_video = RenderedVideo(
            artifact=GeneratedAsset(
                asset_type=AssetType.VIDEO,
                uri=str(output_path),
                metadata={
                    "local": True,
                    "workspace_run_id": run_id,
                },
            ),
            provider_name=self.info.name,
            mime_type="video/mp4",
            duration_seconds=request.total_duration_seconds,
            width=request.width,
            height=request.height,
            fps=request.fps,
            request_id=f"ffmpeg_render_{request_digest}",
            metadata={
                "scene_count": len(request.scenes),
                "output_format": request.output_format,
                "has_narration": narration_path is not None,
                "has_audio_stream": narration_path is not None,
                "audio_codec": "aac" if narration_path is not None else "none",
                "audio_policy": request.audio_policy.narration_timing.value,
                "audio_sample_rate_hz": 48_000 if narration_path is not None else None,
                "audio_channel_layout": "stereo" if narration_path is not None else None,
                "local": True,
            },
        )
        _LOGGER.info(
            "provider_render_completed",
            provider_name=self.info.name,
            request_id=rendered_video.request_id,
            scene_count=len(request.scenes),
            has_narration=narration_path is not None,
            output_filename=output_path.name,
            success=True,
        )
        return ProviderResult[RenderedVideo](
            data=rendered_video,
            provider=self.info,
            usage=ProviderUsage(
                input_units=len(request.scenes),
                output_units=1,
                total_units=len(request.scenes) + 1,
                estimated_cost=0.0,
                currency="USD",
            ),
            request_id=rendered_video.request_id,
        )

    def _require_ffmpeg_binary(self) -> Path:
        """Resolve and validate the configured or discovered FFmpeg executable."""

        ffmpeg_binary = resolve_ffmpeg_binary(self.ffmpeg_path)
        if ffmpeg_binary is None or not ffmpeg_binary.exists() or not ffmpeg_binary.is_file():
            raise ProviderUnavailableError(
                "FFmpeg is not available for local rendering",
                code="provider_binary_unavailable",
                details={"provider_name": self.info.name},
            )
        return ffmpeg_binary

    def _resolve_inputs(
        self,
        request: ShortRenderRequest,
    ) -> tuple[str, Path, list[Path], Path | None]:
        """Resolve all render inputs into validated local artifact paths."""

        scene_sources: list[Path] = []
        run_id: str | None = None

        for scene in request.scenes:
            source_path = self._resolve_scene_source_path(scene)
            scene_sources.append(source_path)
            resolved_run_id = self._extract_run_id(source_path)
            if run_id is None:
                run_id = resolved_run_id
            elif resolved_run_id != run_id:
                raise ArtifactPathError(
                    "render scenes must come from one artifact workspace",
                    code="render_workspace_mismatch",
                )

        narration_path = None
        if request.narration is not None:
            narration_path = self._resolve_local_asset_path(
                request.narration.artifact.uri,
                asset_label="narration",
                expected_asset_type=AssetType.AUDIO,
            )
            narration_run_id = self._extract_run_id(narration_path)
            if run_id is None:
                run_id = narration_run_id
            elif narration_run_id != run_id:
                raise ArtifactPathError(
                    "narration must come from the same artifact workspace as scene assets",
                    code="render_workspace_mismatch",
                )

        if run_id is None:
            raise ArtifactPathError(
                "render request does not contain any local materialized scene assets",
                code="render_missing_local_assets",
            )

        workspace_video_dir = (self.artifact_root / run_id / "video").resolve()
        workspace_video_dir.mkdir(parents=True, exist_ok=True)
        return run_id, workspace_video_dir, scene_sources, narration_path

    def _resolve_scene_source_path(self, scene: RenderScene) -> Path:
        """Resolve the preferred local source path for one render scene."""

        if scene.video_asset_ref is not None:
            return self._resolve_local_asset_path(
                scene.video_asset_ref.uri,
                asset_label=f"scene_{scene.scene_number}_video",
                expected_asset_type=AssetType.VIDEO,
            )
        if scene.visual_asset_ref is not None:
            return self._resolve_local_asset_path(
                scene.visual_asset_ref.uri,
                asset_label=f"scene_{scene.scene_number}_image",
                expected_asset_type=AssetType.IMAGE,
            )
        raise ArtifactPathError(
            "scene is missing a local materialized asset reference",
            code="render_missing_local_assets",
        )

    def _resolve_local_asset_path(
        self,
        uri: str,
        *,
        asset_label: str,
        expected_asset_type: AssetType,
    ) -> Path:
        """Resolve one local absolute asset path under the configured artifact root."""

        direct_path = Path(uri)
        if direct_path.is_absolute():
            raw_path = direct_path
        else:
            parsed_uri = urlparse(uri)
            if parsed_uri.scheme and parsed_uri.scheme.lower() != "file":
                raise ArtifactPathError(
                    "render inputs must reference local materialized files",
                    code="render_non_local_asset",
                    details={"asset_label": asset_label, "asset_type": expected_asset_type.value},
                )

            if parsed_uri.scheme.lower() == "file":
                raw_path = Path(url2pathname(parsed_uri.netloc + parsed_uri.path))
            else:
                raw_path = Path(uri)

        if not raw_path.is_absolute():
            raise ArtifactPathError(
                "render input path must be absolute",
                code="render_relative_asset_path",
                details={"asset_label": asset_label},
            )

        resolved_path = raw_path.resolve()
        if not resolved_path.is_relative_to(self.artifact_root):
            raise ArtifactPathError(
                "render input path is outside the configured artifact root",
                code="render_asset_outside_root",
                details={"asset_label": asset_label},
            )
        if not resolved_path.exists() or not resolved_path.is_file():
            raise ArtifactPathError(
                "render input file does not exist",
                code="render_asset_missing",
                details={"asset_label": asset_label},
            )
        return resolved_path

    def _extract_run_id(self, asset_path: Path) -> str:
        """Return the artifact workspace run identifier for one validated asset path."""

        relative_path = asset_path.relative_to(self.artifact_root)
        return relative_path.parts[0]

    def _build_output_path(self, workspace_video_dir: Path) -> Path:
        """Return the deterministic local final MP4 path for the render output."""

        output_path = (workspace_video_dir / "final_short.mp4").resolve()
        if not output_path.is_relative_to(workspace_video_dir.resolve()):
            raise ArtifactPathError(
                "final render output escaped the workspace video directory",
                code="render_output_outside_workspace",
            )
        if output_path.exists():
            raise ArtifactAlreadyExistsError(
                f"artifact already exists at '{output_path.name}'",
                code="artifact_already_exists",
                details={"filename": output_path.name},
            )
        return output_path

    async def _render_scene_segments(
        self,
        request: ShortRenderRequest,
        *,
        ffmpeg_binary: Path,
        scene_sources: Sequence[Path],
        working_directory: Path,
        timeout_seconds: float | None,
    ) -> list[Path]:
        """Render normalized intermediate MP4 segments for every scene."""

        rendered_segments: list[Path] = []
        for scene, source_path in zip(request.scenes, scene_sources, strict=True):
            segment_path = (working_directory / f"scene_{scene.scene_number:03d}.mp4").resolve()
            command = self._build_scene_command(
                scene,
                source_path=source_path,
                segment_path=segment_path,
                ffmpeg_binary=ffmpeg_binary,
                width=request.width,
                height=request.height,
                fps=request.fps,
            )
            await self._execute_ffmpeg_command(
                command,
                timeout_seconds=timeout_seconds,
                failure_code="render_scene_failed",
            )
            self._validate_output_file(segment_path)
            rendered_segments.append(segment_path)
        return rendered_segments

    def _build_scene_command(
        self,
        scene: RenderScene,
        *,
        source_path: Path,
        segment_path: Path,
        ffmpeg_binary: Path,
        width: int,
        height: int,
        fps: float,
    ) -> tuple[str, ...]:
        """Build one FFmpeg argv command for a normalized scene segment."""

        scale_filter = (
            f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )
        base_command = [str(ffmpeg_binary), "-y"]
        if scene.video_asset_ref is not None:
            base_command.extend(
                [
                    "-i",
                    str(source_path),
                    "-t",
                    self._format_seconds(scene.duration_seconds),
                    "-r",
                    self._format_fps(fps),
                    "-vf",
                    scale_filter,
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(segment_path),
                ]
            )
            return tuple(base_command)

        base_command.extend(
            [
                "-loop",
                "1",
                "-i",
                str(source_path),
                "-t",
                self._format_seconds(scene.duration_seconds),
                "-r",
                self._format_fps(fps),
                "-vf",
                scale_filter,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(segment_path),
            ]
        )
        return tuple(base_command)

    def _write_concat_list(
        self,
        scene_segments: Sequence[Path],
        *,
        working_directory: Path,
    ) -> Path:
        """Write the deterministic FFmpeg concat list file for ordered scene segments."""

        concat_list_path = (working_directory / "concat_list.txt").resolve()
        concat_list_contents = "\n".join(
            "file '" + segment_path.as_posix().replace("'", "'\\''") + "'"
            for segment_path in scene_segments
        )
        concat_list_path.write_text(concat_list_contents + "\n", encoding="utf-8")
        return concat_list_path

    async def _compose_final_video(
        self,
        *,
        request: ShortRenderRequest,
        ffmpeg_binary: Path,
        concat_list_path: Path,
        narration_path: Path | None,
        caption_subtitle_path: Path | None,
        output_path: Path,
        timeout_seconds: float | None,
    ) -> None:
        """Compose normalized scene segments and optional narration into the final MP4."""

        audio_plan = build_audio_render_plan(request)
        command = [
            str(ffmpeg_binary),
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
        ]
        if audio_plan.include_audio_stream and narration_path is not None:
            command.extend(["-i", str(narration_path)])
        if caption_subtitle_path is not None:
            command.extend(
                [
                    "-vf",
                    build_subtitles_filter_arg(
                        subtitle_path=caption_subtitle_path,
                        fonts_dir=self._resolve_caption_fonts_dir(),
                    ),
                ]
            )
        if audio_plan.include_audio_stream and narration_path is not None:
            assert audio_plan.filter_chain is not None
            command.extend(
                [
                    "-filter_complex",
                    audio_plan.filter_chain,
                    "-map",
                    "0:v:0",
                    "-map",
                    "[narration_out]",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    audio_plan.codec,
                    "-ar",
                    str(audio_plan.sample_rate_hz),
                    "-ac",
                    "2",
                    "-b:a",
                    audio_plan.bitrate,
                    "-movflags",
                    "+faststart",
                    "-t",
                    self._format_seconds(request.total_duration_seconds),
                    str(output_path),
                ]
            )
        else:
            command.extend(
                [
                    "-map",
                    "0:v:0",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    "-movflags",
                    "+faststart",
                    "-t",
                    self._format_seconds(request.total_duration_seconds),
                    str(output_path),
                ]
            )
        await self._execute_ffmpeg_command(
            tuple(command),
            timeout_seconds=timeout_seconds,
            failure_code="render_output_failed",
        )

    def _write_caption_subtitle_file(
        self,
        request: ShortRenderRequest,
        *,
        working_directory: Path,
    ) -> Path | None:
        """Write one temporary ASS subtitle file when timed captions are present."""

        timed_captions = build_timed_captions(request.scenes)
        if not timed_captions:
            return None

        self._validate_caption_configuration()
        subtitle_path = (working_directory / "captions.ass").resolve()
        if not subtitle_path.is_relative_to(working_directory):
            raise ArtifactPathError(
                "caption subtitle file escaped the FFmpeg working directory",
                code="render_subtitle_outside_workspace",
            )

        subtitle_document = build_ass_subtitle_document(
            captions=timed_captions,
            width=request.width,
            height=request.height,
            font_name=self.caption_font_name,
        )
        subtitle_path.write_text(subtitle_document, encoding="utf-8")
        return subtitle_path

    def _validate_caption_configuration(self) -> None:
        """Validate the local caption font configuration before subtitle rendering."""

        if not self.caption_font_name:
            raise ProviderUnavailableError(
                "Caption font configuration is invalid",
                code="provider_invalid_configuration",
                details={"provider_name": self.info.name},
            )

        if self.caption_font_file is None:
            return

        if not self.caption_font_file.exists() or not self.caption_font_file.is_file():
            raise ProviderUnavailableError(
                "Caption font file is unavailable",
                code="provider_invalid_configuration",
                details={"provider_name": self.info.name},
            )

    def _resolve_caption_fonts_dir(self) -> Path | None:
        """Return the optional font directory for FFmpeg subtitle resolution."""

        if self.caption_font_file is None:
            return None
        return self.caption_font_file.parent

    async def _execute_ffmpeg_command(
        self,
        argv: tuple[str, ...],
        *,
        timeout_seconds: float | None,
        failure_code: str,
    ) -> FFmpegCommandResult:
        """Run one FFmpeg command and translate failures into safe provider errors."""

        try:
            result = await self.command_runner(argv, timeout_seconds)
        except TimeoutError as error:
            raise ProviderTimeoutError(
                "FFmpeg render operation timed out",
                code="provider_timeout",
                details={"provider_name": self.info.name},
            ) from error
        except ProviderTimeoutError:
            raise
        except OSError as error:
            raise ProviderUnavailableError(
                "FFmpeg could not be started for local rendering",
                code="provider_binary_unavailable",
                details={"provider_name": self.info.name},
            ) from error
        except Exception as error:
            raise ProviderResponseError(
                "FFmpeg render command failed unexpectedly",
                code="provider_response_invalid",
                details={"provider_name": self.info.name},
            ) from error

        if result.exit_code != 0:
            raise ProviderResponseError(
                "FFmpeg render command failed",
                code=failure_code,
                details={"provider_name": self.info.name, "exit_code": result.exit_code},
            )
        return result

    @staticmethod
    def _validate_output_file(output_path: Path) -> None:
        """Require a successful FFmpeg output file to exist and remain non-empty."""

        if not output_path.exists() or not output_path.is_file():
            raise ProviderResponseError(
                "FFmpeg completed without a render output file",
                code="render_output_missing",
            )
        if output_path.stat().st_size <= 0:
            output_path.unlink(missing_ok=True)
            raise ProviderResponseError(
                "FFmpeg produced an empty render output file",
                code="render_output_empty",
            )

    def _resolve_timeout_seconds(self, context: ProviderRequestContext | None) -> float | None:
        """Resolve the active timeout for one render operation."""

        if context is not None and context.timeout_seconds is not None:
            return context.timeout_seconds
        return self.timeout_seconds

    @staticmethod
    def _format_seconds(value: float) -> str:
        """Format one scene duration for deterministic FFmpeg argv use."""

        return f"{value:.6f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_fps(value: float) -> str:
        """Format one frame rate for deterministic FFmpeg argv use."""

        return f"{value:.6f}".rstrip("0").rstrip(".")

    @staticmethod
    def _build_request_digest(request: ShortRenderRequest) -> str:
        """Create one stable digest for request-local identifiers."""

        payload = {
            "scenes": [
                {
                    "scene_number": scene.scene_number,
                    "duration_seconds": scene.duration_seconds,
                    "visual_asset_uri": None if scene.visual_asset_ref is None else scene.visual_asset_ref.uri,
                    "video_asset_uri": None if scene.video_asset_ref is None else scene.video_asset_ref.uri,
                    "caption": None if scene.caption is None else scene.caption.model_dump(mode="json"),
                }
                for scene in request.scenes
            ],
            "narration_uri": None if request.narration is None else request.narration.artifact.uri,
            "audio_policy": request.audio_policy.model_dump(mode="json"),
            "width": request.width,
            "height": request.height,
            "fps": request.fps,
            "output_format": request.output_format,
            "caption_font_name": request.metadata.get("caption_font_name"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


__all__ = [
    "DEFAULT_FFMPEG_RENDER_PROVIDER_NAME",
    "FFmpegCommandResult",
    "FFmpegRenderProvider",
    "resolve_ffmpeg_binary",
]
