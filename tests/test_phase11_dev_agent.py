"""Phase 11 — the autonomous dev agent (ADR-020).

Runs with no live services except the explicitly-gated live-verification
task, which this file does not contain — that task needs real GitHub/Jira
credentials and is run by hand per the plan, not simulated here.
"""

from __future__ import annotations

import json

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



# ─── guardrails.py (Task 4): one pair per gate ─────────────────────────────

from meeting_notes.dev_agent import guardrails as gr  # noqa: E402


def test_tests_green_passes_on_exit_zero() -> None:
    assert gr.gate_tests_green(lambda: (0, "12 passed")).passed is True


def test_tests_green_fails_on_nonzero_exit() -> None:
    result = gr.gate_tests_green(lambda: (1, "FAILED test_x"))
    assert result.passed is False
    assert "FAILED" in result.evidence


def test_lint_type_clean_passes_when_both_are_clean() -> None:
    result = gr.gate_lint_type_clean(lambda: (0, ""), lambda: (0, ""))
    assert result.passed is True


def test_lint_type_clean_fails_when_ruff_is_dirty() -> None:
    result = gr.gate_lint_type_clean(lambda: (1, "E501 line too long"), lambda: (0, ""))
    assert result.passed is False
    assert "ruff" in result.evidence


def test_lint_type_clean_fails_when_mypy_is_dirty() -> None:
    result = gr.gate_lint_type_clean(lambda: (0, ""), lambda: (1, "error: Incompatible types"))
    assert result.passed is False
    assert "mypy" in result.evidence


def test_diff_budget_passes_within_limits() -> None:
    result = gr.gate_diff_budget(["a.py", "b.py"], changed_lines=50)
    assert result.passed is True


def test_diff_budget_fails_over_the_file_limit() -> None:
    files = [f"f{i}.py" for i in range(11)]
    result = gr.gate_diff_budget(files, changed_lines=10, max_files=10)
    assert result.passed is False


def test_diff_budget_fails_over_the_line_limit() -> None:
    result = gr.gate_diff_budget(["a.py"], changed_lines=601, max_lines=600)
    assert result.passed is False


def test_protected_paths_passes_when_clean() -> None:
    assert gr.gate_protected_paths(["meeting_notes/db.py", "tests/test_db.py"]).passed is True


def test_protected_paths_fails_when_touching_env() -> None:
    result = gr.gate_protected_paths([".env"])
    assert result.passed is False
    assert ".env" in result.evidence


def test_protected_paths_allows_env_example() -> None:
    """.env.example holds no secrets -- it is the committed template."""
    assert gr.gate_protected_paths([".env.example"]).passed is True


def test_protected_paths_fails_on_ci_config() -> None:
    assert gr.gate_protected_paths([".github/workflows/ci.yml"]).passed is False


def test_protected_paths_fails_on_key_material() -> None:
    assert gr.gate_protected_paths(["deploy/id_rsa"]).passed is False


def test_protected_paths_fails_on_paths_escaping_the_repo() -> None:
    assert gr.gate_protected_paths(["../../etc/passwd"]).passed is False
    assert gr.gate_protected_paths(["/etc/passwd"]).passed is False


def test_no_new_deps_passes_when_untouched() -> None:
    assert gr.gate_no_new_deps(["meeting_notes/db.py"], "").passed is True


def test_no_new_deps_fails_without_the_opt_in_token() -> None:
    result = gr.gate_no_new_deps(["pyproject.toml"], "just implement the feature")
    assert result.passed is False


def test_no_new_deps_passes_with_opt_in_and_pinned_version() -> None:
    result = gr.gate_no_new_deps(
        ["pyproject.toml"], "allow-new-dependency: add httpx-caching==1.0.0",
        added_dep_lines=["httpx-caching==1.0.0"],
    )
    assert result.passed is True


def test_no_new_deps_fails_with_opt_in_but_unpinned() -> None:
    result = gr.gate_no_new_deps(
        ["pyproject.toml"], "allow-new-dependency: add httpx-caching",
        added_dep_lines=["httpx-caching"],
    )
    assert result.passed is False


def test_secret_scan_passes_on_clean_lines() -> None:
    assert gr.gate_secret_scan(["x = 1", "def foo(): pass"]).passed is True


def test_secret_scan_catches_an_anthropic_style_key() -> None:
    result = gr.gate_secret_scan(["API_KEY = 'sk-ant-abc123def456ghi789'"])
    assert result.passed is False


def test_secret_scan_catches_a_github_token() -> None:
    assert gr.gate_secret_scan(["token = ghp_abcdefghijklmnopqrstuvwxyz1234"]).passed is False


def test_secret_scan_catches_a_private_key_header() -> None:
    assert gr.gate_secret_scan(["-----BEGIN RSA PRIVATE KEY-----"]).passed is False


def test_module_boundaries_passes_for_sql_inside_db_py() -> None:
    result = gr.gate_module_boundaries({"meeting_notes/db.py": 'x = "SELECT * FROM t"'})
    assert result.passed is True


def test_module_boundaries_fails_for_sql_outside_db_py() -> None:
    """CLAUDE.md: DO NOT put SQL outside meeting_notes/db.py."""
    result = gr.gate_module_boundaries(
        {"meeting_notes/pipeline.py": 'x = "SELECT * FROM staged_records"'}
    )
    assert result.passed is False
    assert "sql" in result.evidence


