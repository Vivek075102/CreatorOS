"""Unit tests for the CreatorOS parser registry."""

from __future__ import annotations

import builtins
import importlib
from pathlib import Path

import pytest

from creatoros.core import ParserNotFoundError, ParserRegistryError
from creatoros.domain import CreatorOSModel
from creatoros.parsing import (
    GamingCTAOutput,
    GamingEvidenceConsistencyReviewOutput,
    GamingHookOutput,
    GamingKeywordExpansionOutput,
    GamingNarrationDirectionOutput,
    GamingOpportunityEvaluationOutput,
    GamingPublicationReadinessReviewOutput,
    GamingSceneMotionOutput,
    GamingSceneVisualOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    GamingThumbnailConceptOutput,
    GamingTrendDiscoveryOutput,
    ParserRegistration,
    StoryboardSceneBreakdownOutput,
    StoryboardTimingReviewOutput,
    StoryboardVisualDirectionOutput,
    YouTubeShortsScriptOutput,
    build_builtin_parser_registry,
    create_parser_registry,
    get_builtin_parser_registry,
)
from creatoros.prompts import (
    GAMING_CTA,
    GAMING_DISCOVER_TRENDS,
    GAMING_EVALUATE_OPPORTUNITY,
    GAMING_EVIDENCE_CONSISTENCY_REVIEW,
    GAMING_EXPAND_KEYWORDS,
    GAMING_HOOK,
    GAMING_NARRATION_DIRECTION,
    GAMING_PUBLICATION_READINESS_REVIEW,
    GAMING_SCENE_MOTION_PROMPT,
    GAMING_SCENE_VISUAL_PROMPT,
    GAMING_SCRIPT_QUALITY_REVIEW,
    GAMING_STORYBOARD_QUALITY_REVIEW,
    GAMING_THUMBNAIL_CONCEPT,
    STORYBOARD_SCENE_BREAKDOWN,
    STORYBOARD_TIMING_REVIEW,
    STORYBOARD_VISUAL_DIRECTION,
    YOUTUBE_SHORTS_SCRIPT,
)


class FakeOutput(CreatorOSModel):
    """Minimal output model for parser registry tests."""

    value: str


class WrongOutput(CreatorOSModel):
    """A different output type used to validate mismatch handling."""

    value: str


def build_registration(
    *,
    prompt_name: str = "test_prompt",
    parser=None,
    output_model_type: type[CreatorOSModel] = FakeOutput,
    metadata: dict[str, object] | None = None,
) -> ParserRegistration:
    """Build a reusable parser registration fixture."""

    active_parser = parser or (lambda text: FakeOutput(value=text.strip()))
    return ParserRegistration(
        prompt_name=prompt_name,
        parser=active_parser,
        output_model_type=output_model_type,
        metadata={} if metadata is None else metadata,
    )


@pytest.fixture(autouse=True)
def clear_cached_builtin_registry() -> None:
    """Reset the cached builtin parser registry between tests."""

    get_builtin_parser_registry.cache_clear()


def test_valid_parser_registration_can_be_created() -> None:
    """A valid parser registration should preserve supplied fields."""

    registration = build_registration(metadata={"family": "test"})

    assert registration.prompt_name == "test_prompt"
    assert registration.output_model_type is FakeOutput
    assert registration.metadata == {"family": "test"}


def test_blank_prompt_name_is_rejected() -> None:
    """Blank prompt names should fail validation safely."""

    with pytest.raises(ParserRegistryError) as exc_info:
        build_registration(prompt_name="   ")

    assert exc_info.value.code == "parser_registration_invalid"


def test_non_callable_parser_is_rejected() -> None:
    """Non-callable parser values should fail validation safely."""

    with pytest.raises(ParserRegistryError) as exc_info:
        ParserRegistration(
            prompt_name="test_prompt",
            parser="not callable",  # type: ignore[arg-type]
            output_model_type=FakeOutput,
        )

    assert exc_info.value.code == "parser_registration_invalid"


