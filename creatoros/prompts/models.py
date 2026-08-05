"""Typed prompt contracts for CreatorOS prompt assets."""

from __future__ import annotations

import re

from pydantic import Field, field_validator, model_validator

from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel, generate_id
from creatoros.prompts.enums import PromptFormat, PromptRole, PromptStatus, PromptVariableType

_VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_required_text(value: str, *, field_name: str) -> str:
    """Trim and reject blank required text values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    """Trim and reject blank optional text values when supplied."""

    if value is None:
        return None
    return _normalize_required_text(value, field_name=field_name)


class PromptVariable(CreatorOSModel):
    """Declarative definition of one validated prompt variable."""

    name: str
    variable_type: PromptVariableType = PromptVariableType.STRING
    required: bool = True
    default: object | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Trim and validate prompt variable names."""

        normalized_value = _normalize_required_text(value, field_name="name")
        if not _VARIABLE_NAME_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "name must contain only letters, digits, and underscores and must not start with a digit"
            )
        return normalized_value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        """Trim and reject blank descriptions when supplied."""

        return _normalize_optional_text(value, field_name="description")

    @model_validator(mode="after")
    def validate_default(self) -> PromptVariable:
        """Validate and normalize default values against the declared variable type."""

        if self.default is None:
            return self

        object.__setattr__(self, "default", self._normalize_value_for_type(self.default))
        return self

    def validate_value(self, value: object) -> object:
        """Validate and normalize a runtime prompt variable value."""

        try:
            return self._normalize_value_for_type(value)
        except ValueError as error:
            raise CreatorOSValidationError(
                str(error),
                code="prompt_variable_invalid_value",
                details={
                    "variable_name": self.name,
                    "expected_type": self.variable_type.value,
                },
            ) from error

    def _normalize_value_for_type(self, value: object) -> object:
        """Normalize a value according to the declared prompt variable type."""

        if self.variable_type is PromptVariableType.STRING:
            if not isinstance(value, str):
                raise ValueError("value must be a non-blank string")
            return _normalize_required_text(value, field_name=self.name)

        if self.variable_type is PromptVariableType.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("value must be an integer")
            return value

        if self.variable_type is PromptVariableType.FLOAT:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError("value must be a float")
            return float(value)

        if self.variable_type is PromptVariableType.BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError("value must be a boolean")
            return value

        if self.variable_type is PromptVariableType.STRING_LIST:
            if not isinstance(value, list):
                raise ValueError("value must be a list of non-blank strings")
            normalized_items: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise TypeError("value must be a list of non-blank strings")
                normalized_items.append(_normalize_required_text(item, field_name=self.name))
            return list(normalized_items)

        raise ValueError("unsupported prompt variable type")


class PromptMessage(CreatorOSModel):
    """One provider-independent prompt message."""

    role: PromptRole
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Trim surrounding whitespace and reject blank message content."""

        return _normalize_required_text(value, field_name="content")


class PromptDefinition(CreatorOSModel):
    """Versioned, provider-independent prompt asset definition."""

    id: str = Field(default_factory=lambda: generate_id("prompt"))
    name: str
    version: int = 1
    status: PromptStatus = PromptStatus.DRAFT
    description: str | None = None
    format: PromptFormat = PromptFormat.TEXT
    messages: list[PromptMessage]
    variables: list[PromptVariable] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Trim and reject blank prompt names."""

        return _normalize_required_text(value, field_name="name")

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        """Require prompt versions to start at one."""

        if value < 1:
            raise ValueError("version must be greater than or equal to 1")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        """Trim and reject blank descriptions when supplied."""

        return _normalize_optional_text(value, field_name="description")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        """Trim and validate prompt tags."""

        normalized_tags = [_normalize_required_text(item, field_name="tags") for item in value]
        normalized_keys = [item.casefold() for item in normalized_tags]
        if len(normalized_keys) != len(set(normalized_keys)):
            raise ValueError("tags must be unique after case normalization")
        return normalized_tags

    @model_validator(mode="after")
    def validate_collections(self) -> PromptDefinition:
        """Validate prompt message and variable collection constraints."""

        if not self.messages:
            raise ValueError("messages must contain at least one message")

        variable_keys = [variable.name.casefold() for variable in self.variables]
        if len(variable_keys) != len(set(variable_keys)):
            raise ValueError("variable names must be unique after case normalization")

        return self

    @property
    def qualified_name(self) -> str:
        """Return the stable qualified prompt name."""

        return f"{self.name}:v{self.version}"

    @property
    def variable_names(self) -> frozenset[str]:
        """Return the immutable set of declared prompt variable names."""

        return frozenset(variable.name for variable in self.variables)


class RenderedPrompt(CreatorOSModel):
    """Rendered provider-independent prompt ready for provider adaptation."""

    prompt_id: str
    prompt_name: str
    prompt_version: int
    format: PromptFormat
    messages: list[PromptMessage]
    variables: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("prompt_id", "prompt_name")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank rendered prompt identifiers."""

        return _normalize_required_text(value, field_name=info.field_name)

    @field_validator("prompt_version")
    @classmethod
    def validate_prompt_version(cls, value: int) -> int:
        """Require rendered prompt versions to start at one."""

        if value < 1:
            raise ValueError("prompt_version must be greater than or equal to 1")
        return value

    @model_validator(mode="after")
    def validate_messages(self) -> RenderedPrompt:
        """Ensure rendered prompts always include at least one message."""

        if not self.messages:
            raise ValueError("messages must contain at least one message")
        return self

    @property
    def text(self) -> str:
        """Return a predictable provider-independent text representation."""

        if len(self.messages) == 1:
            return self.messages[0].content

        blocks = [f"{message.role.value.upper()}:\n{message.content}" for message in self.messages]
        return "\n\n".join(blocks)


__all__ = [
    "PromptDefinition",
    "PromptMessage",
    "PromptVariable",
    "RenderedPrompt",
]
