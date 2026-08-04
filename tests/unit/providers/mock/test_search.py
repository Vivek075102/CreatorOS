"""Unit tests for the CreatorOS mock search provider."""

import asyncio

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.providers.mock import MockSearchProvider


def test_blank_query_is_rejected() -> None:
    """Blank search queries should be rejected."""

    provider = MockSearchProvider()

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(provider.search("   "))


def test_non_positive_limits_are_rejected() -> None:
    """Search limits must be positive."""

    provider = MockSearchProvider()

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(provider.search("elden ring", limit=0))


def test_result_count_respects_limit() -> None:
    """Search results should be truncated to the requested limit."""

    provider = MockSearchProvider()

    result = asyncio.run(provider.search("elden ring", limit=1))

    assert len(result.data) == 1


def test_returned_results_are_copies() -> None:
    """Returned search results should not expose internal mutable state."""

    provider = MockSearchProvider()

    first = asyncio.run(provider.search("elden ring"))
    first.data[0]["title"] = "changed"
    second = asyncio.run(provider.search("elden ring"))

    assert second.data[0]["title"] != "changed"
