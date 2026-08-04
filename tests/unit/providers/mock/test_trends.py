"""Unit tests for the CreatorOS mock trend provider."""

import asyncio

import pytest

from creatoros.core import CreatorOSValidationError
from creatoros.providers.mock import MockTrendProvider


def test_default_results_are_deterministic() -> None:
    """Default trend results should be stable and deterministic."""

    provider = MockTrendProvider()

    result = asyncio.run(provider.research_trends("elden ring"))

    assert result.data[0]["game"] == "Elden Ring"
    assert result.data[0]["source"] == "mock_trends"


def test_blank_query_is_rejected() -> None:
    """Blank trend queries should be rejected."""

    provider = MockTrendProvider()

    with pytest.raises(CreatorOSValidationError):
        asyncio.run(provider.research_trends("   "))


def test_returned_results_are_copies() -> None:
    """Returned trend results should not expose internal mutable state."""

    provider = MockTrendProvider()

    first = asyncio.run(provider.research_trends("elden ring"))
    first.data[0]["title"] = "changed"
    second = asyncio.run(provider.research_trends("elden ring"))

    assert second.data[0]["title"] != "changed"
