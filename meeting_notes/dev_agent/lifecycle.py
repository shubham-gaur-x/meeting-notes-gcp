"""Dev-agent run lifecycle: states, the legal-transition table, deterministic IDs.

A run moves through an explicit state machine so a crashed process resumes
from where it left off instead of restarting or double-shipping. Illegal
transitions raise, turning a logic bug into a loud failure instead of silent
corruption.

    TRIAGED -> PLANNED -> IMPLEMENTING -> DEBUGGING -> REVIEWING -> SHIPPED -> CLOSED

with DEBUGGING -> IMPLEMENTING (self-fix) and REVIEWING -> IMPLEMENTING (review
feedback) as the two backward edges, and FAILED / NEEDS_HUMAN reachable from
any active state.

**`SHIPPED` is terminal — this is the ADR-020 fix, not a detail.** v5's
`TERMINAL_STATES` omitted it. `db.get_active_dev_agent_run()`'s SQL
independently hardcoded the same three-state exclusion, already drifted from
`TERMINAL_STATES` in the sense that nothing kept them in sync, and the poller
resumed a shipped run on every single poll with no `should_attempt()` check
at all. 61 `AgentRun` nodes for one ticket in the live v5 graph. The fix has
two independent parts: `SHIPPED` joins this set, and `meeting_notes.db`
builds its exclusion list *from* `TERMINAL_STATES` rather than a second
literal, so the two cannot drift again by construction.

ID derivation (single source of truth — re-derive identically everywhere):
  * run_id            = uuid5("dev-agent-run", f"{ticket_key}#{attempt}")
  * Ticket node       = uuid5("ticket", ticket_key)
  * PullRequest node  = uuid5("pullrequest", pr_url)
A writer/reader ID mismatch is a known past bug class (CLAUDE.md), so these
live in one place.
"""

from __future__ import annotations

from meeting_notes.utils import uuid5_id

TRIAGED = "TRIAGED"
PLANNED = "PLANNED"
IMPLEMENTING = "IMPLEMENTING"
DEBUGGING = "DEBUGGING"
REVIEWING = "REVIEWING"
SHIPPED = "SHIPPED"
CLOSED = "CLOSED"
FAILED = "FAILED"
NEEDS_HUMAN = "NEEDS_HUMAN"

ALL_STATES: frozenset[str] = frozenset(
    {TRIAGED, PLANNED, IMPLEMENTING, DEBUGGING, REVIEWING, SHIPPED, CLOSED, FAILED, NEEDS_HUMAN}
)

# Terminal: no run continues past these. FAILED may be retried as a NEW run
# (a fresh attempt), which is a different row/attempt number, not a resume.
TERMINAL_STATES: frozenset[str] = frozenset({SHIPPED, CLOSED, FAILED, NEEDS_HUMAN})

# Any active (non-terminal) state may escalate to FAILED or NEEDS_HUMAN.
_ESCALATIONS: frozenset[str] = frozenset({FAILED, NEEDS_HUMAN})

_TRANSITIONS: dict[str, frozenset[str]] = {
    TRIAGED: frozenset({PLANNED}),
    PLANNED: frozenset({IMPLEMENTING}),
    IMPLEMENTING: frozenset({DEBUGGING}),
    DEBUGGING: frozenset({REVIEWING, IMPLEMENTING}),  # self-fix loop
    REVIEWING: frozenset({SHIPPED, IMPLEMENTING}),  # review-feedback loop
    SHIPPED: frozenset({CLOSED}),  # only an actual merge closes it
    CLOSED: frozenset(),
    FAILED: frozenset(),
    NEEDS_HUMAN: frozenset(),
}
_TRANSITIONS = {
    state: (targets | _ESCALATIONS if state not in TERMINAL_STATES else targets)
    for state, targets in _TRANSITIONS.items()
}


class IllegalTransitionError(RuntimeError):
    """Raised when a run is asked to move between two states with no legal edge."""


def can_transition(from_state: str, to_state: str) -> bool:
    """True if ``from_state -> to_state`` is a legal edge."""
    return to_state in _TRANSITIONS.get(from_state, frozenset())


def assert_transition(from_state: str, to_state: str) -> None:
    """Raise :class:`IllegalTransitionError` unless the edge is legal."""
    if from_state not in ALL_STATES:
        raise IllegalTransitionError(f"unknown source state {from_state!r}")
    if to_state not in ALL_STATES:
        raise IllegalTransitionError(f"unknown target state {to_state!r}")
    if not can_transition(from_state, to_state):
        raise IllegalTransitionError(f"illegal transition {from_state} -> {to_state}")


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def run_id(ticket_key: str, attempt: int) -> str:
    return uuid5_id("dev-agent-run", f"{ticket_key}#{attempt}")


def ticket_node_id(ticket_key: str) -> str:
    return uuid5_id("ticket", ticket_key)


def pull_request_node_id(pr_url: str) -> str:
    return uuid5_id("pullrequest", pr_url)
