"""Deterministic mock analytics provider for CreatorOS."""

from __future__ import annotations

from creatoros.domain import PerformanceReport, PublishedPost, generate_id
from creatoros.providers.base import (
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.mock.base import MockProviderBase


def _zero_cost_usage() -> ProviderUsage:
    """Return deterministic zero-cost usage metadata."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


class MockAnalyticsProvider(MockProviderBase):
    """Deterministic analytics provider returning copied metric payloads."""

    def __init__(
        self,
        *,
        metrics: dict[str, object] | None = None,
        is_healthy: bool = True,
    ) -> None:
        super().__init__(
            name="mock",
            provider_type="analytics",
            capabilities={ProviderCapability.ANALYTICS},
            is_healthy=is_healthy,
        )
        self._metrics = dict(
            metrics
            if metrics is not None
            else {
                "views": 1000,
                "likes": 125,
                "comments": 18,
                "average_view_duration_seconds": 22.5,
                "click_through_rate": 0.074,
            }
        )

    async def fetch_performance(
        self,
        post: PublishedPost,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[PerformanceReport]:
        """Return a deterministic performance report linked to the supplied post."""

        report = PerformanceReport(post_id=post.id, metrics=dict(self._metrics))
        return ProviderResult[PerformanceReport](
            data=report,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )


__all__ = ["MockAnalyticsProvider"]
