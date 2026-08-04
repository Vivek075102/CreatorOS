"""Deterministic mock trend provider for CreatorOS."""

from __future__ import annotations

from creatoros.core import CreatorOSValidationError
from creatoros.domain import generate_id
from creatoros.providers.base import (
    ProviderCapability,
    ProviderRequestContext,
    ProviderResult,
    ProviderUsage,
)
from creatoros.providers.mock.base import MockProviderBase


def _validate_non_blank(value: str, *, field_name: str) -> str:
    """Trim and reject blank textual inputs."""

    normalized_value = value.strip()
    if not normalized_value:
        raise CreatorOSValidationError(
            f"{field_name} must not be blank",
            code="provider_invalid_input",
            details={"field": field_name},
        )
    return normalized_value


def _zero_cost_usage() -> ProviderUsage:
    """Return deterministic zero-cost usage metadata."""

    return ProviderUsage(
        input_units=0,
        output_units=0,
        total_units=0,
        estimated_cost=0.0,
        currency="USD",
    )


class MockTrendProvider(MockProviderBase):
    """Deterministic mock trend provider returning normalized dictionaries."""

    def __init__(
        self,
        *,
        results: list[dict[str, object]] | None = None,
        is_healthy: bool = True,
    ) -> None:
        super().__init__(
            name="mock",
            provider_type="trend",
            capabilities={ProviderCapability.TREND_RESEARCH},
            is_healthy=is_healthy,
        )
        self._results = [
            dict(result) for result in (
                results
                if results is not None
                else [
                    {
                        "title": "Fastest Elden Ring rune farm",
                        "game": "Elden Ring",
                        "topic": "rune farming",
                        "score": 91,
                        "source": "mock_trends",
                    }
                ]
            )
        ]

    async def research_trends(
        self,
        query: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[list[dict[str, object]]]:
        """Return a copied deterministic list of trend dictionaries."""

        _validate_non_blank(query, field_name="query")
        return ProviderResult[list[dict[str, object]]](
            data=[dict(result) for result in self._results],
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )


__all__ = ["MockTrendProvider"]
