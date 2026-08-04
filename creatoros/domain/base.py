"""Shared domain model helpers for CreatorOS."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

_ALLOWED_PREFIX_PATTERN = re.compile(r"^[a-z0-9_]+$")


class CreatorOSModel(BaseModel):
    """Base model for CreatorOS domain objects with strict validation defaults."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
        use_enum_values=False,
    )


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""

    return datetime.now(UTC)


def ensure_aware_utc_datetime(value: datetime, *, field_name: str) -> datetime:
    """Validate that a datetime is timezone-aware."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def generate_id(prefix: str) -> str:
    """Generate a stable-format identifier using a normalized prefix and UUID4."""

    normalized_prefix = prefix.strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized_prefix:
        raise ValueError("prefix must not be blank")

    if not _ALLOWED_PREFIX_PATTERN.fullmatch(normalized_prefix):
        raise ValueError("prefix may contain only letters, digits, and underscores")

    return f"{normalized_prefix}_{uuid4().hex}"
