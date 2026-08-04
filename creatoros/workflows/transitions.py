"""Workflow execution status transition rules for CreatorOS."""

from __future__ import annotations

from types import MappingProxyType

from creatoros.workflows.enums import WorkflowExecutionStatus

_ALLOWED_TRANSITIONS = MappingProxyType(
    {
        WorkflowExecutionStatus.PENDING: frozenset(
            {
                WorkflowExecutionStatus.RUNNING,
                WorkflowExecutionStatus.CANCELLED,
            },
        ),
        WorkflowExecutionStatus.RUNNING: frozenset(
            {
                WorkflowExecutionStatus.PAUSED,
                WorkflowExecutionStatus.AWAITING_APPROVAL,
                WorkflowExecutionStatus.COMPLETED,
                WorkflowExecutionStatus.FAILED,
                WorkflowExecutionStatus.CANCELLED,
            },
        ),
        WorkflowExecutionStatus.PAUSED: frozenset(
            {
                WorkflowExecutionStatus.RUNNING,
                WorkflowExecutionStatus.CANCELLED,
            },
        ),
        WorkflowExecutionStatus.AWAITING_APPROVAL: frozenset(
            {
                WorkflowExecutionStatus.RUNNING,
                WorkflowExecutionStatus.FAILED,
                WorkflowExecutionStatus.CANCELLED,
            },
        ),
        WorkflowExecutionStatus.COMPLETED: frozenset(),
        WorkflowExecutionStatus.FAILED: frozenset(),
        WorkflowExecutionStatus.CANCELLED: frozenset(),
    },
)

_TERMINAL_STATUSES = frozenset(
    {
        WorkflowExecutionStatus.COMPLETED,
        WorkflowExecutionStatus.FAILED,
        WorkflowExecutionStatus.CANCELLED,
    },
)


def get_allowed_transitions(
    status: WorkflowExecutionStatus,
) -> frozenset[WorkflowExecutionStatus]:
    """Return the immutable set of allowed target statuses for the given status."""

    return _ALLOWED_TRANSITIONS[status]


def is_transition_allowed(
    current: WorkflowExecutionStatus,
    target: WorkflowExecutionStatus,
) -> bool:
    """Return whether a transition between two distinct statuses is allowed."""

    if current is target:
        return False
    return target in get_allowed_transitions(current)


def is_terminal_status(
    status: WorkflowExecutionStatus,
) -> bool:
    """Return whether the supplied status is terminal."""

    return status in _TERMINAL_STATUSES


__all__ = [
    "get_allowed_transitions",
    "is_terminal_status",
    "is_transition_allowed",
]
