"""Pure audio-composition helpers for deterministic FFmpeg Short rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from creatoros.providers.render import (
    AudioCompositionPolicy,
    NarrationTimingPolicy,
    ShortRenderRequest,
)

DEFAULT_OUTPUT_AUDIO_CODEC: Final[str] = "aac"
DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ: Final[int] = 48_000
DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT: Final[str] = "stereo"
DEFAULT_OUTPUT_AUDIO_BITRATE: Final[str] = "192k"


@dataclass(frozen=True)
class AudioRenderPlan:
    """Deterministic audio render plan derived from one render request."""

    has_narration: bool
    include_audio_stream: bool
    sample_rate_hz: int
    channel_layout: str
    codec: str
    bitrate: str
    filter_chain: str | None


def build_audio_render_plan(request: ShortRenderRequest) -> AudioRenderPlan:
    """Build one deterministic audio plan from the provider-neutral render request."""

    validate_audio_policy(request.audio_policy)

    if request.narration is None:
        return AudioRenderPlan(
            has_narration=False,
            include_audio_stream=False,
            sample_rate_hz=DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ,
            channel_layout=DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT,
            codec=DEFAULT_OUTPUT_AUDIO_CODEC,
            bitrate=DEFAULT_OUTPUT_AUDIO_BITRATE,
            filter_chain=None,
        )

    if request.audio_policy.narration_timing is not NarrationTimingPolicy.FIT_TO_VIDEO:
        raise ValueError("unsupported narration_timing policy")

    return AudioRenderPlan(
        has_narration=True,
        include_audio_stream=True,
        sample_rate_hz=DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ,
        channel_layout=DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT,
        codec=DEFAULT_OUTPUT_AUDIO_CODEC,
        bitrate=DEFAULT_OUTPUT_AUDIO_BITRATE,
        filter_chain=build_narration_filter_chain(
            target_duration_seconds=request.total_duration_seconds,
            sample_rate_hz=DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ,
            channel_layout=DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT,
        ),
    )


def build_narration_filter_chain(
    *,
    target_duration_seconds: float,
    sample_rate_hz: int = DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ,
    channel_layout: str = DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT,
    input_stream_label: str = "[1:a]",
) -> str:
    """Build one deterministic FFmpeg audio filter chain for narration fitting."""

    if target_duration_seconds <= 0:
        raise ValueError("target_duration_seconds must be greater than zero")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be greater than zero")
    if not channel_layout.strip():
        raise ValueError("channel_layout must not be blank")
    if not input_stream_label.strip():
        raise ValueError("input_stream_label must not be blank")

    formatted_duration = f"{target_duration_seconds:.6f}".rstrip("0").rstrip(".")
    return (
        input_stream_label
        + 
        f"aresample={sample_rate_hz},"
        f"aformat=sample_fmts=fltp:channel_layouts={channel_layout},"
        "apad,"
        f"atrim=duration={formatted_duration}"
        "[narration_out]"
    )


def validate_audio_policy(policy: AudioCompositionPolicy) -> None:
    """Validate the currently supported provider-neutral audio policy."""

    if policy.narration_timing is not NarrationTimingPolicy.FIT_TO_VIDEO:
        raise ValueError("unsupported narration_timing policy")


__all__ = [
    "DEFAULT_OUTPUT_AUDIO_BITRATE",
    "DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT",
    "DEFAULT_OUTPUT_AUDIO_CODEC",
    "DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ",
    "AudioRenderPlan",
    "build_audio_render_plan",
    "build_narration_filter_chain",
    "validate_audio_policy",
]