def test_invalid_output_model_type_is_rejected() -> None:
    """Only CreatorOSModel subclasses should be accepted as output model types."""

    with pytest.raises(ParserRegistryError) as exc_info:
        ParserRegistration(
            prompt_name="test_prompt",
            parser=lambda text: text,
            output_model_type=str,  # type: ignore[arg-type]
        )

    assert exc_info.value.code == "parser_registration_invalid"


def test_registration_metadata_defaults_are_isolated() -> None:
    """Registration metadata defaults should not be shared accidentally."""

    first = build_registration()
    second = build_registration(prompt_name="other_prompt")
    first.metadata["owner"] = "one"

    assert second.metadata == {}


def test_register_and_resolve_work() -> None:
    """A registered parser should resolve by prompt name."""

    registry = create_parser_registry()
    registration = build_registration()
    registry.register(registration)

    resolved = registry.resolve(" test_prompt ")

    assert resolved == registration
    assert resolved is not registration


def test_contains_works() -> None:
    """Contains should report whether a prompt parser is registered."""

    registry = create_parser_registry()
    registry.register(build_registration())

    assert registry.contains("test_prompt") is True
    assert registry.contains("missing_prompt") is False


def test_list_prompt_names_is_deterministic() -> None:
    """Prompt-name listings should be sorted predictably."""

    registry = create_parser_registry()
    registry.register(build_registration(prompt_name="zeta_prompt"))
    registry.register(build_registration(prompt_name="alpha_prompt"))

    assert registry.list_prompt_names() == ("alpha_prompt", "zeta_prompt")


def test_duplicate_registration_is_rejected() -> None:
    """Duplicate prompt names should not be allowed."""

    registry = create_parser_registry()
    registry.register(build_registration())

    with pytest.raises(ParserRegistryError) as exc_info:
        registry.register(build_registration())

    assert exc_info.value.code == "parser_registry_duplicate"


def test_duplicate_registration_does_not_overwrite_original() -> None:
    """Rejected duplicates should leave the original registration unchanged."""

    registry = create_parser_registry()
    first = build_registration(metadata={"version": "first"})
    second = build_registration(metadata={"version": "second"})
    registry.register(first)

    with pytest.raises(ParserRegistryError):
        registry.register(second)

    assert registry.resolve("test_prompt").metadata == {"version": "first"}


def test_unknown_resolve_fails_safely() -> None:
    """Resolving an unknown parser should raise ParserNotFoundError."""

    registry = create_parser_registry()

    with pytest.raises(ParserNotFoundError) as exc_info:
        registry.resolve("missing_prompt")

    assert exc_info.value.code == "parser_not_found"


def test_parse_invokes_the_registered_parser() -> None:
    """Parse should call the resolved parser with the supplied text."""

    seen: list[str] = []

    def parser(text: str) -> FakeOutput:
        seen.append(text)
        return FakeOutput(value=text)

    registry = create_parser_registry()
    registry.register(build_registration(parser=parser))

    parsed = registry.parse("test_prompt", "hello")

    assert parsed == FakeOutput(value="hello")
    assert seen == ["hello"]


def test_parse_returns_a_typed_model() -> None:
    """Parse should return the declared typed output model."""

    registry = create_parser_registry()
    registry.register(build_registration())

    parsed = registry.parse("test_prompt", "hello")

    assert isinstance(parsed, FakeOutput)


def test_parser_return_type_mismatch_is_rejected_safely() -> None:
    """Registry parse should fail if a parser violates its output contract."""

    secret_text = "sensitive raw model output"
    registry = create_parser_registry()
    registry.register(
        build_registration(
            parser=lambda text: WrongOutput(value=text),
            output_model_type=FakeOutput,
        )
    )

    with pytest.raises(ParserRegistryError) as exc_info:
        registry.parse("test_prompt", secret_text)

    assert exc_info.value.code == "parser_registration_invalid"
    assert secret_text not in str(exc_info.value)
    assert secret_text not in repr(exc_info.value.details)


