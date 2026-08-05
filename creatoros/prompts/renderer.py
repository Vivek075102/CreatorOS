"""Prompt rendering for provider-independent CreatorOS prompt assets."""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter

from creatoros.core import CreatorOSValidationError, PromptRenderError
from creatoros.prompts.models import (
    PromptDefinition,
    PromptMessage,
    PromptVariable,
    RenderedPrompt,
)


class PromptRenderer:
    """Render validated prompt definitions with runtime values."""

    def __init__(self) -> None:
        self._formatter = Formatter()

    def render(
        self,
        definition: PromptDefinition,
        values: dict[str, object] | None = None,
    ) -> RenderedPrompt:
        """Render a prompt definition into a provider-independent prompt payload."""

        supplied_values = {} if values is None else dict(values)
        declared_variables = {variable.name: variable for variable in definition.variables}
        self._validate_supplied_variables(supplied_values, declared_variables)
        self._validate_placeholders(definition, declared_variables)
        resolved_values = self._resolve_values(supplied_values, declared_variables)

        rendered_messages: list[PromptMessage] = []
        for message in definition.messages:
            try:
                rendered_content = self._formatter.vformat(message.content, (), resolved_values)
            except KeyError as error:
                missing_name = str(error).strip("'")
                raise CreatorOSValidationError(
                    f"missing value for variable '{missing_name}'",
                    code="prompt_missing_variable",
                    details={"variable_name": missing_name},
                ) from error
            except ValueError as error:
                raise CreatorOSValidationError(
                    "prompt rendering failed because a placeholder is invalid",
                    code="prompt_invalid_placeholder",
                    details={},
                ) from error
            except Exception as error:
                raise PromptRenderError(
                    "prompt rendering failed",
                    code="prompt_render_failed",
                    details={
                        "prompt_name": definition.name,
                        "prompt_version": definition.version,
                    },
                ) from error

            rendered_messages.append(
                PromptMessage(role=message.role, content=rendered_content)
            )

        return RenderedPrompt(
            prompt_id=definition.id,
            prompt_name=definition.name,
            prompt_version=definition.version,
            format=definition.format,
            messages=rendered_messages,
            variables=dict(resolved_values),
            metadata=dict(definition.metadata),
        )

    def _validate_supplied_variables(
        self,
        supplied_values: dict[str, object],
        declared_variables: Mapping[str, PromptVariable],
    ) -> None:
        """Reject supplied variables that were not declared by the prompt."""

        for variable_name in supplied_values:
            if variable_name not in declared_variables:
                raise CreatorOSValidationError(
                    f"unknown variable '{variable_name}' was supplied",
                    code="prompt_unknown_variable",
                    details={"variable_name": variable_name},
                )

    def _validate_placeholders(
        self,
        definition: PromptDefinition,
        declared_variables: Mapping[str, PromptVariable],
    ) -> None:
        """Validate placeholders used across all prompt messages."""

        for message in definition.messages:
            for _, field_name, format_spec, conversion in self._formatter.parse(message.content):
                if field_name is None:
                    continue

                if not field_name:
                    raise CreatorOSValidationError(
                        "prompt placeholder must declare a variable name",
                        code="prompt_invalid_placeholder",
                        details={"placeholder_name": field_name},
                    )

                if format_spec or conversion or not field_name.isidentifier():
                    raise CreatorOSValidationError(
                        f"prompt placeholder '{field_name}' is invalid",
                        code="prompt_invalid_placeholder",
                        details={"placeholder_name": field_name},
                    )

                if field_name not in declared_variables:
                    raise CreatorOSValidationError(
                        f"prompt placeholder '{field_name}' is not declared",
                        code="prompt_undeclared_placeholder",
                        details={"placeholder_name": field_name},
                    )

    def _resolve_values(
        self,
        supplied_values: dict[str, object],
        declared_variables: Mapping[str, PromptVariable],
    ) -> dict[str, object]:
        """Resolve and validate runtime prompt variable values."""

        resolved_values: dict[str, object] = {}
        for variable_name, variable in declared_variables.items():
            if variable_name in supplied_values:
                resolved_values[variable_name] = variable.validate_value(supplied_values[variable_name])
                continue

            if variable.default is not None:
                resolved_values[variable_name] = variable.validate_value(variable.default)
                continue

            if variable.required:
                raise CreatorOSValidationError(
                    f"missing required variable '{variable_name}'",
                    code="prompt_missing_variable",
                    details={"variable_name": variable_name},
                )

        return resolved_values


__all__ = ["PromptRenderer"]
