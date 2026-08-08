"""FFmpeg-backed local render provider for CreatorOS."""

from creatoros.providers.ffmpeg.bootstrap import register_ffmpeg_render_provider
from creatoros.providers.ffmpeg.render import (
    DEFAULT_FFMPEG_RENDER_PROVIDER_NAME,
    FFmpegCommandResult,
    FFmpegRenderProvider,
    resolve_ffmpeg_binary,
)

__all__ = [
    "DEFAULT_FFMPEG_RENDER_PROVIDER_NAME",
    "FFmpegCommandResult",
    "FFmpegRenderProvider",
    "register_ffmpeg_render_provider",
    "resolve_ffmpeg_binary",
]