def test_parse_does_not_mutate_registry() -> None:
    """Parsing should not alter registry state."""

    registry = create_parser_registry()
    registry.register(build_registration())
    before = registry.list_prompt_names()

    registry.parse("test_prompt", "hello")

    assert registry.list_prompt_names() == before


def test_resolve_does_not_mutate_registry() -> None:
    """Resolving should not alter registry state."""

    registry = create_parser_registry()
    registry.register(build_registration())
    before = registry.list_prompt_names()

    registry.resolve("test_prompt")

    assert registry.list_prompt_names() == before


def test_caller_text_remains_unchanged() -> None:
    """Parse should not mutate the caller-provided text value."""

    registry = create_parser_registry()
    registry.register(build_registration(parser=lambda text: FakeOutput(value=text)))
    text = "  keep original text  "

    registry.parse("test_prompt", text)

    assert text == "  keep original text  "


def test_builtin_registry_contains_exactly_seventeen_registrations() -> None:
    """The builtin parser registry should cover all current builtin prompt assets."""

    registry = build_builtin_parser_registry()

    assert len(registry.list_prompt_names()) == 17


def test_builtin_registry_contains_all_research_prompt_names() -> None:
    """Research prompt logical names should all be registered."""

    registry = build_builtin_parser_registry()

    assert registry.contains(GAMING_DISCOVER_TRENDS) is True
    assert registry.contains(GAMING_EVALUATE_OPPORTUNITY) is True
    assert registry.contains(GAMING_EXPAND_KEYWORDS) is True


def test_builtin_registry_contains_all_script_prompt_names() -> None:
    """Script prompt logical names should all be registered."""

    registry = build_builtin_parser_registry()

    assert registry.contains(YOUTUBE_SHORTS_SCRIPT) is True
    assert registry.contains(GAMING_HOOK) is True
    assert registry.contains(GAMING_CTA) is True


def test_builtin_registry_contains_all_storyboard_prompt_names() -> None:
    """Storyboard-family prompt logical names should all be registered."""

    registry = build_builtin_parser_registry()

    assert registry.contains(STORYBOARD_SCENE_BREAKDOWN) is True
    assert registry.contains(STORYBOARD_VISUAL_DIRECTION) is True
    assert registry.contains(STORYBOARD_TIMING_REVIEW) is True
    assert registry.contains(GAMING_SCENE_VISUAL_PROMPT) is True
    assert registry.contains(GAMING_SCENE_MOTION_PROMPT) is True


def test_builtin_registry_contains_all_media_prompt_names() -> None:
    """Media-family prompt logical names should all be registered."""

    registry = build_builtin_parser_registry()

    assert registry.contains(GAMING_THUMBNAIL_CONCEPT) is True
    assert registry.contains(GAMING_NARRATION_DIRECTION) is True


def test_builtin_registry_contains_all_review_prompt_names() -> None:
    """Review prompt logical names should all be registered."""

    registry = build_builtin_parser_registry()

    assert registry.contains(GAMING_SCRIPT_QUALITY_REVIEW) is True
    assert registry.contains(GAMING_EVIDENCE_CONSISTENCY_REVIEW) is True
    assert registry.contains(GAMING_STORYBOARD_QUALITY_REVIEW) is True
    assert registry.contains(GAMING_PUBLICATION_READINESS_REVIEW) is True


