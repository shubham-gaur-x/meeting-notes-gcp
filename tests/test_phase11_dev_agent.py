"""Phase 11 — the autonomous dev agent (ADR-020).

Runs with no live services except the explicitly-gated live-verification
task, which this file does not contain — that task needs real GitHub/Jira
credentials and is run by hand per the plan, not simulated here.
"""

from __future__ import annotations

import pytest

from meeting_notes.dev_agent import lifecycle
from meeting_notes.dev_agent.models import DevAgentRun

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
    for a, b in zip(path, path[1:], strict=False):
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


# ─── db.py: dev_agent_runs (Task 1) ────────────────────────────────────────────

from meeting_notes.db import (  # noqa: E402
    ACTIVE_RUN_EXCLUDED_STATES,
    DEV_AGENT_SCHEMA_SQL,
)


def _norm(sql: str) -> str:
    return " ".join(sql.split()).upper()


def test_active_run_exclusion_is_built_from_terminal_states_not_a_second_list() -> None:
    """The other half of the ADR-020 fix. If this equality ever fails, someone
    reintroduced the exact drift that caused the original bug: two places
    spelling "terminal" independently."""
    assert ACTIVE_RUN_EXCLUDED_STATES == lifecycle.TERMINAL_STATES


def test_dev_agent_runs_schema_has_one_state_column_not_two() -> None:
    """v5 had `state` AND `status` -- two overlapping vocabularies for the same
    fact. One column, one vocabulary (lifecycle.py's)."""
    up = _norm(DEV_AGENT_SCHEMA_SQL)
    assert "CREATE TABLE IF NOT EXISTS DEV_AGENT_RUNS" in up
    assert " STATE " in up or "STATE TEXT" in up
    assert " STATUS " not in up, "a second status column reintroduces the v5 drift"


def test_dev_agent_runs_schema_is_idempotent() -> None:
    up = _norm(DEV_AGENT_SCHEMA_SQL)
    assert up.count("CREATE TABLE") == up.count("CREATE TABLE IF NOT EXISTS")


def test_ticket_key_is_unique_so_a_second_claim_upserts() -> None:
    assert "UNIQUE" in _norm(DEV_AGENT_SCHEMA_SQL) or "PRIMARY KEY" in _norm(DEV_AGENT_SCHEMA_SQL)


# ─── should_attempt: the independent second check ──────────────────────────


import meeting_notes.db as db  # noqa: E402


async def test_should_attempt_refuses_a_shipped_ticket() -> None:
    """The second half of the ADR-020 fix, exercised directly against the
    function orchestrator.poll_and_process is required to call before
    resuming anything get_active_dev_agent_run returns."""
    async def fake_get(ticket_key, pool=None):
        return DevAgentRun(ticket_key=ticket_key, state=lifecycle.SHIPPED, attempt_count=1)

    original = db.get_dev_agent_run
    db.get_dev_agent_run = fake_get  # type: ignore[assignment]
    try:
        allowed = await db.should_attempt_dev_agent_run("SCRUM-1", max_attempts=1)
    finally:
        db.get_dev_agent_run = original  # type: ignore[assignment]

    assert allowed is False


async def test_should_attempt_allows_a_fresh_ticket() -> None:
    async def fake_get(ticket_key, pool=None):
        return None

    original = db.get_dev_agent_run
    db.get_dev_agent_run = fake_get  # type: ignore[assignment]
    try:
        assert await db.should_attempt_dev_agent_run("SCRUM-2", max_attempts=1) is True
    finally:
        db.get_dev_agent_run = original  # type: ignore[assignment]


async def test_should_attempt_allows_a_retry_of_a_failed_ticket_under_the_cap() -> None:
    async def fake_get(ticket_key, pool=None):
        return DevAgentRun(ticket_key=ticket_key, state=lifecycle.FAILED, attempt_count=1)

    original = db.get_dev_agent_run
    db.get_dev_agent_run = fake_get  # type: ignore[assignment]
    try:
        assert await db.should_attempt_dev_agent_run("SCRUM-3", max_attempts=3) is True
        assert await db.should_attempt_dev_agent_run("SCRUM-3", max_attempts=1) is False
    finally:
        db.get_dev_agent_run = original  # type: ignore[assignment]


async def test_should_attempt_refuses_a_run_already_in_flight() -> None:
    async def fake_get(ticket_key, pool=None):
        return DevAgentRun(ticket_key=ticket_key, state=lifecycle.IMPLEMENTING, attempt_count=1)

    original = db.get_dev_agent_run
    db.get_dev_agent_run = fake_get  # type: ignore[assignment]
    try:
        assert await db.should_attempt_dev_agent_run("SCRUM-4", max_attempts=3) is False
    finally:
        db.get_dev_agent_run = original  # type: ignore[assignment]

