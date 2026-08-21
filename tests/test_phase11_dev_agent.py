"""Phase 11 — the autonomous dev agent (ADR-020).

Runs with no live services except the explicitly-gated live-verification
task, which this file does not contain — that task needs real GitHub/Jira
credentials and is run by hand per the plan, not simulated here.
"""

from __future__ import annotations

import pytest

from meeting_notes.dev_agent import lifecycle

# ─── the bug fix (ADR-020) ─────────────────────────────────────────────────────


def test_shipped_is_terminal() -> None:
    """The bug, precisely. v5's TERMINAL_STATES omitted SHIPPED, and a
    confirmed-live consequence was 61 AgentRun nodes for one ticket."""
    assert lifecycle.is_terminal(lifecycle.SHIPPED) is True


def test_closed_failed_and_needs_human_are_also_terminal() -> None:
    for state in (lifecycle.CLOSED, lifecycle.FAILED, lifecycle.NEEDS_HUMAN):
        assert lifecycle.is_terminal(state) is True


def test_active_states_are_not_terminal() -> None:
    for state in (lifecycle.TRIAGED, lifecycle.PLANNED, lifecycle.IMPLEMENTING,
                  lifecycle.DEBUGGING, lifecycle.REVIEWING):
        assert lifecycle.is_terminal(state) is False


def test_shipped_only_transitions_to_closed() -> None:
    """CLOSED means an actual merge. Nothing else follows SHIPPED."""
    assert lifecycle.can_transition(lifecycle.SHIPPED, lifecycle.CLOSED) is True
    assert lifecycle.can_transition(lifecycle.SHIPPED, lifecycle.IMPLEMENTING) is False
    assert lifecycle.can_transition(lifecycle.SHIPPED, lifecycle.TRIAGED) is False


def test_shipped_does_not_escalate() -> None:
    """A shipped run is done. It does not additionally become FAILED or
    NEEDS_HUMAN -- that would be a second, contradictory outcome for one run."""
    assert lifecycle.can_transition(lifecycle.SHIPPED, lifecycle.FAILED) is False
    assert lifecycle.can_transition(lifecycle.SHIPPED, lifecycle.NEEDS_HUMAN) is False


def test_illegal_transitions_raise() -> None:
    with pytest.raises(lifecycle.IllegalTransition):
        lifecycle.assert_transition(lifecycle.TRIAGED, lifecycle.SHIPPED)


def test_assert_transition_passes_silently_for_a_legal_edge() -> None:
    lifecycle.assert_transition(lifecycle.TRIAGED, lifecycle.PLANNED)  # must not raise


def test_unknown_states_raise() -> None:
    with pytest.raises(lifecycle.IllegalTransition):
        lifecycle.assert_transition("NOT_A_STATE", lifecycle.PLANNED)
    with pytest.raises(lifecycle.IllegalTransition):
        lifecycle.assert_transition(lifecycle.TRIAGED, "NOT_A_STATE")


def test_debugging_can_loop_back_to_implementing() -> None:
    """The self-fix loop: the agent's own test run fails, it retries."""
    assert lifecycle.can_transition(lifecycle.DEBUGGING, lifecycle.IMPLEMENTING) is True


def test_reviewing_can_loop_back_to_implementing() -> None:
    """The review-feedback loop."""
    assert lifecycle.can_transition(lifecycle.REVIEWING, lifecycle.IMPLEMENTING) is True


def test_the_happy_path_is_fully_connected() -> None:
    path = [lifecycle.TRIAGED, lifecycle.PLANNED, lifecycle.IMPLEMENTING,
            lifecycle.DEBUGGING, lifecycle.REVIEWING, lifecycle.SHIPPED, lifecycle.CLOSED]
    for a, b in zip(path, path[1:]):
        assert lifecycle.can_transition(a, b), f"{a} -> {b} should be legal"


def test_every_active_state_can_escalate_to_needs_human() -> None:
    """A human can always be pulled in — there is no state that traps a stuck
    run with no way to flag it."""
    for state in lifecycle.ALL_STATES - lifecycle.TERMINAL_STATES:
        assert lifecycle.can_transition(state, lifecycle.NEEDS_HUMAN), state


def test_every_active_state_can_escalate_to_failed() -> None:
    for state in lifecycle.ALL_STATES - lifecycle.TERMINAL_STATES:
        assert lifecycle.can_transition(state, lifecycle.FAILED), state


def test_terminal_states_have_no_outgoing_edges_except_shipped() -> None:
    """SHIPPED -> CLOSED is the one deliberate exception; the rest are dead ends."""
    for state in lifecycle.TERMINAL_STATES - {lifecycle.SHIPPED}:
        assert lifecycle._TRANSITIONS[state] == frozenset(), state


# ─── deterministic ids ──────────────────────────────────────────────────────


def test_run_id_is_stable_for_the_same_ticket_and_attempt() -> None:
    assert lifecycle.run_id("SCRUM-1", 1) == lifecycle.run_id("SCRUM-1", 1)


def test_run_id_differs_by_attempt() -> None:
    """A retry must not collide with the run it is retrying."""
    assert lifecycle.run_id("SCRUM-1", 1) != lifecycle.run_id("SCRUM-1", 2)


def test_run_id_differs_by_ticket() -> None:
    assert lifecycle.run_id("SCRUM-1", 1) != lifecycle.run_id("SCRUM-2", 1)


def test_ticket_and_pull_request_ids_are_deterministic() -> None:
    assert lifecycle.ticket_node_id("SCRUM-1") == lifecycle.ticket_node_id("SCRUM-1")
    assert lifecycle.pull_request_node_id("https://x/1") == lifecycle.pull_request_node_id(
        "https://x/1"
    )
    assert lifecycle.ticket_node_id("SCRUM-1") != lifecycle.pull_request_node_id("SCRUM-1"), (
        "different namespaces must not collide even on the same raw string"
    )
