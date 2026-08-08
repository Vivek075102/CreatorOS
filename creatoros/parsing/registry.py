"""Provider-independent parser registration and registry helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from creatoros.core import ParserNotFoundError, ParserRegistryError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.media import (
    GamingNarrationDirectionOutput,
    GamingSceneMotionOutput,
    GamingSceneVisualOutput,
    GamingThumbnailConceptOutput,
    parse_gaming_narration_direction,
    parse_gaming_scene_motion,
    parse_gaming_scene_visual,
    parse_gaming_thumbnail_concept,
)
from creatoros.parsing.research import (
    GamingKeywordExpansionOutput,
    GamingOpportunityEvaluationOutput,
    GamingTrendDiscoveryOutput,
    parse_gaming_keyword_expansion,
    parse_gaming_opportunity_evaluation,
    parse_gaming_trend_discovery,
)
from creatoros.parsing.review import (
    GamingEvidenceConsistencyReviewOutput,
    GamingPublicationReadinessReviewOutput,
    GamingScriptQualityReviewOutput,
    GamingStoryboardQualityReviewOutput,
    parse_gaming_evidence_consistency_review,
    parse_gaming_publication_readiness_review,
    parse_gaming_script_quality_review,
    parse_gaming_storyboard_quality_review,
)
from creatoros.parsing.script import (
    GamingCTAOutput,
    GamingHookOutput,
    YouTubeShortsScriptOutput,
    parse_gaming_cta,
    parse_gaming_hook,
    parse_youtube_shorts_script,
)
from creatoros.parsing.storyboard import (
    StoryboardSceneBreakdownOutput,
    StoryboardTimingReviewOutput,
    StoryboardVisualDirectionOutput,
    parse_storyboard_scene_breakdown,
    parse_storyboard_timing_review,
    parse_storyboard_visual_direction,
)
from creatoros.prompts.media import (
    GAMING_NARRATION_DIRECTION,
    GAMING_SCENE_MOTION_PROMPT,
    GAMING_SCENE_VISUAL_PROMPT,
    GAMING_THUMBNAIL_CONCEPT,
)
from creatoros.prompts.research import (
    GAMING_DISCOVER_TRENDS,
    GAMING_EVALUATE_OPPORTUNITY,
    GAMING_EXPAND_KEYWORDS,
)
from creatoros.prompts.review import (
    GAMING_EVIDENCE_CONSISTENCY_REVIEW,
    GAMING_PUBLICATION_READINESS_REVIEW,
    GAMING_SCRIPT_QUALITY_REVIEW,
    GAMING_STORYBOARD_QUALITY_REVIEW,
)
from creatoros.prompts.script import GAMING_CTA, GAMING_HOOK, YOUTUBE_SHORTS_SCRIPT
from creatoros.prompts.storyboard import (
    STORYBOARD_SCENE_BREAKDOWN,
    STORYBOARD_TIMING_REVIEW,
    STORYBOARD_VISUAL_DIRECTION,
)

ParserCallable = Callable[[str], CreatorOSModel]


def _normalize_prompt_name(name: str, *, field_name: str = "prompt_name") -> str:
    """Trim and validate prompt logical names used for registry lookups."""

    normalized_name = name.strip()
    if not normalized_name:
        raise ParserRegistryError(
            f"{field_name} must not be blank",
            code="parser_registration_invalid",
            details={"field_name": field_name},
        )
    return normalized_name


@dataclass(frozen=True, slots=True)
class ParserRegistration:
    """One stable prompt-to-parser registration."""

    prompt_name: str
    parser: ParserCallable
    output_model_type: type[CreatorOSModel]
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate registration fields and isolate mutable metadata."""

        normalized_prompt_name = _normalize_prompt_name(self.prompt_name)
        if not callable(self.parser):
            raise ParserRegistryError(
                "parser must be callable",
                code="parser_registration_invalid",
                details={"prompt_name": normalized_prompt_name},
            )
        if not isinstance(self.output_model_type, type) or not issubclass(
            self.output_model_type,
            CreatorOSModel,
        ):
            raise ParserRegistryError(
                "output_model_type must be a CreatorOSModel subclass",
                code="parser_registration_invalid",
                details={"prompt_name": normalized_prompt_name},
            )

        object.__setattr__(self, "prompt_name", normalized_prompt_name)
        object.__setattr__(self, "metadata", dict(self.metadata))


