"""Filename parsing and construction for versioned CreatorOS prompt assets."""

from __future__ import annotations

import re

from pydantic import ValidationError, field_validator

from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel

_ASSET_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_ASSET_FILENAME_PATTERN = re.compile(r"^(?P<name>[a-z][a-z0-9_]*)\.v(?P<version>[1-9][0-9]*)\.json$")


class PromptAssetName(CreatorOSModel):
    """Parsed identity information from a canonical prompt asset filename."""

    name: str
    version: int
    filename: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate canonical prompt asset names."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("name must not be blank")
        if not _ASSET_NAME_PATTERN.fullmatch(normalized_value):
            raise ValueError("name must use lowercase snake_case")
        return normalized_value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        """Require positive integer asset versions."""

        if value < 1:
            raise ValueError("version must be greater than or equal to 1")
        return value

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        """Reject blank filenames."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("filename must not be blank")
        return normalized_value


def parse_prompt_asset_filename(filename: str) -> PromptAssetName:
    """Parse and validate one canonical prompt asset filename."""

    normalized_filename = filename.strip()
    if not normalized_filename or "/" in normalized_filename or "\\" in normalized_filename:
        raise _invalid_filename_error(filename)

    match = _ASSET_FILENAME_PATTERN.fullmatch(normalized_filename)
    if match is None:
        raise _invalid_filename_error(normalized_filename)

    parsed_name = match.group("name")
    parsed_version = int(match.group("version"))
    return PromptAssetName(name=parsed_name, version=parsed_version, filename=normalized_filename)


def build_prompt_asset_filename(name: str, version: int) -> str:
    """Build the canonical filename for a prompt asset identity."""

    try:
        parsed_name = PromptAssetName(name=name, version=version, filename="placeholder").name
    except ValidationError as error:
        raise CreatorOSValidationError(
            "prompt asset filename is invalid",
            code="prompt_asset_invalid_filename",
            details={"filename": f"{name}.v{version}.json"},
        ) from error

    return f"{parsed_name}.v{version}.json"


def _invalid_filename_error(filename: str) -> CreatorOSValidationError:
    """Return a safe validation error for invalid asset filenames."""

    return CreatorOSValidationError(
        "prompt asset filename is invalid",
        code="prompt_asset_invalid_filename",
        details={"filename": filename},
    )


__all__ = [
    "PromptAssetName",
    "build_prompt_asset_filename",
    "parse_prompt_asset_filename",
]
