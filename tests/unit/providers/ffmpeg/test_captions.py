"""Unit tests for pure FFmpeg caption helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers.ffmpeg.captions import (
    DEFAULT_CAPTION_MAX_CHARS_PER_LINE,
    build_ass_subtitle_document,
    build_subtitles_filter_arg,
    build_timed_captions,
    derive_caption_style,
    format_ass_timestamp,
    normalize_caption_text,
    wrap_caption_text,
)
from creatoros.providers.render import CaptionOverlay, CaptionPosition, RenderScene


def build_scene(
    *,
    scene_number: int,
    duration_seconds: float,
    caption: CaptionOverlay | None,
) -> RenderScene:
    """Create one render scene for pure caption-helper tests."""

    return RenderScene(
        scene_number=scene_number,
        duration_seconds=duration_seconds,
        visual_asset_ref=GeneratedAsset(
            asset_type=AssetType.IMAGE,
            uri=f"mock://generated/image/{scene_number}.png",
        ),
        caption=caption,
    )


def test_normalize_caption_text_trims_and_flattens_whitespace() -> None:
    """Caption normalization should produce deterministic single-line text."""

    assert normalize_caption_text("  Roblox \n funny   myths  ") == "Roblox funny myths"


def test_normalize_caption_text_rejects_blank_values() -> None:
    """Blank caption text should fail validation."""

    with pytest.raises(ValueError):
        normalize_caption_text("   \n  ")


def test_wrap_caption_text_keeps_short_text_on_one_line() -> None:
    """Short captions should not wrap unnecessarily."""

    assert wrap_caption_text("Funny myths", max_chars_per_line=20, max_lines=2) == ("Funny myths",)


def test_wrap_caption_text_wraps_deterministically_at_word_boundaries() -> None:
    """Long captions should wrap consistently across repeated calls."""

    text = "Roblox funny myths players still repeat"

    first = wrap_caption_text(text, max_chars_per_line=16, max_lines=3)
    second = wrap_caption_text(text, max_chars_per_line=16, max_lines=3)

    assert first == second == ("Roblox funny", "myths players", "still repeat")


def test_wrap_caption_text_rejects_overflow_without_silent_truncation() -> None:
    """Captions that cannot fit should fail explicitly."""

    with pytest.raises(ValueError):
        wrap_caption_text("one two three four five six", max_chars_per_line=8, max_lines=2)


def test_wrap_caption_text_splits_overlong_tokens_without_losing_content() -> None:
    """Long single tokens should be split deterministically instead of dropped."""

    assert wrap_caption_text("supercalifragilistic", max_chars_per_line=6, max_lines=4) == (
        "superc",
        "alifra",
        "gilist",
        "ic",
    )


def test_build_timed_captions_accumulates_scene_timeline_and_skips_missing_captions() -> None:
    """Scene captions should map onto one deterministic final timeline."""

    timed_captions = build_timed_captions(
        [
            build_scene(
                scene_number=1,
                duration_seconds=2.0,
                caption=CaptionOverlay(text="Caption one"),
            ),
            build_scene(
                scene_number=2,
                duration_seconds=3.5,
                caption=None,
            ),
            build_scene(
                scene_number=3,
                duration_seconds=4.0,
                caption=CaptionOverlay(text="Caption two", position=CaptionPosition.TOP),
            ),
        ]
    )

    assert len(timed_captions) == 2
    assert timed_captions[0].start_seconds == 0.0
    assert timed_captions[0].end_seconds == 2.0
    assert timed_captions[1].start_seconds == 5.5
    assert timed_captions[1].end_seconds == 9.5
    assert timed_captions[1].position is CaptionPosition.TOP


def test_format_ass_timestamp_is_deterministic() -> None:
    """ASS timestamps should use centisecond precision."""

    assert format_ass_timestamp(65.43) == "0:01:05.43"


def test_build_ass_subtitle_document_is_utf8_safe_and_escapes_ass_control_chars() -> None:
    """ASS output should keep arbitrary text inert as subtitle content."""

    document = build_ass_subtitle_document(
        captions=build_timed_captions(
            [
                build_scene(
                    scene_number=1,
                    duration_seconds=2.0,
                    caption=CaptionOverlay(
                        text=r"Funny {myths} [v1]: 100% \ filter ; , & π",
                        position=CaptionPosition.CENTER,
                    ),
                )
            ]
        ),
        width=1080,
        height=1920,
        font_name="Arial",
        max_chars_per_line=DEFAULT_CAPTION_MAX_CHARS_PER_LINE,
    )

    assert "PlayResY: 1920" in document
    assert r"{\an5}" in document
    assert r"\{" in document
    assert r"\}" in document
    assert "100%" in document
    assert "π" in document


def test_build_subtitles_filter_arg_escapes_local_paths() -> None:
    """Filter arguments should escape local subtitle and font paths safely."""

    filter_arg = build_subtitles_filter_arg(
        subtitle_path=Path("C:/GamingAIFactory/artifacts/run_001/video/.ffmpeg_render_001/captions.ass"),
        fonts_dir=Path("C:/Windows/Fonts"),
    )

    assert filter_arg.startswith("subtitles='C\\:/GamingAIFactory/")
    assert ":fontsdir='C\\:/Windows/Fonts'" in filter_arg


def test_derive_caption_style_scales_with_resolution() -> None:
    """Caption style values should scale sensibly beyond one fixed output size."""

    standard = derive_caption_style(width=1080, height=1920, font_name="Arial")
    smaller = derive_caption_style(width=720, height=1280, font_name="Arial")

    assert standard.font_size >= smaller.font_size
    assert standard.margin_vertical >= smaller.margin_vertical
    assert standard.outline >= 1
