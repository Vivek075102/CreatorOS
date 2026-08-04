"""Unit tests for the CreatorOS mock analytics provider."""

import asyncio

from creatoros.domain import ContentPlatform, PublishedPost
from creatoros.providers.mock import MockAnalyticsProvider


def build_post() -> PublishedPost:
    """Create a simple published post for analytics tests."""

    return PublishedPost(
        platform=ContentPlatform.YOUTUBE_SHORTS,
        external_id="mock_post_123",
        url="mock://published/mock_post_123",
    )


def test_fetch_performance_returns_deterministic_metrics() -> None:
    """Analytics should return deterministic default metrics."""

    provider = MockAnalyticsProvider()

    result = asyncio.run(provider.fetch_performance(build_post()))

    assert result.data.metrics["views"] == 1000
    assert result.data.metrics["likes"] == 125


def test_metrics_are_copied() -> None:
    """Returned metrics should not expose internal mutable state."""

    provider = MockAnalyticsProvider()

    first = asyncio.run(provider.fetch_performance(build_post()))
    first.data.metrics["views"] = 999999
    second = asyncio.run(provider.fetch_performance(build_post()))

    assert second.data.metrics["views"] == 1000


def test_report_links_to_supplied_post() -> None:
    """Performance reports should be linked to the supplied post identifier."""

    provider = MockAnalyticsProvider()
    post = build_post()

    result = asyncio.run(provider.fetch_performance(post))

    assert result.data.post_id == post.id
