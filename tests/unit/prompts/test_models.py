"""Unit tests for CreatorOS prompt models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from creatoros.core import CreatorOSValidationError
from creatoros.prompts import (
    PromptDefinition,
    PromptFormat,
    PromptMessage,
    PromptRole,
    PromptStatus,
    PromptVariable,
    PromptVariableType,
    RenderedPrompt,
)


def build_message() -> PromptMessage:
    """Return a reusable prompt message fixture."""

    return PromptMessage(role=PromptRole.USER, content="Create content about {topic}.")


def build_variable(name: str = "topic") -> PromptVariable:
    """Return a reusable prompt variable fixture."""

    return PromptVariable(name=name)


def build_definition() -> PromptDefinition:
    """Return a reusable prompt definition fixture."""

    return PromptDefinition(
        name="gaming_script",
        status=PromptStatus.ACTIVE,
        messages=[build_message()],
        variables=[build_variable()],
        tags=["gaming", "script"],
    )


def test_prompt_variable_validates_names() -> None:
    """Prompt variables should trim and validate names."""

    variable = PromptVariable(name="  topic_name  ")

    assert variable.name == "topic_name"

    with pytest.raises(ValidationError):
        PromptVariable(name="topic-name")


def test_prompt_variable_rejects_names_starting_with_digits() -> None:
    """Prompt variable names must not start with digits."""

    with pytest.raises(ValidationError):
        PromptVariable(name="1topic")


@pytest.mark.parametrize(
    ("variable_type", "default", "expected"),
    [
        (PromptVariableType.STRING, "  game  ", "game"),
        (PromptVariableType.INTEGER, 30, 30),
        (PromptVariableType.FLOAT, 1.5, 1.5),
        (PromptVariableType.BOOLEAN, True, True),
        (PromptVariableType.STRING_LIST, ["  one  ", "two"], ["one", "two"]),
    ],
)
def test_prompt_variable_validates_supported_default_types(
    variable_type: PromptVariableType,
    default: object,
    expected: object,
) -> None:
    """Defaults should be validated and normalized by variable type."""

    variable = PromptVariable(name="value", variable_type=variable_type, default=default)

    assert variable.default == expected


def test_booleans_are_not_accepted_as_integers_or_floats() -> None:
    """Boolean values must not satisfy integer or float prompt variables."""

    with pytest.raises(ValidationError):
        PromptVariable(name="count", variable_type=PromptVariableType.INTEGER, default=True)

    with pytest.raises(ValidationError):
        PromptVariable(name="ratio", variable_type=PromptVariableType.FLOAT, default=False)


def test_string_list_defaults_are_copied_and_normalized() -> None:
    """List defaults should be normalized and detached from caller state."""

    default_value = ["  one  ", "two"]
    variable = PromptVariable(
        name="items",
        variable_type=PromptVariableType.STRING_LIST,
        default=default_value,
    )
    default_value.append("three")

    assert variable.default == ["one", "two"]
    assert variable.default is not default_value


def test_validate_value_returns_normalized_values() -> None:
    """Runtime values should be validated and normalized safely."""

    assert PromptVariable(name="name").validate_value("  Roblox  ") == "Roblox"
    assert PromptVariable(
        name="items",
        variable_type=PromptVariableType.STRING_LIST,
        required=False,
    ).validate_value(["  one  ", "two"]) == ["one", "two"]


def test_validate_value_errors_contain_no_supplied_values() -> None:
    """Runtime validation errors should exclude the caller's unsafe value."""

    variable = PromptVariable(name="count", variable_type=PromptVariableType.INTEGER)

    with pytest.raises(CreatorOSValidationError) as exc_info:
        variable.validate_value("secret-value")

    assert exc_info.value.code == "prompt_variable_invalid_value"
    assert exc_info.value.details == {
        "variable_name": "count",
        "expected_type": "integer",
    }
    assert "secret-value" not in str(exc_info.value)


def test_prompt_message_rejects_blank_content() -> None:
    """Prompt messages should reject blank content."""

    with pytest.raises(ValidationError):
        PromptMessage(role=PromptRole.SYSTEM, content="   ")


def test_prompt_definition_generates_prompt_id() -> None:
    """Prompt definitions should generate prompt-prefixed identifiers."""

    definition = build_definition()

    assert definition.id.startswith("prompt_")


