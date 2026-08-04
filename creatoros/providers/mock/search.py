"""Deterministic mock search provider for CreatorOS."""

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


class MockSearchProvider(MockProviderBase):
    """Deterministic mock search provider returning copied result dictionaries."""

    def __init__(
        self,
        *,
        results: list[dict[str, object]] | None = None,
        is_healthy: bool = True,
    ) -> None:
        super().__init__(
            name="mock",
            provider_type="search",
            capabilities={ProviderCapability.WEB_SEARCH},
            is_healthy=is_healthy,
        )
        self._results = [
            dict(result) for result in (
                results
                if results is not None
                else [
                    {
                        "title": "Elden Ring rune farm guide",
                        "url": "mock://search/elden-ring-rune-farm",
                        "snippet": "Deterministic mock result.",
                    },
                    {
                        "title": "Top rune farm locations",
                        "url": "mock://search/top-rune-farm-locations",
                        "snippet": "Another deterministic mock result.",
                    },
                ]
            )
        ]

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[list[dict[str, object]]]:
        """Return copied deterministic search results up to the requested limit."""

        _validate_non_blank(query, field_name="query")
        if limit <= 0:
            raise CreatorOSValidationError(
                "limit must be greater than zero",
                code="provider_invalid_input",
                details={"field": "limit"},
            )

        return ProviderResult[list[dict[str, object]]](
            data=[dict(result) for result in self._results[:limit]],
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )


__all__ = ["MockSearchProvider"]
