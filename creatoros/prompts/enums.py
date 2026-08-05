"""Enumerations for provider-independent CreatorOS prompt contracts."""

from enum import StrEnum


class PromptRole(StrEnum):
    """Supported prompt message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class PromptFormat(StrEnum):
    """Supported prompt output formats."""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class PromptStatus(StrEnum):
    """Lifecycle states for versioned prompt definitions."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class PromptVariableType(StrEnum):
    """Supported prompt variable types."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING_LIST = "string_list"


__all__ = [
    "PromptFormat",
    "PromptRole",
    "PromptStatus",
    "PromptVariableType",
]
