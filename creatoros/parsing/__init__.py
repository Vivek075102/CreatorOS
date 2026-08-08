"""Provider-independent structured-output parsing foundation for CreatorOS."""

from creatoros.parsing.enums import FieldRequirement, ParseStatus
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
from creatoros.parsing.models import (
    ParsedField,
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)
from creatoros.parsing.parser import StructuredTextParser, parse_into_model
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
    StoryboardScenePlan,
    StoryboardTimingReviewOutput,
    StoryboardVisualDirectionOutput,
    parse_storyboard_scene_breakdown,
    parse_storyboard_timing_review,
    parse_storyboard_visual_direction,
)
from creatoros.parsing.text import normalize_field_label, normalize_model_text

__all__ = [
    "FieldRequirement",
    "GamingCTAOutput",
    "GamingEvidenceConsistencyReviewOutput",
    "GamingHookOutput",
    "GamingKeywordExpansionOutput",
    "GamingNarrationDirectionOutput",
    "GamingOpportunityEvaluationOutput",
    "GamingPublicationReadinessReviewOutput",
    "GamingSceneMotionOutput",
    "GamingSceneVisualOutput",
    "GamingScriptQualityReviewOutput",
    "GamingStoryboardQualityReviewOutput",
    "GamingThumbnailConceptOutput",
    "GamingTrendDiscoveryOutput",
    "ParseStatus",
    "ParsedField",
    "StoryboardSceneBreakdownOutput",
    "StoryboardScenePlan",
    "StoryboardTimingReviewOutput",
    "StoryboardVisualDirectionOutput",
    "StructuredFieldSpec",
    "StructuredOutputSpec",
    "StructuredTextParseResult",
    "StructuredTextParser",
    "YouTubeShortsScriptOutput",
    "normalize_field_label",
    "normalize_model_text",
    "parse_gaming_cta",
    "parse_gaming_evidence_consistency_review",
    "parse_gaming_hook",
    "parse_gaming_keyword_expansion",
    "parse_gaming_narration_direction",
    "parse_gaming_opportunity_evaluation",
    "parse_gaming_publication_readiness_review",
    "parse_gaming_scene_motion",
    "parse_gaming_scene_visual",
    "parse_gaming_script_quality_review",
    "parse_gaming_storyboard_quality_review",
    "parse_gaming_thumbnail_concept",
    "parse_gaming_trend_discovery",
    "parse_into_model",
    "parse_storyboard_scene_breakdown",
    "parse_storyboard_timing_review",
    "parse_storyboard_visual_direction",
    "parse_youtube_shorts_script",
]
