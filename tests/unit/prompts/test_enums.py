"""Unit tests for CreatorOS prompt enums."""

from creatoros.prompts import PromptFormat, PromptRole, PromptStatus, PromptVariableType


def test_prompt_role_values_are_exact() -> None:
    """Prompt role values should match the documented contract."""

    assert [role.value for role in PromptRole] == ["system", "user", "assistant"]


def test_prompt_format_values_are_exact() -> None:
    """Prompt format values should match the documented contract."""

    assert [item.value for item in PromptFormat] == ["text", "json", "markdown"]


def test_prompt_status_values_are_exact() -> None:
    """Prompt status values should match the documented contract."""

    assert [item.value for item in PromptStatus] == ["draft", "active", "deprecated"]


def test_prompt_variable_type_values_are_exact() -> None:
    """Prompt variable type values should match the documented contract."""

    assert [item.value for item in PromptVariableType] == [
        "string",
        "integer",
        "float",
        "boolean",
        "string_list",
    ]
