"""Exception hierarchy for expected CreatorOS application failures."""

from __future__ import annotations

from typing import Any


class CreatorOSError(Exception):
    """Root exception for expected CreatorOS application failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        normalized_message = message.strip()
        if not normalized_message:
            raise ValueError("message must not be blank")

        super().__init__(normalized_message)
        self.message = normalized_message
        self.code = code
        self.details = {} if details is None else dict(details)
        self.retryable = retryable

    def to_dict(self) -> dict[str, object]:
        """Return a serializable representation of the exception."""

        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "details": dict(self.details),
            "retryable": self.retryable,
        }

    def __str__(self) -> str:
        """Return the human-readable exception message."""

        return self.message


class ConfigurationError(CreatorOSError):
    """Raised when configuration is invalid or incomplete."""


class CreatorOSValidationError(CreatorOSError):
    """Raised when validated application input is invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message, code=code, details=details, retryable=retryable)


class DomainError(CreatorOSError):
    """Raised for domain-level business failures."""


class ApplicationError(CreatorOSError):
    """Raised for application-layer execution failures."""


class WorkflowError(ApplicationError):
    """Raised for workflow execution failures."""


class WorkflowStateError(WorkflowError):
    """Raised when workflow state is invalid or inconsistent."""


class ApprovalRequiredError(WorkflowError):
    """Raised when execution must pause for human approval."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message, code=code, details=details, retryable=retryable)


class EngineError(ApplicationError):
    """Raised for engine-level failures."""


class AgentError(ApplicationError):
    """Raised for agent-level failures."""


class ProviderError(ApplicationError):
    """Raised for provider integration failures."""


class ProviderRegistryError(ConfigurationError):
    """Raised when provider registry configuration or resolution fails."""


class ProviderAlreadyRegisteredError(ProviderRegistryError):
    """Raised when a provider registration already exists."""

    def __init__(self, provider_type: str, name: str) -> None:
        super().__init__(
            f"Provider '{name}' is already registered for type '{provider_type}'",
            code="provider_already_registered",
            details={"provider_type": provider_type, "provider_name": name},
        )


class ProviderNotFoundError(ProviderRegistryError):
    """Raised when a requested provider registration cannot be found."""

    def __init__(self, provider_type: str, name: str) -> None:
        super().__init__(
            f"Provider '{name}' was not found for type '{provider_type}'",
            code="provider_not_found",
            details={"provider_type": provider_type, "provider_name": name},
        )


class ProviderTypeMismatchError(ProviderRegistryError):
    """Raised when a resolved provider does not satisfy the expected contract."""

    def __init__(self, provider_type: str, name: str, expected_type: str) -> None:
        super().__init__(
            f"Provider '{name}' for type '{provider_type}' does not satisfy '{expected_type}'",
            code="provider_type_mismatch",
            details={
                "provider_type": provider_type,
                "provider_name": name,
                "expected_type": expected_type,
            },
        )


class ProviderAuthenticationError(ProviderError):
    """Raised when provider authentication fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message, code=code, details=details, retryable=retryable)


class ProviderRateLimitError(ProviderError):
    """Raised when provider rate limits are encountered."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message, code=code, details=details, retryable=retryable)


class ProviderTimeoutError(ProviderError):
    """Raised when provider operations time out."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message, code=code, details=details, retryable=retryable)


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is temporarily unavailable."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message, code=code, details=details, retryable=retryable)


class PersistenceError(ApplicationError):
    """Raised for persistence-layer failures."""


class PublishingError(ApplicationError):
    """Raised for publishing failures."""


class AnalyticsError(ApplicationError):
    """Raised for analytics failures."""


class AssetError(ApplicationError):
    """Raised for asset-related failures."""


class PromptError(ApplicationError):
    """Raised for prompt-system execution failures."""


class PromptRegistryError(PromptError):
    """Raised when prompt registry operations fail."""


class PromptAlreadyRegisteredError(PromptRegistryError):
    """Raised when a prompt definition is already registered."""

    def __init__(self, name: str, version: int) -> None:
        super().__init__(
            f"Prompt '{name}' is already registered for version '{version}'",
            code="prompt_already_registered",
            details={"prompt_name": name.strip(), "prompt_version": version},
        )


class PromptNotFoundError(PromptRegistryError):
    """Raised when a requested prompt definition cannot be found."""

    def __init__(
        self,
        name: str,
        version: int | None,
        *,
        active_only: bool = False,
    ) -> None:
        if version is None and active_only:
            message = f"No active prompt was found for name '{name}'"
        elif version is None:
            message = f"Prompt '{name}' was not found"
        else:
            message = f"Prompt '{name}' was not found for version '{version}'"

        details: dict[str, object] = {"prompt_name": name.strip()}
        if version is not None:
            details["prompt_version"] = version
        if active_only:
            details["active_only"] = True

        super().__init__(
            message,
            code="prompt_not_found",
            details=details,
        )


class PromptLoadError(PromptError):
    """Raised when loading prompt definitions from the filesystem fails."""


class PromptManifestError(PromptError):
    """Raised when a prompt manifest is invalid or mismatched."""


class PromptRenderError(PromptError):
    """Raised when prompt rendering fails for non-validation reasons."""


class ParsingError(ApplicationError):
    """Raised for structured-output parsing failures."""


class ParserRegistryError(ParsingError):
    """Raised when parser registry operations fail."""


class ParserNotFoundError(ParserRegistryError):
    """Raised when a registered parser cannot be found for a prompt name."""

    def __init__(self, prompt_name: str) -> None:
        super().__init__(
            f"No parser is registered for prompt '{prompt_name}'",
            code="parser_not_found",
            details={"prompt_name": prompt_name.strip()},
        )


class StructuredOutputError(ParsingError):
    """Raised when structured provider text is invalid or unusable."""


class StructuredValueError(StructuredOutputError):
    """Raised when one structured parsed field contains an invalid value."""

    def __init__(self, field_name: str, *, expected_type: str) -> None:
        super().__init__(
            "structured output field contains an invalid value",
            code="structured_output_invalid_value",
            details={"field_name": field_name.strip(), "expected_type": expected_type.strip()},
        )


class DuplicateParsedFieldError(StructuredOutputError):
    """Raised when structured output repeats the same canonical field."""

    def __init__(self, field_name: str) -> None:
        super().__init__(
            "structured output contains a duplicate field",
            code="structured_output_duplicate_field",
            details={"field_name": field_name.strip()},
        )


def wrap_exception(
    error: Exception,
    *,
    message: str,
    exception_type: type[CreatorOSError] = CreatorOSError,
    code: str | None = None,
    details: dict[str, object] | None = None,
    retryable: bool | None = None,
) -> CreatorOSError:
    """Wrap an external exception in the requested CreatorOS exception type."""

    if not issubclass(exception_type, CreatorOSError):
        raise TypeError("exception_type must be a CreatorOSError subclass")

    has_overrides = code is not None or details is not None or retryable is not None
    if isinstance(error, exception_type) and not has_overrides:
        return error

    kwargs: dict[str, Any] = {
        "code": code,
        "details": details,
    }
    if retryable is not None:
        kwargs["retryable"] = retryable

    wrapped_error = exception_type(message, **kwargs)
    wrapped_error.__cause__ = error
    return wrapped_error
