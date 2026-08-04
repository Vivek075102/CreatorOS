"""Base agent framework for CreatorOS focused reasoning components."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from creatoros.agents.models import AgentExecutionContext, AgentResult
from creatoros.core import AgentError, CreatorOSError, CreatorOSValidationError, wrap_exception
from creatoros.domain import utc_now
from creatoros.observability import bind_context, clear_context, get_logger
from creatoros.providers import Provider, ProviderRegistry, get_provider_registry

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")
TProvider = TypeVar("TProvider")


class BaseAgent[TInput, TOutput](ABC):
    """Abstract base class for CreatorOS agents with shared lifecycle behavior."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.provider_registry = provider_registry or get_provider_registry()
        self.logger = get_logger(f"agents.{self.__class__.__name__.lower()}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable agent name used for logging and results."""

    @abstractmethod
    async def execute(
        self,
        input_data: TInput,
        *,
        context: AgentExecutionContext,
    ) -> TOutput:
        """Run the agent's focused behavior and return the output payload."""

    async def before_execute(
        self,
        input_data: TInput,
        *,
        context: AgentExecutionContext,
    ) -> None:
        """Run optional pre-execution logic."""

    async def after_execute(
        self,
        result: TOutput,
        *,
        context: AgentExecutionContext,
    ) -> None:
        """Run optional post-execution logic."""

    async def run(
        self,
        input_data: TInput,
        *,
        context: AgentExecutionContext,
    ) -> AgentResult[TOutput]:
        """Execute the agent lifecycle and return a structured result."""

        agent_name = self._validate_agent_name()
        bind_context(
            job_id=context.job_id,
            step_id=context.step_id,
            workflow_name=context.workflow_name,
            engine_name=context.engine_name,
        )

        started_at = utc_now()
        self.logger.info(
            "agent_started",
            agent_name=agent_name,
            engine_name=context.engine_name,
        )

        try:
            await self.before_execute(input_data, context=context)
            result = await self.execute(input_data, context=context)
            await self.after_execute(result, context=context)

            completed_at = utc_now()
            duration_seconds = max((completed_at - started_at).total_seconds(), 0.0)
            self.logger.info(
                "agent_completed",
                agent_name=agent_name,
                engine_name=context.engine_name,
                duration_seconds=duration_seconds,
            )
            return AgentResult[TOutput](
                data=result,
                agent_name=agent_name,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration_seconds,
            )
        except CreatorOSError as error:
            self.logger.exception(
                "agent_failed",
                agent_name=agent_name,
                engine_name=context.engine_name,
                error_type=type(error).__name__,
                error_code=error.code,
                retryable=error.retryable,
            )
            raise
        except Exception as error:
            wrapped_error = wrap_exception(
                error,
                message=f"{agent_name} agent execution failed",
                exception_type=AgentError,
            )
            self.logger.exception(
                "agent_failed",
                agent_name=agent_name,
                engine_name=context.engine_name,
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
        """Resolve a provider from the agent's provider registry."""

        return self.provider_registry.get(provider_type, name)

    def get_typed_provider(
        self,
        provider_type: str,
        name: str,
        expected_type: type[TProvider],
    ) -> TProvider:
        """Resolve a provider from the agent's provider registry with useful typing."""

        return self.provider_registry.get_typed(provider_type, name, expected_type)

    def _validate_agent_name(self) -> str:
        """Trim and validate the agent name before execution starts."""

        normalized_name = self.name.strip()
        if not normalized_name:
            raise CreatorOSValidationError(
                "agent name must not be blank",
                code="agent_invalid_name",
                details={"field": "name"},
            )
        return normalized_name


__all__ = ["BaseAgent"]
