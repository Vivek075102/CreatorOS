"""Pure caption helpers for deterministic FFmpeg subtitle rendering."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from creatoros.providers.render import CaptionPosition, ProductionTimelineScene

DEFAULT_CAPTION_MAX_CHARS_PER_LINE: Final[int] = 32
_DEFAULT_MIN_FONT_SIZE: Final[int] = 28
_DEFAULT_MAX_FONT_SIZE: Final[int] = 72
_DEFAULT_FONT_HEIGHT_RATIO: Final[float] = 0.034
_DEFAULT_MARGIN_HEIGHT_RATIO: Final[float] = 0.055
_DEFAULT_MARGIN_WIDTH_RATIO: Final[float] = 0.05
_DEFAULT_OUTLINE_RATIO: Final[float] = 0.0022
_DEFAULT_SHADOW_RATIO: Final[float] = 0.0012
_ASS_SPECIAL_CHARACTERS = re.compile(r"([{}\\\\])")


@dataclass(frozen=True)
class CaptionStyle:
    """Derived visual style values for ASS subtitle output."""

    font_name: str
    font_size: int
    margin_vertical: int
    margin_horizontal: int
    outline: int
    shadow: int


@dataclass(frozen=True)
class TimedCaption:
    """One deterministic caption interval on the final Short timeline."""

    text: str
    start_seconds: float
    end_seconds: float
    position: CaptionPosition
    max_lines: int


def normalize_caption_text(text: str) -> str:
    """Normalize free-form caption text into one deterministic single-line string."""

    normalized_text = " ".join(text.replace("\r", "\n").split())
    if not normalized_text:
        raise ValueError("caption text must not be blank")
    return normalized_text


def wrap_caption_text(
    text: str,
    *,
    max_chars_per_line: int = DEFAULT_CAPTION_MAX_CHARS_PER_LINE,
    max_lines: int = 2,
) -> tuple[str, ...]:
    """Wrap caption text deterministically without silently truncating content."""

    if max_chars_per_line <= 0:
        raise ValueError("max_chars_per_line must be greater than zero")
    if max_lines <= 0:
        raise ValueError("max_lines must be greater than zero")

    normalized_text = normalize_caption_text(text)
    words = normalized_text.split(" ")
    lines: list[str] = []
    current_line = ""

    for word in words:
        word_segments = _split_long_word(word, max_chars_per_line=max_chars_per_line)
        for segment in word_segments:
            if not current_line:
                current_line = segment
                continue

            candidate_line = f"{current_line} {segment}"
            if len(candidate_line) <= max_chars_per_line:
                current_line = candidate_line
                continue

            lines.append(current_line)
            current_line = segment
            if len(lines) >= max_lines:
                raise ValueError("caption text exceeds the configured line capacity")

    if current_line:
        lines.append(current_line)

    if len(lines) > max_lines:
        raise ValueError("caption text exceeds the configured line capacity")
    return tuple(lines)


def build_timed_captions(
    scenes: tuple[ProductionTimelineScene, ...] | list[ProductionTimelineScene],
) -> tuple[TimedCaption, ...]:
    """Convert production-timeline caption relationships into final timeline intervals."""

    timed_captions: list[TimedCaption] = []

    for scene in scenes:
        if scene.caption_text is not None:
            timed_captions.append(
                TimedCaption(
                    text=normalize_caption_text(scene.caption_text),
                    start_seconds=scene.start_seconds,
                    end_seconds=scene.end_seconds,
                    position=scene.caption_position,
                    max_lines=scene.caption_max_lines,
                )
            )

    return tuple(timed_captions)


def derive_caption_style(
    *,
    width: int,
    height: int,
    font_name: str,
) -> CaptionStyle:
    """Derive a simple caption style that scales safely with vertical-video resolution."""

    if width <= 0 or height <= 0:
        raise ValueError("caption style dimensions must be greater than zero")

    font_size = _clamp(round(height * _DEFAULT_FONT_HEIGHT_RATIO), _DEFAULT_MIN_FONT_SIZE, _DEFAULT_MAX_FONT_SIZE)
    margin_vertical = max(24, round(height * _DEFAULT_MARGIN_HEIGHT_RATIO))
    margin_horizontal = max(24, round(width * _DEFAULT_MARGIN_WIDTH_RATIO))
    outline = max(1, round(height * _DEFAULT_OUTLINE_RATIO))
    shadow = max(0, round(height * _DEFAULT_SHADOW_RATIO))
    return CaptionStyle(
        font_name=font_name.strip(),
        font_size=font_size,
        margin_vertical=margin_vertical,
        margin_horizontal=margin_horizontal,
        outline=outline,
        shadow=shadow,
    )


def build_ass_subtitle_document(
    *,
    captions: tuple[TimedCaption, ...] | list[TimedCaption],
    width: int,
    height: int,
    font_name: str,
    max_chars_per_line: int = DEFAULT_CAPTION_MAX_CHARS_PER_LINE,
) -> str:
    """Build one deterministic UTF-8 ASS subtitle document for FFmpeg rendering."""

    style = derive_caption_style(width=width, height=height, font_name=font_name)
    header_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            "Style: Default,"
            f"{_escape_ass_style_value(style.font_name)},{style.font_size},&H00FFFFFF,&H000000FF,"
            f"&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},2,"
            f"{style.margin_horizontal},{style.margin_horizontal},{style.margin_vertical},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    event_lines = [
        (
            "Dialogue: 0,"
            f"{format_ass_timestamp(caption.start_seconds)},{format_ass_timestamp(caption.end_seconds)},"
            f"Default,,0,0,0,,{_build_ass_event_text(caption, max_chars_per_line=max_chars_per_line)}"
        )
        for caption in captions
    ]
    return "\n".join([*header_lines, *event_lines, ""])


def build_subtitles_filter_arg(*, subtitle_path: Path, fonts_dir: Path | None = None) -> str:
    """Build a safe FFmpeg subtitles filter argument for one local ASS file."""

    filter_value = f"subtitles='{_escape_filter_path(subtitle_path)}'"
    if fonts_dir is not None:
        filter_value += f":fontsdir='{_escape_filter_path(fonts_dir)}'"
    return filter_value


def format_ass_timestamp(seconds: float) -> str:
    """Format a non-negative second offset for ASS dialogue timestamps."""

    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("caption timestamp must be finite and non-negative")

    total_centiseconds = round(seconds * 100)
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def _build_ass_event_text(caption: TimedCaption, *, max_chars_per_line: int) -> str:
    """Build one escaped ASS dialogue payload with alignment overrides."""

    wrapped_lines = wrap_caption_text(
        caption.text,
        max_chars_per_line=max_chars_per_line,
        max_lines=caption.max_lines,
    )
    escaped_text = r"\N".join(_escape_ass_text(line) for line in wrapped_lines)
    alignment = {
        CaptionPosition.TOP: r"{\an8}",
        CaptionPosition.CENTER: r"{\an5}",
        CaptionPosition.BOTTOM: r"{\an2}",
    }[caption.position]
    return alignment + escaped_text


def _escape_ass_text(text: str) -> str:
    """Escape ASS override syntax characters while preserving visible caption text."""

    return _ASS_SPECIAL_CHARACTERS.sub(r"\\\1", text)


def _escape_ass_style_value(text: str) -> str:
    """Escape commas in ASS style values conservatively."""

    return text.replace(",", r"\,")


def _escape_filter_path(path: Path) -> str:
    """Escape a local path for FFmpeg filter arguments without invoking a shell."""

    return (
        path.as_posix()
        .replace("\\", "/")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("[", r"\[")
        .replace("]", r"\]")
        .replace(",", r"\,")
        .replace(";", r"\;")
    )


def _split_long_word(word: str, *, max_chars_per_line: int) -> tuple[str, ...]:
    """Split overlong tokens deterministically rather than dropping content."""

    if len(word) <= max_chars_per_line:
        return (word,)

    return tuple(
        word[index : index + max_chars_per_line]
        for index in range(0, len(word), max_chars_per_line)
    )


def _clamp(value: int, minimum: int, maximum: int) -> int:
    """Clamp one integer value within a closed range."""

    return max(minimum, min(maximum, value))


__all__ = [
    "DEFAULT_CAPTION_MAX_CHARS_PER_LINE",
    "CaptionStyle",
    "TimedCaption",
    "build_ass_subtitle_document",
    "build_subtitles_filter_arg",
    "build_timed_captions",
    "derive_caption_style",
    "format_ass_timestamp",
    "normalize_caption_text",
    "wrap_caption_text",
]
