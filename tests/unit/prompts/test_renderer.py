"""Unit tests for CreatorOS prompt rendering."""

from __future__ import annotations

import pytest

from creatoros.core import CreatorOSValidationError, PromptRenderError
from creatoros.prompts import (
    PromptDefinition,
    PromptFormat,
    PromptMessage,
    PromptRenderer,
    PromptRole,
    PromptVariable,
    PromptVariableType,
)


def build_definition(
    *,
    messages: list[PromptMessage] | None = None,
    variables: list[PromptVariable] | None = None,
) -> PromptDefinition:
    """Return a reusable prompt definition for renderer tests."""

    return PromptDefinition(
        name="gaming_script",
        format=PromptFormat.TEXT,
        messages=messages
        or [
            PromptMessage(role=PromptRole.SYSTEM, content="You create concise scripts."),
            PromptMessage(role=PromptRole.USER, content="Write about {game} and {topic}."),
        ],
        variables=variables
        or [
            PromptVariable(name="game"),
            PromptVariable(name="topic"),
        ],
        metadata={"owner": "creatoros"},
    )


def test_required_variables_render_correctly() -> None:
    """Declared required variables should render successfully."""

    renderer = PromptRenderer()
    definition = build_definition()

    rendered = renderer.render(definition, {"game": "Minecraft", "topic": "facts"})

    assert rendered.messages[1].content == "Write about Minecraft and facts."


def test_defaults_are_applied() -> None:
    """Variable defaults should be applied when values are absent."""

    renderer = PromptRenderer()
    definition = build_definition(
        variables=[
            PromptVariable(name="game", default="Minecraft"),
            PromptVariable(name="topic", default="facts"),
        ]
    )

    rendered = renderer.render(definition)

    assert rendered.variables == {"game": "Minecraft", "topic": "facts"}


def test_missing_required_variables_are_rejected() -> None:
    """Missing required variables should raise a typed validation error."""

    renderer = PromptRenderer()

    with pytest.raises(CreatorOSValidationError) as exc_info:
        renderer.render(build_definition(), {"game": "Minecraft"})

    assert exc_info.value.code == "prompt_missing_variable"


def test_unknown_supplied_variables_are_rejected() -> None:
    """Supplied undeclared variables should be rejected."""

    renderer = PromptRenderer()

    with pytest.raises(CreatorOSValidationError) as exc_info:
        renderer.render(build_definition(), {"game": "Minecraft", "topic": "facts", "extra": "value"})

    assert exc_info.value.code == "prompt_unknown_variable"


def test_undeclared_placeholders_are_rejected() -> None:
    """Placeholders used in messages must be declared."""

    renderer = PromptRenderer()
    definition = build_definition(
        messages=[PromptMessage(role=PromptRole.USER, content="Write about {game} and {topic}.")],
        variables=[PromptVariable(name="game")],
    )

    with pytest.raises(CreatorOSValidationError) as exc_info:
        renderer.render(definition, {"game": "Minecraft"})

    assert exc_info.value.code == "prompt_undeclared_placeholder"


def test_attribute_traversal_placeholders_are_rejected() -> None:
    """Attribute traversal placeholders must be rejected."""

    renderer = PromptRenderer()
    definition = build_definition(
        messages=[PromptMessage(role=PromptRole.USER, content="Write about {user.name}.")],
        variables=[PromptVariable(name="user")],
    )

    with pytest.raises(CreatorOSValidationError) as exc_info:
        renderer.render(definition, {"user": "Vinay"})

    assert exc_info.value.code == "prompt_invalid_placeholder"


def test_item_traversal_placeholders_are_rejected() -> None:
    """Item traversal placeholders must be rejected."""

    renderer = PromptRenderer()
    definition = build_definition(
        messages=[PromptMessage(role=PromptRole.USER, content="Write about {items[0]}.")],
        variables=[PromptVariable(name="items")],
    )

    with pytest.raises(CreatorOSValidationError) as exc_info:
        renderer.render(definition, {"items": "value"})

    assert exc_info.value.code == "prompt_invalid_placeholder"


def test_escaped_braces_work() -> None:
    """Escaped literal braces should remain supported."""

    renderer = PromptRenderer()
    definition = build_definition(
        messages=[PromptMessage(role=PromptRole.USER, content="Return JSON like {{\"game\": \"{game}\"}}.")],
        variables=[PromptVariable(name="game")],
    )

    rendered = renderer.render(definition, {"game": "Minecraft"})

    assert rendered.messages[0].content == 'Return JSON like {"game": "Minecraft"}.'


def test_multiple_messages_render_correctly() -> None:
    """Multiple messages should render predictably in order."""

    renderer = PromptRenderer()
    rendered = renderer.render(build_definition(), {"game": "Minecraft", "topic": "facts"})

    assert rendered.text == (
        "SYSTEM:\nYou create concise scripts.\n\n"
        "USER:\nWrite about Minecraft and facts."
    )


def test_definition_and_input_values_are_not_mutated() -> None:
    """Rendering should not mutate the definition or the caller values."""

    renderer = PromptRenderer()
    definition = build_definition(
        messages=[PromptMessage(role=PromptRole.USER, content="Use {items}.")],
        variables=[PromptVariable(name="items", variable_type=PromptVariableType.STRING_LIST)],
    )
    values = {"items": ["  one  ", "two"]}
    original_message_content = definition.messages[0].content

    rendered = renderer.render(definition, values)
    values["items"].append("three")

    assert definition.messages[0].content == original_message_content
    assert rendered.variables["items"] == ["one", "two"]


def test_error_details_do_not_contain_prompt_content_or_values() -> None:
    """Validation errors should exclude prompt content and supplied values."""

    renderer = PromptRenderer()

    with pytest.raises(CreatorOSValidationError) as exc_info:
        renderer.render(build_definition(), {"game": "Minecraft", "topic": 123})

    assert exc_info.value.details == {
        "variable_name": "topic",
        "expected_type": "string",
    }
    assert "Write about" not in str(exc_info.value)
    assert "123" not in str(exc_info.value)


def test_typed_values_render_predictably() -> None:
    """Typed integer and boolean values should render through simple placeholders."""

    renderer = PromptRenderer()
    definition = build_definition(
        messages=[PromptMessage(role=PromptRole.USER, content="Duration {duration}; enabled {enabled}.")],
        variables=[
            PromptVariable(name="duration", variable_type=PromptVariableType.INTEGER),
            PromptVariable(name="enabled", variable_type=PromptVariableType.BOOLEAN),
        ],
    )

    rendered = renderer.render(definition, {"duration": 30, "enabled": True})

    assert rendered.messages[0].content == "Duration 30; enabled True."


def test_non_validation_render_failures_use_prompt_render_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected renderer failures should surface as PromptRenderError."""

    renderer = PromptRenderer()
    definition = build_definition()

    def fail_vformat(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("unexpected")

    monkeypatch.setattr(renderer._formatter, "vformat", fail_vformat)

    with pytest.raises(PromptRenderError) as exc_info:
        renderer.render(definition, {"game": "Minecraft", "topic": "facts"})

    assert exc_info.value.code == "prompt_render_failed"
