"""Bootstrap helpers for the CreatorOS FFmpeg render provider."""

from __future__ import annotations

from pathlib import Path

from creatoros.config import get_settings
from creatoros.providers.ffmpeg.render import FFmpegRenderProvider
from creatoros.providers.registry import ProviderRegistry


def register_ffmpeg_render_provider(
    registry: ProviderRegistry,
    *,
    replace: bool = False,
    ffmpeg_path: str | Path | None = None,
) -> FFmpegRenderProvider:
    """Register one local FFmpeg render provider without starting subprocesses."""

    settings = get_settings()
    provider = FFmpegRenderProvider(
        artifact_root=settings.artifact_root,
        ffmpeg_path=settings.ffmpeg_path if ffmpeg_path is None else ffmpeg_path,
        timeout_seconds=settings.provider_timeout_seconds,
        caption_font_name=getattr(settings, "caption_font_name", "Arial"),
        caption_font_file=getattr(settings, "caption_font_file", None),
    )
    registry.register(provider, replace=replace)
    return provider


__all__ = ["register_ffmpeg_render_provider"]
