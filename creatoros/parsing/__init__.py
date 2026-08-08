"""Provider-independent structured-output parsing foundation for CreatorOS."""

from creatoros.parsing.enums import FieldRequirement, ParseStatus
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
from creatoros.parsing.script import (
    GamingCTAOutput,
    GamingHookOutput,
    YouTubeShortsScriptOutput,
    parse_gaming_cta,
    parse_gaming_hook,
    parse_youtube_shorts_script,
)
from creatoros.parsing.text import normalize_field_label, normalize_model_text

__all__ = [
    "FieldRequirement",
    "GamingCTAOutput",
    "GamingHookOutput",
    "GamingKeywordExpansionOutput",
    "GamingOpportunityEvaluationOutput",
    "GamingTrendDiscoveryOutput",
    "ParseStatus",
    "ParsedField",
    "StructuredFieldSpec",
    "StructuredOutputSpec",
    "StructuredTextParseResult",
    "StructuredTextParser",
    "YouTubeShortsScriptOutput",
    "normalize_field_label",
    "normalize_model_text",
    "parse_gaming_cta",
    "parse_gaming_hook",
    "parse_gaming_keyword_expansion",
    "parse_gaming_opportunity_evaluation",
    "parse_gaming_trend_discovery",
    "parse_into_model",
    "parse_youtube_shorts_script",
]
