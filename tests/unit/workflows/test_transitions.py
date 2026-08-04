"""Unit tests for CreatorOS workflow execution transition rules."""

from creatoros.workflows import (
    WorkflowExecutionStatus,
    get_allowed_transitions,
    is_terminal_status,
    is_transition_allowed,
)


def test_every_allowed_transition_returns_true() -> None:
    """Allowed workflow transitions should return True."""

    assert is_transition_allowed(WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.RUNNING)
    assert is_transition_allowed(WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.CANCELLED)
    assert is_transition_allowed(WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.PAUSED)
    assert is_transition_allowed(WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.AWAITING_APPROVAL)
    assert is_transition_allowed(WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.COMPLETED)
    assert is_transition_allowed(WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.FAILED)
    assert is_transition_allowed(WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.CANCELLED)
    assert is_transition_allowed(WorkflowExecutionStatus.PAUSED, WorkflowExecutionStatus.RUNNING)
    assert is_transition_allowed(WorkflowExecutionStatus.PAUSED, WorkflowExecutionStatus.CANCELLED)
    assert is_transition_allowed(
        WorkflowExecutionStatus.AWAITING_APPROVAL,
        WorkflowExecutionStatus.RUNNING,
    )
    assert is_transition_allowed(
        WorkflowExecutionStatus.AWAITING_APPROVAL,
        WorkflowExecutionStatus.FAILED,
    )
    assert is_transition_allowed(
        WorkflowExecutionStatus.AWAITING_APPROVAL,
        WorkflowExecutionStatus.CANCELLED,
    )


def test_every_unlisted_transition_returns_false() -> None:
    """Unlisted transitions should return False."""

    assert not is_transition_allowed(WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.PAUSED)
    assert not is_transition_allowed(WorkflowExecutionStatus.PAUSED, WorkflowExecutionStatus.COMPLETED)
    assert not is_transition_allowed(
        WorkflowExecutionStatus.AWAITING_APPROVAL,
        WorkflowExecutionStatus.COMPLETED,
    )
    assert not is_transition_allowed(WorkflowExecutionStatus.COMPLETED, WorkflowExecutionStatus.RUNNING)


def test_same_status_transitions_are_rejected() -> None:
    """Transitions to the current status should not be allowed."""

    for status in WorkflowExecutionStatus:
        assert not is_transition_allowed(status, status)


def test_terminal_states_have_no_transitions() -> None:
    """Terminal states should not allow any outgoing transitions."""

    assert get_allowed_transitions(WorkflowExecutionStatus.COMPLETED) == frozenset()
    assert get_allowed_transitions(WorkflowExecutionStatus.FAILED) == frozenset()
    assert get_allowed_transitions(WorkflowExecutionStatus.CANCELLED) == frozenset()


def test_returned_transition_sets_are_immutable() -> None:
    """Returned transition sets should be immutable."""

    transitions = get_allowed_transitions(WorkflowExecutionStatus.RUNNING)

    assert isinstance(transitions, frozenset)


def test_is_terminal_status_identifies_exact_terminal_states() -> None:
    """Only completed, failed, and cancelled should be terminal."""

    assert is_terminal_status(WorkflowExecutionStatus.COMPLETED)
    assert is_terminal_status(WorkflowExecutionStatus.FAILED)
    assert is_terminal_status(WorkflowExecutionStatus.CANCELLED)
    assert not is_terminal_status(WorkflowExecutionStatus.PENDING)
    assert not is_terminal_status(WorkflowExecutionStatus.RUNNING)
    assert not is_terminal_status(WorkflowExecutionStatus.PAUSED)
    assert not is_terminal_status(WorkflowExecutionStatus.AWAITING_APPROVAL)
