"""Pure caption helpers for deterministic FFmpeg subtitle rendering."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Final

from creatoros.providers.render import (
    CaptionEmphasis,
    CaptionFontSizeProfile,
    CaptionPosition,
    CaptionSafeMarginProfile,
    CaptionStylePolicy,
    CaptionTextAlignment,
    ProductionTimelineScene,
)

DEFAULT_CAPTION_MAX_CHARS_PER_LINE: Final[int] = 32
_DEFAULT_MIN_FONT_SIZE: Final[int] = 28
_DEFAULT_MAX_FONT_SIZE: Final[int] = 78
_DEFAULT_FONT_HEIGHT_RATIO: Final[float] = 0.034
_DEFAULT_LARGE_FONT_MULTIPLIER: Final[float] = 1.12
_DEFAULT_BOTTOM_MARGIN_RATIO: Final[float] = 0.09
_DEFAULT_TOP_MARGIN_RATIO: Final[float] = 0.065
_DEFAULT_TIGHT_MARGIN_RATIO: Final[float] = 0.055
_DEFAULT_MARGIN_WIDTH_RATIO: Final[float] = 0.065
_DEFAULT_TIGHT_MARGIN_WIDTH_RATIO: Final[float] = 0.05
_DEFAULT_OUTLINE_RATIO: Final[float] = 0.0024
_DEFAULT_SHADOW_RATIO: Final[float] = 0.0015
_ASS_SPECIAL_CHARACTERS = re.compile(r"([{}\\\\])")
_EMPHASIS_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "so",
        "than",
        "that",
        "the",
        "their",
        "there",
        "these",
        "they",
        "this",
        "to",
        "up",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)


@dataclass(frozen=True)
class CaptionStyle:
    """Derived visual style values for ASS subtitle output."""

    font_name: str
    font_size: int
    margin_vertical: int
    margin_horizontal: int
    outline: int
    shadow: int
    bold: bool
    text_alignment: CaptionTextAlignment


@dataclass(frozen=True)
class TimedCaption:
    """One deterministic caption interval on the final Short timeline."""

    text: str
    start_seconds: float
    end_seconds: float
    position: CaptionPosition
    max_lines: int
    style: CaptionStylePolicy


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
    """Wrap caption text deterministically with punctuation-aware and orphan-aware balancing."""

    if max_chars_per_line <= 0:
        raise ValueError("max_chars_per_line must be greater than zero")
    if max_lines <= 0:
        raise ValueError("max_lines must be greater than zero")

    normalized_text = normalize_caption_text(text)
    words = _normalize_wrappable_words(normalized_text, max_chars_per_line=max_chars_per_line)
    wrapped = _solve_wrapped_lines(tuple(words), max_chars_per_line=max_chars_per_line, max_lines=max_lines)
    if wrapped is None:
        raise ValueError("caption text exceeds the configured line capacity")
    return wrapped


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
                    style=scene.caption_style.model_copy(deep=True),
                )
            )

    return tuple(timed_captions)


def derive_caption_style(
    *,
    width: int,
    height: int,
    font_name: str,
    style_policy: CaptionStylePolicy | None = None,
    position: CaptionPosition = CaptionPosition.BOTTOM,
) -> CaptionStyle:
    """Derive a caption style that scales safely with vertical-video resolution."""

    if width <= 0 or height <= 0:
        raise ValueError("caption style dimensions must be greater than zero")

    resolved_policy = CaptionStylePolicy() if style_policy is None else style_policy
    font_size = round(height * _DEFAULT_FONT_HEIGHT_RATIO)
    if resolved_policy.font_size_profile is CaptionFontSizeProfile.LARGE:
        font_size = round(font_size * _DEFAULT_LARGE_FONT_MULTIPLIER)
    font_size = _clamp(font_size, _DEFAULT_MIN_FONT_SIZE, _DEFAULT_MAX_FONT_SIZE)

    vertical_ratio = (
        _DEFAULT_TIGHT_MARGIN_RATIO
        if resolved_policy.safe_margin_profile is CaptionSafeMarginProfile.TIGHT
        else (_DEFAULT_TOP_MARGIN_RATIO if position is CaptionPosition.TOP else _DEFAULT_BOTTOM_MARGIN_RATIO)
    )
    horizontal_ratio = (
        _DEFAULT_TIGHT_MARGIN_WIDTH_RATIO
        if resolved_policy.safe_margin_profile is CaptionSafeMarginProfile.TIGHT
        else _DEFAULT_MARGIN_WIDTH_RATIO
    )
    margin_vertical = max(24, round(height * vertical_ratio))
    margin_horizontal = max(24, round(width * horizontal_ratio))
    outline = max(1, round(height * _DEFAULT_OUTLINE_RATIO))
    shadow = max(0, round(height * _DEFAULT_SHADOW_RATIO))
    return CaptionStyle(
        font_name=font_name.strip(),
        font_size=font_size,
        margin_vertical=margin_vertical,
        margin_horizontal=margin_horizontal,
        outline=outline,
        shadow=shadow,
        bold=False,
        text_alignment=resolved_policy.text_alignment,
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
        _build_ass_dialogue_line(
            caption,
            width=width,
            height=height,
            font_name=font_name,
            max_chars_per_line=max_chars_per_line,
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


def determine_emphasized_token_indices(
    text: str,
    *,
    emphasis: CaptionEmphasis,
) -> tuple[int, ...]:
    """Return deterministic token indices to emphasize for one caption string."""

    if emphasis is CaptionEmphasis.NONE:
        return ()

    words = _caption_words(normalize_caption_text(text))
    eligible_indices = [index for index, word in enumerate(words) if _is_emphasis_candidate(word)]
    if not eligible_indices:
        return ()

    if emphasis is CaptionEmphasis.KEYWORD:
        scored = sorted(
            eligible_indices,
            key=lambda index: (-len(_normalize_emphasis_word(words[index])), index),
        )
        max_count = 1 if len(eligible_indices) < 3 else 2
        return tuple(sorted(scored[:max_count]))

    best_phrase: tuple[int, ...] | None = None
    best_score = -1
    for start_index, end_index in pairwise(eligible_indices):
        if end_index != start_index + 1:
            continue
        score = len(_normalize_emphasis_word(words[start_index])) + len(_normalize_emphasis_word(words[end_index]))
        if score > best_score:
            best_phrase = (start_index, end_index)
            best_score = score

    if best_phrase is not None:
        return best_phrase
    return determine_emphasized_token_indices(text, emphasis=CaptionEmphasis.KEYWORD)


def _build_ass_event_text(
    caption: TimedCaption,
    *,
    width: int,
    height: int,
    font_name: str,
    max_chars_per_line: int,
) -> str:
    """Build one escaped ASS dialogue payload with alignment and deterministic emphasis."""

    derived_style = derive_caption_style(
        width=width,
        height=height,
        font_name=font_name,
        style_policy=caption.style,
        position=caption.position,
    )
    wrapped_lines = wrap_caption_text(
        caption.text,
        max_chars_per_line=min(max_chars_per_line, caption.style.max_chars_per_line),
        max_lines=caption.max_lines,
    )
    emphasis_indices = determine_emphasized_token_indices(caption.text, emphasis=caption.style.emphasis)
    emphasized_words = _emphasize_wrapped_lines(wrapped_lines, emphasis_indices=emphasis_indices)
    escaped_text = r"\N".join(emphasized_words)
    inline_overrides = _alignment_override(position=caption.position, text_alignment=derived_style.text_alignment)
    inline_overrides += rf"{{\fs{derived_style.font_size}}}"
    return inline_overrides + escaped_text


def _build_ass_dialogue_line(
    caption: TimedCaption,
    *,
    width: int,
    height: int,
    font_name: str,
    max_chars_per_line: int,
) -> str:
    """Build one ASS dialogue row with deterministic per-caption styling and margins."""

    derived_style = derive_caption_style(
        width=width,
        height=height,
        font_name=font_name,
        style_policy=caption.style,
        position=caption.position,
    )
    return (
        "Dialogue: 0,"
        f"{format_ass_timestamp(caption.start_seconds)},{format_ass_timestamp(caption.end_seconds)},"
        f"Default,,{derived_style.margin_horizontal},{derived_style.margin_horizontal},"
        f"{derived_style.margin_vertical},,"
        f"{_build_ass_event_text(caption, width=width, height=height, font_name=font_name, max_chars_per_line=max_chars_per_line)}"
    )


def _alignment_override(*, position: CaptionPosition, text_alignment: CaptionTextAlignment) -> str:
    """Return one ASS alignment override that combines vertical and horizontal placement."""

    alignment_map = {
        (CaptionPosition.TOP, CaptionTextAlignment.LEFT): r"{\an7}",
        (CaptionPosition.TOP, CaptionTextAlignment.CENTER): r"{\an8}",
        (CaptionPosition.TOP, CaptionTextAlignment.RIGHT): r"{\an9}",
        (CaptionPosition.CENTER, CaptionTextAlignment.LEFT): r"{\an4}",
        (CaptionPosition.CENTER, CaptionTextAlignment.CENTER): r"{\an5}",
        (CaptionPosition.CENTER, CaptionTextAlignment.RIGHT): r"{\an6}",
        (CaptionPosition.BOTTOM, CaptionTextAlignment.LEFT): r"{\an1}",
        (CaptionPosition.BOTTOM, CaptionTextAlignment.CENTER): r"{\an2}",
        (CaptionPosition.BOTTOM, CaptionTextAlignment.RIGHT): r"{\an3}",
    }
    return alignment_map[(position, text_alignment)]


def _emphasize_wrapped_lines(lines: tuple[str, ...], *, emphasis_indices: tuple[int, ...]) -> tuple[str, ...]:
    """Apply deterministic emphasis markup to wrapped lines without altering text timing."""

    emphasis_set = set(emphasis_indices)
    rendered_lines: list[str] = []
    current_word_index = 0
    for line in lines:
        words = line.split(" ")
        rendered_words: list[str] = []
        for word in words:
            escaped_word = _escape_ass_text(word)
            if current_word_index in emphasis_set:
                rendered_words.append(r"{\b1}" + escaped_word + r"{\b0}")
            else:
                rendered_words.append(escaped_word)
            current_word_index += 1
        rendered_lines.append(" ".join(rendered_words))
    return tuple(rendered_lines)


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


def _normalize_wrappable_words(text: str, *, max_chars_per_line: int) -> list[str]:
    """Split long tokens deterministically before line-wrap optimization."""

    words: list[str] = []
    for word in normalize_caption_text(text).split(" "):
        words.extend(_split_long_word(word, max_chars_per_line=max_chars_per_line))
    return words


@lru_cache(maxsize=256)
def _solve_wrapped_lines(
    words: tuple[str, ...],
    *,
    max_chars_per_line: int,
    max_lines: int,
) -> tuple[str, ...] | None:
    """Return the lowest-penalty deterministic line wrapping for one word tuple."""

    if not words:
        return ()

    @lru_cache(maxsize=1024)
    def search(start_index: int, remaining_lines: int) -> tuple[int, tuple[str, ...] | None]:
        if start_index == len(words):
            return 0, ()
        if remaining_lines <= 0:
            return 10**9, None

        best_score = 10**9
        best_lines: tuple[str, ...] | None = None
        line_words: list[str] = []
        for end_index in range(start_index, len(words)):
            line_words.append(words[end_index])
            candidate_line = " ".join(line_words)
            if len(candidate_line) > max_chars_per_line:
                break

            rest_score, rest_lines = search(end_index + 1, remaining_lines - 1)
            if rest_lines is None:
                continue

            candidate_lines = (candidate_line, *rest_lines)
            candidate_score = _wrap_penalty(candidate_lines)
            if candidate_score + rest_score < best_score:
                best_score = candidate_score + rest_score
                best_lines = candidate_lines

        return best_score, best_lines

    _score, best_lines = search(0, max_lines)
    return best_lines


def _wrap_penalty(lines: tuple[str, ...]) -> int:
    """Score one wrapped caption candidate for readable deterministic line balance."""

    line_lengths = [len(line) for line in lines]
    target = sum(line_lengths) / len(line_lengths)
    score = 0
    for line in lines:
        difference = len(line) - target
        score += int(difference * difference)
        if line.endswith((",", ";", ":", "!", "?", ".")):
            score -= 2

    if len(lines) > 1 and len(lines[-1].split(" ")) == 1:
        score += 10
    if len(lines) > 1 and max(line_lengths) - min(line_lengths) > 10:
        score += 6
    return score


def _caption_words(text: str) -> tuple[str, ...]:
    """Split one normalized caption into deterministic word tokens."""

    return tuple(normalize_caption_text(text).split(" "))


def _is_emphasis_candidate(word: str) -> bool:
    """Return whether one caption token is eligible for deterministic emphasis."""

    normalized_word = _normalize_emphasis_word(word)
    return (
        bool(normalized_word)
        and normalized_word not in _EMPHASIS_STOP_WORDS
        and len(normalized_word) >= 4
    )


def _normalize_emphasis_word(word: str) -> str:
    """Normalize one word token for deterministic emphasis scoring."""

    return re.sub(r"(^[^\w]+|[^\w]+$)", "", word.lower())


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
    "determine_emphasized_token_indices",
    "format_ass_timestamp",
    "normalize_caption_text",
    "wrap_caption_text",
]
