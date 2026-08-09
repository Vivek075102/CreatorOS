"""Unit tests for pure FFmpeg caption helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers.ffmpeg.captions import (
    DEFAULT_CAPTION_MAX_CHARS_PER_LINE,
    build_ass_subtitle_document,
    build_subtitles_filter_arg,
    build_timed_captions,
    derive_caption_style,
    determine_emphasized_token_indices,
    format_ass_timestamp,
    normalize_caption_text,
    wrap_caption_text,
)
from creatoros.providers.render import (
    CaptionEmphasis,
    CaptionFontSizeProfile,
    CaptionOverlay,
    CaptionPosition,
    CaptionSafeMarginProfile,
    CaptionStylePolicy,
    CaptionTextAlignment,
    ProductionTimelineScene,
)


def build_scene(
    *,
    scene_number: int,
    start_seconds: float,
    duration_seconds: float,
    caption: CaptionOverlay | None,
) -> ProductionTimelineScene:
    """Create one render scene for pure caption-helper tests."""

    return ProductionTimelineScene(
        scene_number=scene_number,
        start_seconds=start_seconds,
        end_seconds=round(start_seconds + duration_seconds, 6),
        duration_seconds=duration_seconds,
        source_asset_ref=GeneratedAsset(
            asset_type=AssetType.IMAGE,
            uri=f"mock://generated/image/{scene_number}.png",
        ),
        caption_text=None if caption is None else caption.text,
        caption_position=CaptionPosition.BOTTOM if caption is None else caption.position,
        caption_max_lines=2 if caption is None else caption.max_lines,
        caption_style=CaptionStylePolicy() if caption is None else caption.style,
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


def test_wrap_caption_text_avoids_orphan_single_word_when_possible() -> None:
    """Wrapping should avoid a trailing orphan single word when a better fit exists."""

    assert wrap_caption_text("Roblox myths spread really fast", max_chars_per_line=18, max_lines=2) == (
        "Roblox myths",
        "spread really fast",
    )


def test_wrap_caption_text_prefers_punctuation_aware_breaks_when_possible() -> None:
    """Wrapping should prefer punctuation-friendly breaks when they fit safely."""

    assert wrap_caption_text("Roblox myths: fake secrets linger", max_chars_per_line=22, max_lines=2) == (
        "Roblox myths: fake",
        "secrets linger",
    )


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


def test_deterministic_keyword_emphasis_is_bounded_and_repeatable() -> None:
    """Keyword emphasis should be deterministic and should not emphasize every word."""

    text = "Roblox hidden myths confuse veteran players"

    first = determine_emphasized_token_indices(text, emphasis=CaptionEmphasis.KEYWORD)
    second = determine_emphasized_token_indices(text, emphasis=CaptionEmphasis.KEYWORD)

    assert first == second
    assert 1 <= len(first) <= 2


def test_punctuation_only_and_stopword_only_captions_have_no_emphasis() -> None:
    """Unsafe or meaningless emphasis candidates should be ignored."""

    assert determine_emphasized_token_indices("!!! ???", emphasis=CaptionEmphasis.KEYWORD) == ()
    assert determine_emphasized_token_indices("the and for with", emphasis=CaptionEmphasis.KEYWORD) == ()


def test_active_phrase_emphasis_prefers_adjacent_meaningful_words() -> None:
    """Active-phrase emphasis should select a short deterministic phrase."""

    emphasized = determine_emphasized_token_indices(
        "Roblox secret bosses shock veteran players",
        emphasis=CaptionEmphasis.ACTIVE_PHRASE,
    )

    assert len(emphasized) == 2
    assert emphasized[1] == emphasized[0] + 1


def test_build_timed_captions_accumulates_scene_timeline_and_skips_missing_captions() -> None:
    """Scene captions should map onto one deterministic final timeline."""

    timed_captions = build_timed_captions(
        [
            build_scene(
                scene_number=1,
                start_seconds=0.0,
                duration_seconds=2.0,
                caption=CaptionOverlay(text="Caption one"),
            ),
            build_scene(
                scene_number=2,
                start_seconds=2.0,
                duration_seconds=3.5,
                caption=None,
            ),
            build_scene(
                scene_number=3,
                start_seconds=5.5,
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
                    start_seconds=0.0,
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


def test_build_ass_subtitle_document_applies_keyword_emphasis_safely() -> None:
    """ASS output should render deterministic emphasis without exposing raw control injection."""

    document = build_ass_subtitle_document(
        captions=build_timed_captions(
            [
                build_scene(
                    scene_number=1,
                    start_seconds=0.0,
                    duration_seconds=2.0,
                    caption=CaptionOverlay(
                        text="Roblox secret bosses",
                        style=CaptionStylePolicy(emphasis=CaptionEmphasis.KEYWORD),
                    ),
                )
            ]
        ),
        width=1080,
        height=1920,
        font_name="Arial",
    )

    assert r"{\b1}" in document
    assert r"{\b0}" in document


def test_build_subtitles_filter_arg_escapes_local_paths() -> None:
    """Filter arguments should escape local subtitle and font paths safely."""

    filter_arg = build_subtitles_filter_arg(
        subtitle_path=Path("C:/GamingAIFactory/artifacts/run_001/video/.ffmpeg_render_001/captions.ass"),
        fonts_dir=Path("C:/Windows/Fonts"),
    )

    assert filter_arg.startswith("subtitles='C\\:/GamingAIFactory/")
    assert ":fontsdir='C\\:/Windows/Fonts'" in filter_arg


def test_default_caption_style_policy_is_valid() -> None:
    """The provider-neutral caption-style default should be stable and valid."""

    style = CaptionStylePolicy()

    assert style.emphasis is CaptionEmphasis.NONE
    assert style.font_size_profile is CaptionFontSizeProfile.STANDARD
    assert style.text_alignment is CaptionTextAlignment.CENTER
    assert style.safe_margin_profile is CaptionSafeMarginProfile.COMFORTABLE


def test_unsupported_caption_emphasis_is_rejected() -> None:
    """Only supported provider-neutral emphasis modes should be accepted."""

    with pytest.raises(ValidationError):
        CaptionStylePolicy(emphasis="flash")  # type: ignore[arg-type]


def test_derive_caption_style_scales_with_resolution() -> None:
    """Caption style values should scale sensibly beyond one fixed output size."""

    standard = derive_caption_style(width=1080, height=1920, font_name="Arial")
    smaller = derive_caption_style(width=720, height=1280, font_name="Arial")

    assert standard.font_size >= smaller.font_size
    assert standard.margin_vertical >= smaller.margin_vertical
    assert standard.outline >= 1


def test_derive_caption_style_respects_safe_area_profiles_and_positions() -> None:
    """Derived ASS margins should vary safely across positions and safe-area profiles."""

    bottom = derive_caption_style(
        width=1080,
        height=1920,
        font_name="Arial",
        style_policy=CaptionStylePolicy(safe_margin_profile=CaptionSafeMarginProfile.COMFORTABLE),
        position=CaptionPosition.BOTTOM,
    )
    top = derive_caption_style(
        width=1080,
        height=1920,
        font_name="Arial",
        style_policy=CaptionStylePolicy(safe_margin_profile=CaptionSafeMarginProfile.COMFORTABLE),
        position=CaptionPosition.TOP,
    )
    tight = derive_caption_style(
        width=1080,
        height=1920,
        font_name="Arial",
        style_policy=CaptionStylePolicy(safe_margin_profile=CaptionSafeMarginProfile.TIGHT),
        position=CaptionPosition.BOTTOM,
    )

    assert bottom.margin_vertical > top.margin_vertical
    assert tight.margin_vertical < bottom.margin_vertical


def test_large_font_profile_increases_font_size() -> None:
    """The large font-size profile should increase derived font size deterministically."""

    standard = derive_caption_style(
        width=1080,
        height=1920,
        font_name="Arial",
        style_policy=CaptionStylePolicy(font_size_profile=CaptionFontSizeProfile.STANDARD),
    )
    large = derive_caption_style(
        width=1080,
        height=1920,
        font_name="Arial",
        style_policy=CaptionStylePolicy(font_size_profile=CaptionFontSizeProfile.LARGE),
    )

    assert large.font_size > standard.font_size
