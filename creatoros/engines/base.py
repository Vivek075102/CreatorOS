"""Base engine framework for CreatorOS execution lifecycle management."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from creatoros.core import CreatorOSError, CreatorOSValidationError, EngineError, wrap_exception
from creatoros.domain import utc_now
from creatoros.engines.models import EngineExecutionContext, EngineResult
from creatoros.observability import bind_context, clear_context, get_logger
from creatoros.providers import Provider, ProviderRegistry, get_provider_registry

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")
TProvider = TypeVar("TProvider")


class BaseEngine[TInput, TOutput](ABC):
    """Abstract base class for CreatorOS engines with shared lifecycle behavior."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.provider_registry = provider_registry or get_provider_registry()
        self.logger = get_logger(f"engines.{self.__class__.__name__.lower()}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable engine name used for logging and results."""

    @abstractmethod
    async def execute(
        self,
        input_data: TInput,
        *,
        context: EngineExecutionContext,
    ) -> TOutput:
        """Run the engine's core behavior and return the output payload."""

    async def before_execute(
        self,
        input_data: TInput,
        *,
        context: EngineExecutionContext,
    ) -> None:
        """Run optional pre-execution logic."""

    async def after_execute(
        self,
        result: TOutput,
        *,
        context: EngineExecutionContext,
    ) -> None:
        """Run optional post-execution logic."""

    async def run(
        self,
        input_data: TInput,
        *,
        context: EngineExecutionContext,
    ) -> EngineResult[TOutput]:
        """Execute the engine lifecycle and return a structured result."""

        engine_name = self._validate_engine_name()
        bind_context(
            job_id=context.job_id,
            step_id=context.step_id,
            workflow_name=context.workflow_name,
            engine_name=engine_name,
        )

        started_at = utc_now()
        self.logger.info("engine_started", engine_name=engine_name)

        try:
            await self.before_execute(input_data, context=context)
            result = await self.execute(input_data, context=context)
            await self.after_execute(result, context=context)

            completed_at = utc_now()
            duration_seconds = max((completed_at - started_at).total_seconds(), 0.0)
            self.logger.info(
                "engine_completed",
                engine_name=engine_name,
                duration_seconds=duration_seconds,
            )
            return EngineResult[TOutput](
                data=result,
                engine_name=engine_name,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration_seconds,
            )
        except CreatorOSError as error:
            self.logger.exception(
                "engine_failed",
                engine_name=engine_name,
                error_type=type(error).__name__,
                error_code=error.code,
                retryable=error.retryable,
            )
            raise
        except Exception as error:
            wrapped_error = wrap_exception(
                error,
                message=f"{engine_name} engine execution failed",
                exception_type=EngineError,
            )
            self.logger.exception(
                "engine_failed",
                engine_name=engine_name,
                error_type=type(wrapped_error).__name__,
                error_code=wrapped_error.code,
                retryable=wrapped_error.retryable,
            )
            raise wrapped_error from error
        finally:
            clear_context()

    def get_provider(
        self,
        provider_type: str,
        name: str,
    ) -> Provider:
        """Resolve a provider from the engine's provider registry."""

        return self.provider_registry.get(provider_type, name)

    def get_typed_provider(
        self,
        provider_type: str,
        name: str,
        expected_type: type[TProvider],
    ) -> TProvider:
        """Resolve a provider from the engine's provider registry with useful typing."""

        return self.provider_registry.get_typed(provider_type, name, expected_type)

    def _validate_engine_name(self) -> str:
        """Trim and validate the engine name before execution starts."""

        normalized_name = self.name.strip()
        if not normalized_name:
            raise CreatorOSValidationError(
                "engine name must not be blank",
                code="engine_invalid_name",
                details={"field": "name"},
            )
        return normalized_name


__all__ = ["BaseEngine"]