def test_prompt_definition_requires_messages() -> None:
    """Prompt definitions must include at least one message."""

    with pytest.raises(ValidationError):
        PromptDefinition(name="gaming_script", messages=[])


def test_prompt_definition_rejects_duplicate_variables() -> None:
    """Prompt definitions should reject duplicate normalized variable names."""

    with pytest.raises(ValidationError):
        PromptDefinition(
            name="gaming_script",
            messages=[build_message()],
            variables=[build_variable("Game"), build_variable("game")],
        )


def test_prompt_definition_rejects_duplicate_normalized_tags() -> None:
    """Prompt definitions should reject duplicate normalized tags."""

    with pytest.raises(ValidationError):
        PromptDefinition(
            name="gaming_script",
            messages=[build_message()],
            tags=["Gaming", "gaming"],
        )


def test_qualified_name_is_correct() -> None:
    """Prompt definitions should expose the expected qualified name."""

    definition = PromptDefinition(name="gaming_script", version=2, messages=[build_message()])

    assert definition.qualified_name == "gaming_script:v2"


def test_variable_names_property_is_immutable() -> None:
    """Variable names should be exposed through an immutable frozenset."""

    definition = build_definition()

    assert definition.variable_names == frozenset({"topic"})
    with pytest.raises(AttributeError):
        definition.variable_names.add("other")  # type: ignore[attr-defined]


def test_mutable_defaults_are_isolated() -> None:
    """Mutable defaults should not be shared across prompt model instances."""

    first = PromptDefinition(name="first", messages=[build_message()])
    second = PromptDefinition(name="second", messages=[build_message()])
    first.tags.append("gaming")
    first.metadata["demo"] = True
    first.variables.append(build_variable("game"))

    assert second.tags == []
    assert second.metadata == {}
    assert second.variables == []


def test_prompt_definition_serializes_and_restores() -> None:
    """Prompt definitions should serialize and restore predictably."""

    definition = build_definition()

    restored = PromptDefinition.model_validate(definition.model_dump())

    assert restored == definition


def test_rendered_prompt_validates_fields() -> None:
    """Rendered prompts should validate required fields and message presence."""

    with pytest.raises(ValidationError):
        RenderedPrompt(
            prompt_id="  ",
            prompt_name="gaming_script",
            prompt_version=1,
            format=PromptFormat.TEXT,
            messages=[build_message()],
        )

    with pytest.raises(ValidationError):
        RenderedPrompt(
            prompt_id="prompt_1",
            prompt_name="gaming_script",
            prompt_version=0,
            format=PromptFormat.TEXT,
            messages=[build_message()],
        )


def test_rendered_prompt_text_rendering_is_predictable() -> None:
    """Rendered prompt text should follow the documented block format."""

    one_message = RenderedPrompt(
        prompt_id="prompt_1",
        prompt_name="single_prompt",
        prompt_version=1,
        format=PromptFormat.TEXT,
        messages=[PromptMessage(role=PromptRole.USER, content="One")],
    )
    many_messages = RenderedPrompt(
        prompt_id="prompt_2",
        prompt_name="multi_prompt",
        prompt_version=1,
        format=PromptFormat.TEXT,
        messages=[
            PromptMessage(role=PromptRole.SYSTEM, content="System text"),
            PromptMessage(role=PromptRole.USER, content="User text"),
            PromptMessage(role=PromptRole.ASSISTANT, content="Assistant text"),
        ],
    )

    assert one_message.text == "One"
    assert many_messages.text == (
        "SYSTEM:\nSystem text\n\nUSER:\nUser text\n\nASSISTANT:\nAssistant text"
    )


def test_rendered_prompt_mutable_defaults_are_isolated() -> None:
    """Rendered prompt dictionaries should not be shared between instances."""

    first = RenderedPrompt(
        prompt_id="prompt_1",
        prompt_name="first",
        prompt_version=1,
        format=PromptFormat.TEXT,
        messages=[build_message()],
    )
    second = RenderedPrompt(
        prompt_id="prompt_2",
        prompt_name="second",
        prompt_version=1,
        format=PromptFormat.TEXT,
        messages=[build_message()],
    )
    first.variables["topic"] = "gaming"
    first.metadata["demo"] = True

    assert second.variables == {}
    assert second.metadata == {}