class ParserRegistry:
    """Store stable parser registrations by prompt logical name."""

    def __init__(self) -> None:
        self._registrations: dict[str, ParserRegistration] = {}

    def register(self, registration: ParserRegistration) -> None:
        """Register one parser by exact stable prompt name."""

        normalized_name = _normalize_prompt_name(registration.prompt_name)
        if normalized_name.casefold() in self._registrations:
            raise ParserRegistryError(
                f"Parser '{registration.prompt_name}' is already registered",
                code="parser_registry_duplicate",
                details={"prompt_name": registration.prompt_name},
            )

        self._registrations[normalized_name.casefold()] = ParserRegistration(
            prompt_name=registration.prompt_name,
            parser=registration.parser,
            output_model_type=registration.output_model_type,
            metadata=registration.metadata,
        )

    def resolve(self, prompt_name: str) -> ParserRegistration:
        """Return a detached registration for one stable prompt name."""

        normalized_name = _normalize_prompt_name(prompt_name)
        registration = self._registrations.get(normalized_name.casefold())
        if registration is None:
            raise ParserNotFoundError(normalized_name)
        return ParserRegistration(
            prompt_name=registration.prompt_name,
            parser=registration.parser,
            output_model_type=registration.output_model_type,
            metadata=registration.metadata,
        )

    def contains(self, prompt_name: str) -> bool:
        """Return whether a prompt name has a registered parser."""

        normalized_name = _normalize_prompt_name(prompt_name)
        return normalized_name.casefold() in self._registrations

    def list_prompt_names(self) -> tuple[str, ...]:
        """Return deterministic stable prompt names without exposing internal state."""

        registrations = sorted(
            self._registrations.values(),
            key=lambda registration: registration.prompt_name.casefold(),
        )
        return tuple(registration.prompt_name for registration in registrations)

    def parse(self, prompt_name: str, text: str) -> CreatorOSModel:
        """Parse raw provider text using the registered parser for one prompt."""

        registration = self.resolve(prompt_name)
        parsed = registration.parser(text)
        if not isinstance(parsed, registration.output_model_type):
            raise ParserRegistryError(
                "registered parser returned an unexpected output model type",
                code="parser_registration_invalid",
                details={
                    "prompt_name": registration.prompt_name,
                    "expected_output_model_type": registration.output_model_type.__name__,
                },
            )
        return parsed


def create_parser_registry() -> ParserRegistry:
    """Return a fresh empty parser registry."""

    return ParserRegistry()


def build_builtin_parser_registry() -> ParserRegistry:
    """Create a fresh parser registry with all builtin parser registrations."""

    registry = create_parser_registry()
    registrations = (
        ParserRegistration(
            prompt_name=GAMING_DISCOVER_TRENDS,
            parser=parse_gaming_trend_discovery,
            output_model_type=GamingTrendDiscoveryOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_EVALUATE_OPPORTUNITY,
            parser=parse_gaming_opportunity_evaluation,
            output_model_type=GamingOpportunityEvaluationOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_EXPAND_KEYWORDS,
            parser=parse_gaming_keyword_expansion,
            output_model_type=GamingKeywordExpansionOutput,
        ),
        ParserRegistration(
            prompt_name=YOUTUBE_SHORTS_SCRIPT,
            parser=parse_youtube_shorts_script,
            output_model_type=YouTubeShortsScriptOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_HOOK,
            parser=parse_gaming_hook,
            output_model_type=GamingHookOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_CTA,
            parser=parse_gaming_cta,
            output_model_type=GamingCTAOutput,
        ),
        ParserRegistration(
            prompt_name=STORYBOARD_SCENE_BREAKDOWN,
            parser=parse_storyboard_scene_breakdown,
            output_model_type=StoryboardSceneBreakdownOutput,
        ),
        ParserRegistration(
            prompt_name=STORYBOARD_VISUAL_DIRECTION,
            parser=parse_storyboard_visual_direction,
            output_model_type=StoryboardVisualDirectionOutput,
        ),
        ParserRegistration(
            prompt_name=STORYBOARD_TIMING_REVIEW,
            parser=parse_storyboard_timing_review,
            output_model_type=StoryboardTimingReviewOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_SCENE_VISUAL_PROMPT,
            parser=parse_gaming_scene_visual,
            output_model_type=GamingSceneVisualOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_SCENE_MOTION_PROMPT,
            parser=parse_gaming_scene_motion,
            output_model_type=GamingSceneMotionOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_THUMBNAIL_CONCEPT,
            parser=parse_gaming_thumbnail_concept,
            output_model_type=GamingThumbnailConceptOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_NARRATION_DIRECTION,
            parser=parse_gaming_narration_direction,
            output_model_type=GamingNarrationDirectionOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_SCRIPT_QUALITY_REVIEW,
            parser=parse_gaming_script_quality_review,
            output_model_type=GamingScriptQualityReviewOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_EVIDENCE_CONSISTENCY_REVIEW,
            parser=parse_gaming_evidence_consistency_review,
            output_model_type=GamingEvidenceConsistencyReviewOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_STORYBOARD_QUALITY_REVIEW,
            parser=parse_gaming_storyboard_quality_review,
            output_model_type=GamingStoryboardQualityReviewOutput,
        ),
        ParserRegistration(
            prompt_name=GAMING_PUBLICATION_READINESS_REVIEW,
            parser=parse_gaming_publication_readiness_review,
            output_model_type=GamingPublicationReadinessReviewOutput,
        ),
    )
    for registration in registrations:
        registry.register(registration)
    return registry


@lru_cache(maxsize=1)
def get_builtin_parser_registry() -> ParserRegistry:
    """Return the cached builtin parser registry."""

    return build_builtin_parser_registry()


__all__ = [
    "ParserCallable",
    "ParserRegistration",
    "ParserRegistry",
    "build_builtin_parser_registry",
    "create_parser_registry",
    "get_builtin_parser_registry",
]
