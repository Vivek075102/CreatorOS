"""Unit tests for the CreatorOS exception hierarchy."""

import pytest

from creatoros.core import (
    AgentError,
    AnalyticsError,
    ApplicationError,
    ApprovalRequiredError,
    AssetError,
    ConfigurationError,
    CreatorOSError,
    CreatorOSValidationError,
    DomainError,
    EngineError,
    PersistenceError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    PublishingError,
    WorkflowError,
    WorkflowStateError,
    wrap_exception,
)


def test_creatoros_error_stores_message_code_details_and_retryable() -> None:
    """The root exception should preserve its core constructor fields."""

    error = CreatorOSError(
        "Configuration failed",
        code="CONFIG_ERROR",
        details={"field": "database_url"},
        retryable=True,
    )

    assert error.message == "Configuration failed"
    assert error.code == "CONFIG_ERROR"
    assert error.details == {"field": "database_url"}
    assert error.retryable is True


def test_blank_messages_are_rejected() -> None:
    """Blank messages should not be accepted."""

    with pytest.raises(ValueError):
        CreatorOSError("   ")


def test_details_are_copied_during_construction() -> None:
    """Details should be copied into the exception."""

    details = {"field": "database_url"}
    error = CreatorOSError("Configuration failed", details=details)

    assert error.details is not details


def test_mutating_original_details_does_not_change_exception() -> None:
    """Mutating the caller's details should not affect stored exception details."""

    details = {"field": "database_url"}
    error = CreatorOSError("Configuration failed", details=details)
    details["field"] = "mutated"

    assert error.details == {"field": "database_url"}


def test_to_dict_returns_expected_structure() -> None:
    """The dictionary representation should contain the expected fields."""

    error = CreatorOSError(
        "Configuration failed",
        code="CONFIG_ERROR",
        details={"field": "database_url"},
        retryable=False,
    )

    assert error.to_dict() == {
        "type": "CreatorOSError",
        "message": "Configuration failed",
        "code": "CONFIG_ERROR",
        "details": {"field": "database_url"},
        "retryable": False,
    }


def test_str_returns_the_message() -> None:
    """String conversion should return the exception message."""

    error = CreatorOSError("Configuration failed")

    assert str(error) == "Configuration failed"


def test_provider_rate_limit_error_is_retryable_by_default() -> None:
    """Rate limit failures should be retryable by default."""

    error = ProviderRateLimitError("Rate limit")

    assert error.retryable is True


def test_provider_timeout_error_is_retryable_by_default() -> None:
    """Timeout failures should be retryable by default."""

    error = ProviderTimeoutError("Timeout")

    assert error.retryable is True


def test_provider_unavailable_error_is_retryable_by_default() -> None:
    """Unavailable provider failures should be retryable by default."""

    error = ProviderUnavailableError("Unavailable")

    assert error.retryable is True


def test_provider_authentication_error_is_not_retryable_by_default() -> None:
    """Authentication failures should not be retryable by default."""

    error = ProviderAuthenticationError("Authentication failed")

    assert error.retryable is False


def test_approval_required_error_is_not_retryable_by_default() -> None:
    """Approval-required failures should not be retryable by default."""

    error = ApprovalRequiredError("Approval required")

    assert error.retryable is False


def test_validation_error_is_not_retryable_by_default() -> None:
    """Validation failures should not be retryable by default."""

    error = CreatorOSValidationError("Invalid input")

    assert error.retryable is False


def test_explicit_retryable_values_can_override_defaults() -> None:
    """Explicit retryability should override subclass defaults."""

    error = ProviderRateLimitError("Rate limit", retryable=False)

    assert error.retryable is False


def test_wrap_exception_creates_the_requested_exception_type() -> None:
    """Wrapping should create the requested CreatorOS exception subclass."""

    wrapped = wrap_exception(
        RuntimeError("provider failed"),
        message="Provider call failed",
        exception_type=ProviderError,
    )

    assert isinstance(wrapped, ProviderError)
    assert wrapped.message == "Provider call failed"


def test_wrap_exception_preserves_code_and_safe_details() -> None:
    """Wrapping should preserve explicit code and safe details."""

    wrapped = wrap_exception(
        RuntimeError("provider failed"),
        message="Provider call failed",
        exception_type=ProviderError,
        code="PROVIDER_FAILURE",
        details={"provider": "mock"},
    )

    assert wrapped.code == "PROVIDER_FAILURE"
    assert wrapped.details == {"provider": "mock"}


def test_wrap_exception_preserves_subclass_retry_defaults_when_retryable_is_none() -> None:
    """Wrapping should preserve subclass retry defaults when not overridden."""

    wrapped = wrap_exception(
        TimeoutError("timed out"),
        message="Provider timed out",
        exception_type=ProviderTimeoutError,
    )

    assert wrapped.retryable is True


def test_wrap_exception_returns_existing_matching_exception_when_no_override_is_supplied() -> None:
    """Existing matching exceptions should be returned unchanged when no override is supplied."""

    error = ProviderError("Provider call failed")

    wrapped = wrap_exception(
        error,
        message="Ignored message",
        exception_type=ProviderError,
    )

    assert wrapped is error


def test_wrap_exception_rejects_a_non_creatoros_exception_type() -> None:
    """Only CreatorOSError subclasses should be accepted as wrapper targets."""

    with pytest.raises(TypeError):
        wrap_exception(
            RuntimeError("provider failed"),
            message="Invalid wrapper",
            exception_type=RuntimeError,
        )


def test_exception_hierarchy_relationships_are_correct() -> None:
    """The exception hierarchy should reflect the expected category structure."""

    assert issubclass(ConfigurationError, CreatorOSError)
    assert issubclass(CreatorOSValidationError, CreatorOSError)
    assert issubclass(DomainError, CreatorOSError)
    assert issubclass(ApplicationError, CreatorOSError)
    assert issubclass(WorkflowError, ApplicationError)
    assert issubclass(WorkflowStateError, WorkflowError)
    assert issubclass(ApprovalRequiredError, WorkflowError)
    assert issubclass(EngineError, ApplicationError)
    assert issubclass(AgentError, ApplicationError)
    assert issubclass(ProviderError, ApplicationError)
    assert issubclass(ProviderAuthenticationError, ProviderError)
    assert issubclass(ProviderRateLimitError, ProviderError)
    assert issubclass(ProviderTimeoutError, ProviderError)
    assert issubclass(ProviderUnavailableError, ProviderError)
    assert issubclass(PersistenceError, ApplicationError)
    assert issubclass(PublishingError, ApplicationError)
    assert issubclass(AnalyticsError, ApplicationError)
    assert issubclass(AssetError, ApplicationError)


def test_no_external_exception_text_is_copied_automatically_into_details() -> None:
    """Wrapping should not automatically copy external exception text into details."""

    wrapped = wrap_exception(
        RuntimeError("password=secret-value"),
        message="Provider call failed",
        exception_type=ProviderError,
    )

    assert wrapped.details == {}
