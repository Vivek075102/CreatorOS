"""Deterministic mock publishing provider for CreatorOS."""

from __future__ import annotations

from creatoros.core import CreatorOSValidationError, ProviderNotFoundError
from creatoros.domain import PublishedPost, PublishingPackage, generate_id
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


class MockPublishingProvider(MockProviderBase):
    """Deterministic in-memory publishing provider for local testing."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        super().__init__(
            name="mock",
            provider_type="publishing",
            capabilities={ProviderCapability.PUBLISHING},
            is_healthy=is_healthy,
        )
        self._posts: dict[str, PublishedPost] = {}
        self._statuses: dict[str, str] = {}

    async def publish(
        self,
        package: PublishingPackage,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[PublishedPost]:
        """Publish a deterministic mock post with a generated external identifier."""

        if not package.asset_ids:
            raise CreatorOSValidationError(
                "publishing package must contain at least one asset_id",
                code="provider_invalid_input",
                details={"field": "asset_ids"},
            )

        external_id = generate_id("mock_post")
        post = PublishedPost(
            platform=package.platform,
            external_id=external_id,
            url=f"mock://published/{external_id}",
        )
        self._posts[external_id] = post.model_copy(deep=True)
        self._statuses[external_id] = "published"
        return ProviderResult[PublishedPost](
            data=post,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )

    async def get_status(
        self,
        external_id: str,
        *,
        context: ProviderRequestContext | None = None,
    ) -> ProviderResult[str]:
        """Return the stored status for a previously published mock post."""

        normalized_external_id = _validate_non_blank(external_id, field_name="external_id")
        status = self._statuses.get(normalized_external_id)
        if status is None:
            raise ProviderNotFoundError("publishing", normalized_external_id)

        return ProviderResult[str](
            data=status,
            provider=self.info,
            usage=_zero_cost_usage(),
            request_id=generate_id("mock_request"),
        )


__all__ = ["MockPublishingProvider"]