def test_module_boundaries_fails_for_cypher_outside_graph_client() -> None:
    """CLAUDE.md: generic Cypher lives only in graph_client.py."""
    result = gr.gate_module_boundaries(
        {"meeting_notes/dev_agent/orchestrator.py": 'q = "MERGE (t:Ticket {id: $id})"'}
    )
    assert result.passed is False
    assert "cypher" in result.evidence


def test_module_boundaries_fails_for_a_mage_call_outside_graph_algorithms() -> None:
    """CLAUDE.md: MAGE CALL procedures live only in graph_algorithms.py."""
    result = gr.gate_module_boundaries(
        {"meeting_notes/memory/vector.py": 'q = "CALL vector_search.search(1)"'}
    )
    assert result.passed is False
    assert "mage-call" in result.evidence


def test_module_boundaries_ignores_ordinary_identifiers() -> None:
    """A variable literally named `merge` must not trip the Cypher check."""
    result = gr.gate_module_boundaries({"meeting_notes/utils.py": "def merge(a, b): return a"})
    assert result.passed is True


def test_module_boundaries_falls_back_to_raw_source_on_a_syntax_error() -> None:
    """A partial agent edit may not parse. Over-flagging is the safe direction."""
    result = gr.gate_module_boundaries(
        {"meeting_notes/pipeline.py": "def broken(:\n    SELECT * FROM t"}
    )
    assert result.passed is False


def test_all_passed_requires_every_gate() -> None:
    ok = [gr.GateResult(name="a", passed=True, evidence="")]
    mixed = [gr.GateResult(name="a", passed=True, evidence=""),
             gr.GateResult(name="b", passed=False, evidence="")]
    assert gr.all_passed(ok) is True
    assert gr.all_passed(mixed) is False


def test_failed_gates_returns_only_the_failures() -> None:
    mixed = [gr.GateResult(name="a", passed=True, evidence=""),
             gr.GateResult(name="b", passed=False, evidence="boom")]
    failed = gr.failed_gates(mixed)
    assert len(failed) == 1 and failed[0].name == "b"


# ─── self_verify.py (Task 5) ────────────────────────────────────────────────

from meeting_notes.dev_agent import self_verify  # noqa: E402


def test_passed_requires_all_three_conditions_independently() -> None:
    """Each of checked/addresses/confidence must independently gate .passed --
    a verdict that satisfies any two of three must still be False."""
    base = dict(checked=True, addresses=True, confidence=0.9, threshold=0.6)

    assert self_verify.VerifyVerdict(**base).passed is True
    assert self_verify.VerifyVerdict(**{**base, "checked": False}).passed is False
    assert self_verify.VerifyVerdict(**{**base, "addresses": False}).passed is False
    assert self_verify.VerifyVerdict(**{**base, "confidence": 0.1}).passed is False


def test_default_verdict_is_unpassed() -> None:
    assert self_verify.VerifyVerdict().passed is False


async def test_verify_pr_parses_a_good_response() -> None:
    async def fake_oneshot(prompt, timeout_seconds, model=None):
        return json.dumps({"addresses": True, "confidence": 0.85, "reason": "matches"})

    verdict = await self_verify.verify_pr(
        {"key": "SCRUM-1", "summary": "x"}, "diff --git a/x", run_oneshot=fake_oneshot
    )
    assert verdict.checked is True
    assert verdict.passed is True


async def test_verify_pr_degrades_to_unchecked_on_a_malformed_response() -> None:
    """Must never raise -- verification is best-effort and must not block the
    review transition."""
    async def garbage_oneshot(prompt, timeout_seconds, model=None):
        return "not json at all"

    verdict = await self_verify.verify_pr(
        {"key": "SCRUM-1", "summary": "x"}, "diff", run_oneshot=garbage_oneshot
    )
    assert verdict.checked is False
    assert verdict.passed is False


async def test_verify_pr_degrades_to_unchecked_when_the_runner_raises() -> None:
    async def exploding_oneshot(prompt, timeout_seconds, model=None):
        raise RuntimeError("backend unreachable")

    verdict = await self_verify.verify_pr(
        {"key": "SCRUM-1", "summary": "x"}, "diff", run_oneshot=exploding_oneshot
    )
    assert verdict.checked is False


async def test_verify_pr_degrades_to_unchecked_on_empty_output() -> None:
    async def empty_oneshot(prompt, timeout_seconds, model=None):
        return None

    verdict = await self_verify.verify_pr(
        {"key": "SCRUM-1", "summary": "x"}, "diff", run_oneshot=empty_oneshot
    )
    assert verdict.checked is False


async def test_verify_pr_respects_a_custom_threshold() -> None:
    async def fake_oneshot(prompt, timeout_seconds, model=None):
        return json.dumps({"addresses": True, "confidence": 0.7, "reason": "ok"})

    low_bar = await self_verify.verify_pr(
        {"key": "SCRUM-1", "summary": "x"}, "diff", threshold=0.5, run_oneshot=fake_oneshot
    )
    high_bar = await self_verify.verify_pr(
        {"key": "SCRUM-1", "summary": "x"}, "diff", threshold=0.9, run_oneshot=fake_oneshot
    )
    assert low_bar.passed is True
    assert high_bar.passed is False
