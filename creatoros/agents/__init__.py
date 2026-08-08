"""Base agent framework exports for CreatorOS."""

from creatoros.agents.base import BaseAgent
from creatoros.agents.models import AgentExecutionContext, AgentResult
from creatoros.agents.research import (
    GamingKeywordExpansionRequest,
    GamingOpportunityEvaluationRequest,
    GamingResearchAgent,
    GamingTrendDiscoveryRequest,
    ResearchExecutionOptions,
)

__all__ = [
    "AgentExecutionContext",
    "AgentResult",
    "BaseAgent",
    "GamingKeywordExpansionRequest",
    "GamingOpportunityEvaluationRequest",
    "GamingResearchAgent",
    "GamingTrendDiscoveryRequest",
    "ResearchExecutionOptions",
]
