"""Pure audio-composition helpers for deterministic FFmpeg Short rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from creatoros.domain import GeneratedAsset
from creatoros.providers.render import (
    AudioCompositionPolicy,
    AudioLoopPolicy,
    AudioTrackRole,
    NarrationTimingPolicy,
    ProductionTimeline,
    ShortRenderRequest,
)

DEFAULT_OUTPUT_AUDIO_CODEC: Final[str] = "aac"
DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ: Final[int] = 48_000
DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT: Final[str] = "stereo"
DEFAULT_OUTPUT_AUDIO_BITRATE: Final[str] = "192k"


@dataclass(frozen=True)
class PlannedAudioTrack:
    """Normalized provider-local audio-track plan derived from one render request."""

    source_asset_ref: GeneratedAsset
    role: AudioTrackRole
    start_seconds: float
    end_seconds: float | None
    duration_seconds: float | None
    source_duration_seconds: float | None
    gain_db: float
    fade_in_seconds: float
    fade_out_seconds: float
    loop_policy: AudioLoopPolicy
    duck_under_narration: bool


@dataclass(frozen=True)
class AudioRenderPlan:
    """Deterministic audio render plan derived from one render request."""

    tracks: tuple[PlannedAudioTrack, ...]
    include_audio_stream: bool
    sample_rate_hz: int
    channel_layout: str
    codec: str
    bitrate: str

    @property
    def has_narration(self) -> bool:
        """Return whether narration is present in the normalized audio plan."""

        return any(track.role is AudioTrackRole.NARRATION for track in self.tracks)


def build_audio_render_plan(request: ShortRenderRequest) -> AudioRenderPlan:
    """Build one deterministic audio plan from the provider-neutral render request."""

    validate_audio_policy(request.audio_policy)

    normalized_tracks: list[PlannedAudioTrack] = []
    if request.narration is not None:
        normalized_tracks.append(
            PlannedAudioTrack(
                source_asset_ref=request.narration.artifact.model_copy(deep=True),
                role=AudioTrackRole.NARRATION,
                start_seconds=0.0,
                end_seconds=None,
                duration_seconds=None,
                source_duration_seconds=request.narration.estimated_duration_seconds,
                gain_db=0.0,
                fade_in_seconds=0.0,
                fade_out_seconds=0.0,
                loop_policy=AudioLoopPolicy.NO_LOOP,
                duck_under_narration=False,
            )
        )

    normalized_tracks.extend(
        PlannedAudioTrack(
            source_asset_ref=track.source_asset_ref.model_copy(deep=True),
            role=track.role,
            start_seconds=track.start_seconds,
            end_seconds=track.end_seconds,
            duration_seconds=track.duration_seconds,
            source_duration_seconds=track.source_duration_seconds,
            gain_db=track.gain_db,
            fade_in_seconds=track.fade_in_seconds,
            fade_out_seconds=track.fade_out_seconds,
            loop_policy=track.loop_policy,
            duck_under_narration=track.duck_under_narration,
        )
        for track in request.audio_tracks
    )

    return AudioRenderPlan(
        tracks=tuple(normalized_tracks),
        include_audio_stream=bool(normalized_tracks),
        sample_rate_hz=DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ,
        channel_layout=DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT,
        codec=DEFAULT_OUTPUT_AUDIO_CODEC,
        bitrate=DEFAULT_OUTPUT_AUDIO_BITRATE,
    )


def build_audio_filter_chain(
    *,
    plan: AudioRenderPlan,
    target_duration_seconds: float,
    input_stream_indexes: tuple[int, ...],
    audio_policy: AudioCompositionPolicy,
    production_timeline: ProductionTimeline | None,
) -> str:
    """Build one deterministic FFmpeg audio filter chain for the normalized audio plan."""

    if target_duration_seconds <= 0:
        raise ValueError("target_duration_seconds must be greater than zero")
    if len(plan.tracks) != len(input_stream_indexes):
        raise ValueError("audio track and input stream counts must match")
    if not plan.tracks:
        raise ValueError("at least one audio track is required to build a filter chain")

    narration_intervals = _build_narration_intervals(
        production_timeline=production_timeline,
        fallback_narration_duration=target_duration_seconds if plan.has_narration else None,
    )
    filter_chains: list[str] = []
    track_labels: list[str] = []

    for track_index, (track, input_stream_index) in enumerate(
        zip(plan.tracks, input_stream_indexes, strict=True)
    ):
        input_label = f"[{input_stream_index}:a]"
        output_label = f"[audio_track_{track_index}]"
        filter_chains.append(
            _build_track_filter_chain(
                track=track,
                input_label=input_label,
                output_label=output_label,
                target_duration_seconds=target_duration_seconds,
                sample_rate_hz=plan.sample_rate_hz,
                channel_layout=plan.channel_layout,
                ducking_gain_db=audio_policy.narration_ducking_gain_db,
                narration_intervals=narration_intervals,
            )
        )
        track_labels.append(output_label)

    if len(track_labels) == 1:
        filter_chains.append(
            track_labels[0]
            + f"alimiter=limit=0.95,atrim=duration={_format_seconds(target_duration_seconds)}[audio_out]"
        )
        return ";".join(filter_chains)

    filter_chains.append(
        "".join(track_labels)
        + f"amix=inputs={len(track_labels)}:duration=longest:dropout_transition=0,"
        "alimiter=limit=0.95,"
        f"atrim=duration={_format_seconds(target_duration_seconds)}[audio_out]"
    )
    return ";".join(filter_chains)


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

    formatted_duration = _format_seconds(target_duration_seconds)
    return (
        input_stream_label
        + f"aresample={sample_rate_hz},"
        f"aformat=sample_fmts=fltp:channel_layouts={channel_layout},"
        "apad,"
        f"atrim=duration={formatted_duration}"
        "[narration_out]"
    )


def validate_audio_policy(policy: AudioCompositionPolicy) -> None:
    """Validate the currently supported provider-neutral audio policy."""

    if policy.narration_timing is not NarrationTimingPolicy.FIT_TO_VIDEO:
        raise ValueError("unsupported narration_timing policy")


def _build_track_filter_chain(
    *,
    track: PlannedAudioTrack,
    input_label: str,
    output_label: str,
    target_duration_seconds: float,
    sample_rate_hz: int,
    channel_layout: str,
    ducking_gain_db: float,
    narration_intervals: tuple[tuple[float, float], ...],
) -> str:
    """Build the deterministic FFmpeg chain for one normalized track."""

    filters = [
        f"aresample={sample_rate_hz}",
        f"aformat=sample_fmts=fltp:channel_layouts={channel_layout}",
    ]

    playable_duration = _resolve_playable_duration(track, target_duration_seconds=target_duration_seconds)
    if playable_duration is not None:
        filters.append(f"atrim=duration={_format_seconds(playable_duration)}")

    if track.fade_in_seconds > 0:
        filters.append(f"afade=t=in:st=0:d={_format_seconds(track.fade_in_seconds)}")
    if track.fade_out_seconds > 0:
        if playable_duration is None:
            raise ValueError("fade_out_seconds requires a bounded playable duration")
        fade_out_start = max(playable_duration - track.fade_out_seconds, 0.0)
        filters.append(
            f"afade=t=out:st={_format_seconds(fade_out_start)}:d={_format_seconds(track.fade_out_seconds)}"
        )

    if not math.isclose(track.gain_db, 0.0, rel_tol=0.0, abs_tol=1e-6):
        filters.append(f"volume={track.gain_db}dB")

    if track.start_seconds > 0:
        delay_ms = max(0, round(track.start_seconds * 1000))
        filters.append(f"adelay={delay_ms}|{delay_ms}")

    if track.duck_under_narration and narration_intervals:
        duck_gain_linear = 10 ** (ducking_gain_db / 20)
        filters.append(
            "volume='"
            + _build_ducking_expression(
                duck_gain_linear=duck_gain_linear,
                narration_intervals=narration_intervals,
            )
            + "'"
        )

    filters.extend(
        [
            "apad",
            f"atrim=duration={_format_seconds(target_duration_seconds)}",
        ]
    )
    return input_label + ",".join(filters) + output_label


def _resolve_playable_duration(
    track: PlannedAudioTrack,
    *,
    target_duration_seconds: float,
) -> float | None:
    """Resolve the bounded duration for one track before timeline placement."""

    if track.role is AudioTrackRole.NARRATION:
        return target_duration_seconds
    if track.duration_seconds is not None:
        return min(track.duration_seconds, max(target_duration_seconds - track.start_seconds, 0.0))
    if track.end_seconds is not None:
        return min(track.end_seconds - track.start_seconds, max(target_duration_seconds - track.start_seconds, 0.0))
    if (
        track.source_duration_seconds is not None
        and track.loop_policy is AudioLoopPolicy.NO_LOOP
    ):
        return min(track.source_duration_seconds, max(target_duration_seconds - track.start_seconds, 0.0))
    return max(target_duration_seconds - track.start_seconds, 0.0)


def _build_narration_intervals(
    *,
    production_timeline: ProductionTimeline | None,
    fallback_narration_duration: float | None,
) -> tuple[tuple[float, float], ...]:
    """Return merged narration intervals for music ducking decisions."""

    if production_timeline is None:
        if fallback_narration_duration is None:
            return ()
        return ((0.0, fallback_narration_duration),)

    intervals = [
        (scene.narration_start_seconds, scene.narration_end_seconds)
        for scene in production_timeline.scenes
        if scene.narration_start_seconds is not None and scene.narration_end_seconds is not None
    ]
    normalized = [(start, end) for start, end in intervals if end > start]
    if not normalized:
        if fallback_narration_duration is None:
            return ()
        return ((0.0, fallback_narration_duration),)

    merged: list[tuple[float, float]] = []
    for start, end in normalized:
        if not merged:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        if start <= previous_end + 1e-6:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _build_ducking_expression(
    *,
    duck_gain_linear: float,
    narration_intervals: tuple[tuple[float, float], ...],
) -> str:
    """Build one deterministic global-time ducking expression."""

    interval_terms = "+".join(
        f"between(t,{_format_seconds(start)},{_format_seconds(end)})"
        for start, end in narration_intervals
    )
    return f"if(gt({interval_terms},0),{duck_gain_linear:.6f},1)"


def _format_seconds(value: float) -> str:
    """Format one deterministic FFmpeg-friendly duration value."""

    return f"{value:.6f}".rstrip("0").rstrip(".")


__all__ = [
    "DEFAULT_OUTPUT_AUDIO_BITRATE",
    "DEFAULT_OUTPUT_AUDIO_CHANNEL_LAYOUT",
    "DEFAULT_OUTPUT_AUDIO_CODEC",
    "DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE_HZ",
    "AudioRenderPlan",
    "PlannedAudioTrack",
    "build_audio_filter_chain",
    "build_audio_render_plan",
    "build_narration_filter_chain",
    "validate_audio_policy",
]
