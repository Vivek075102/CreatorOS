"""Base agent framework exports for CreatorOS."""

from creatoros.agents.base import BaseAgent
from creatoros.agents.media import (
    GamingMediaAgent,
    GamingNarrationDirectionRequest,
    GamingSceneMotionPromptRequest,
    GamingSceneVisualPromptRequest,
    GamingThumbnailConceptRequest,
)
from creatoros.agents.models import AgentExecutionContext, AgentResult
from creatoros.agents.research import (
    GamingKeywordExpansionRequest,
    GamingOpportunityEvaluationRequest,
    GamingResearchAgent,
    GamingTrendDiscoveryRequest,
    ResearchExecutionOptions,
)
from creatoros.agents.script import (
    GamingCTAGenerationRequest,
    GamingHookGenerationRequest,
    GamingScriptAgent,
    GamingScriptGenerationRequest,
)
from creatoros.agents.storyboard import (
    GamingStoryboardAgent,
    GamingStoryboardSceneBreakdownRequest,
    GamingStoryboardTimingReviewRequest,
    GamingStoryboardVisualDirectionRequest,
)

__all__ = [
    "AgentExecutionContext",
    "AgentResult",
    "BaseAgent",
    "GamingCTAGenerationRequest",
    "GamingHookGenerationRequest",
    "GamingKeywordExpansionRequest",
    "GamingMediaAgent",
    "GamingNarrationDirectionRequest",
    "GamingOpportunityEvaluationRequest",
    "GamingResearchAgent",
    "GamingSceneMotionPromptRequest",
    "GamingSceneVisualPromptRequest",
    "GamingScriptAgent",
    "GamingScriptGenerationRequest",
    "GamingStoryboardAgent",
    "GamingStoryboardSceneBreakdownRequest",
    "GamingStoryboardTimingReviewRequest",
    "GamingStoryboardVisualDirectionRequest",
    "GamingThumbnailConceptRequest",
    "GamingTrendDiscoveryRequest",
    "ResearchExecutionOptions",
]