def test_each_builtin_registration_has_the_expected_output_model() -> None:
    """Each builtin prompt should map to the expected typed output model."""

    registry = build_builtin_parser_registry()
    expected = {
        GAMING_DISCOVER_TRENDS: GamingTrendDiscoveryOutput,
        GAMING_EVALUATE_OPPORTUNITY: GamingOpportunityEvaluationOutput,
        GAMING_EXPAND_KEYWORDS: GamingKeywordExpansionOutput,
        YOUTUBE_SHORTS_SCRIPT: YouTubeShortsScriptOutput,
        GAMING_HOOK: GamingHookOutput,
        GAMING_CTA: GamingCTAOutput,
        STORYBOARD_SCENE_BREAKDOWN: StoryboardSceneBreakdownOutput,
        STORYBOARD_VISUAL_DIRECTION: StoryboardVisualDirectionOutput,
        STORYBOARD_TIMING_REVIEW: StoryboardTimingReviewOutput,
        GAMING_SCENE_VISUAL_PROMPT: GamingSceneVisualOutput,
        GAMING_SCENE_MOTION_PROMPT: GamingSceneMotionOutput,
        GAMING_THUMBNAIL_CONCEPT: GamingThumbnailConceptOutput,
        GAMING_NARRATION_DIRECTION: GamingNarrationDirectionOutput,
        GAMING_SCRIPT_QUALITY_REVIEW: GamingScriptQualityReviewOutput,
        GAMING_EVIDENCE_CONSISTENCY_REVIEW: GamingEvidenceConsistencyReviewOutput,
        GAMING_STORYBOARD_QUALITY_REVIEW: GamingStoryboardQualityReviewOutput,
        GAMING_PUBLICATION_READINESS_REVIEW: GamingPublicationReadinessReviewOutput,
    }

    for prompt_name, output_model_type in expected.items():
        assert registry.resolve(prompt_name).output_model_type is output_model_type


def test_builtin_names_are_deterministic() -> None:
    """Builtin prompt-name ordering should be stable."""

    registry = build_builtin_parser_registry()

    assert registry.list_prompt_names() == tuple(sorted(registry.list_prompt_names()))


def test_cached_builtin_registry_returns_the_same_instance() -> None:
    """The cached builtin parser registry accessor should be stable."""

    first = get_builtin_parser_registry()
    second = get_builtin_parser_registry()

    assert first is second


def test_rebuilding_builtin_registry_produces_equivalent_registrations() -> None:
    """Fresh builtin registry builds should be equivalent by public behavior."""

    first = build_builtin_parser_registry()
    second = build_builtin_parser_registry()

    assert first.list_prompt_names() == second.list_prompt_names()
    for prompt_name in first.list_prompt_names():
        assert first.resolve(prompt_name) == second.resolve(prompt_name)


def test_builtin_registry_requires_no_provider_imports() -> None:
    """Parser registry loading should not import provider modules."""

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name.startswith("creatoros.providers"):
            raise AssertionError("provider imports are not expected")
        return original_import(name, globals, locals, fromlist, level)

    module = importlib.import_module("creatoros.parsing.registry")
    try:
        builtins.__import__ = guarded_import
        importlib.reload(module)
    finally:
        builtins.__import__ = original_import


def test_building_builtin_registry_does_not_execute_parsers() -> None:
    """Creating the builtin registry should only register callables, not execute them."""

    import creatoros.parsing.registry as parsing_registry_module

    original_parser = parsing_registry_module.parse_gaming_trend_discovery
    parsing_registry_module.parse_gaming_trend_discovery = lambda text: (_ for _ in ()).throw(AssertionError("called"))
    try:
        registry = parsing_registry_module.build_builtin_parser_registry()
    finally:
        parsing_registry_module.parse_gaming_trend_discovery = original_parser

    assert registry.contains(GAMING_DISCOVER_TRENDS) is True


def test_returned_prompt_name_collections_cannot_corrupt_cached_global_state() -> None:
    """Returned name collections should be detached from cached global state."""

    registry = get_builtin_parser_registry()
    names = list(registry.list_prompt_names())
    names.append("corrupted")

    assert "corrupted" not in registry.list_prompt_names()


def test_registry_module_source_mentions_no_provider_imports() -> None:
    """The parser registry module should stay provider-independent."""

    source = Path("creatoros/parsing/registry.py").read_text(encoding="utf-8")

    assert "creatoros.providers" not in source
