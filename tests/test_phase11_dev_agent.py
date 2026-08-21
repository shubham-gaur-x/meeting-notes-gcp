"""Phase 11 — the autonomous dev agent (ADR-020).

Runs with no live services except the explicitly-gated live-verification
task, which this file does not contain — that task needs real GitHub/Jira
credentials and is run by hand per the plan, not simulated here.
"""

from __future__ import annotations

import json

import pytest

from meeting_notes.dev_agent import lifecycle
from meeting_notes.dev_agent.models import ClaudeRunResult, DevAgentRun

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


# ─── backend.py (Task 6): coding-model routing, NOT llm_client ─────────────

from meeting_notes.dev_agent import backend as dab  # noqa: E402


def _settings(**over):
    from meeting_notes.config import Settings

    return Settings(_env_file=None, **over)


def test_select_backend_reads_dev_agent_llm_backend() -> None:
    for name in ("local", "vertex", "claude"):
        assert dab.select_backend(_settings(DEV_AGENT_LLM_BACKEND=name)) == name


def test_select_backend_defaults_to_local() -> None:
    assert dab.select_backend(_settings()) == "local"


def test_select_backend_rejects_an_unknown_value() -> None:
    with pytest.raises(ValueError, match="Invalid"):
        dab.select_backend(_settings(DEV_AGENT_LLM_BACKEND="groq"))


def test_local_backend_empties_the_anthropic_api_key() -> None:
    """A real key sitting in the parent environment must never let a local
    run route to api.anthropic.com."""
    env = dab.resolve_backend_env("local", _settings())
    assert env["ANTHROPIC_API_KEY"] == ""


def test_local_backend_pins_both_the_main_and_small_fast_model() -> None:
    """LM Studio's JIT loader evicts the loaded coder model and reloads at a
    default 8192 context if Claude Code requests an unknown background model
    id -- v5's original blocker, reproduced live. Pinning both avoids it."""
    env = dab.resolve_backend_env("local", _settings(DEV_AGENT_LM_MODEL="qwen-coder-7b"))
    assert env["ANTHROPIC_MODEL"] == "qwen-coder-7b"
    assert env["ANTHROPIC_SMALL_FAST_MODEL"] == "qwen-coder-7b"


def test_vertex_backend_sets_the_use_vertex_flag_and_no_api_key() -> None:
    """ADR-020's actual fix: authentication is Application Default
    Credentials, the same path llm_client.py already proved. No key at all."""
    env = dab.resolve_backend_env(
        "vertex", _settings(GCP_PROJECT_ID="my-proj", VERTEX_LOCATION="us-east4")
    )
    assert env["CLAUDE_CODE_USE_VERTEX"] == "1"
    assert env["ANTHROPIC_VERTEX_PROJECT_ID"] == "my-proj"
    assert env["CLOUD_ML_REGION"] == "us-east4"
    assert env["ANTHROPIC_API_KEY"] == ""


def test_claude_backend_sets_the_real_key_and_routes_to_anthropic() -> None:
    env = dab.resolve_backend_env(
        "claude", _settings(DEV_AGENT_ANTHROPIC_API_KEY="sk-ant-leakcanary")
    )
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-leakcanary"
    assert env["ANTHROPIC_BASE_URL"] == "https://api.anthropic.com"


def test_resolve_backend_env_covers_all_valid_backends() -> None:
    """v5 stated this as a discipline explicitly; assert it directly rather
    than trusting the three tests above happen to cover everything."""
    for name in dab.VALID_BACKENDS:
        env = dab.resolve_backend_env(name, _settings(GCP_PROJECT_ID="p"))
        assert "ANTHROPIC_API_KEY" in env


def test_model_for_run_reads_the_matching_setting_per_backend() -> None:
    s = _settings(
        DEV_AGENT_LM_MODEL="local-model", DEV_AGENT_VERTEX_MODEL="claude-vertex-model",
        DEV_AGENT_CLAUDE_MODEL="claude-direct-model",
    )
    assert dab.model_for_run("local", s) == "local-model"
    assert dab.model_for_run("vertex", s) == "claude-vertex-model"
    assert dab.model_for_run("claude", s) == "claude-direct-model"


def test_select_loaded_model_requires_the_minimum_context() -> None:
    models = [{"state": "loaded", "type": "llm", "id": "m1", "loaded_context_length": 8192}]
    ok, detail = dab.select_loaded_model(models, min_context=32768)
    assert ok is False
    assert "8192" in detail


def test_select_loaded_model_ignores_embedding_models() -> None:
    models = [{"state": "loaded", "type": "embeddings", "id": "e1", "loaded_context_length": 99999}]
    ok, _ = dab.select_loaded_model(models, min_context=1000)
    assert ok is False


def test_select_loaded_model_picks_the_best_of_several() -> None:
    models = [
        {"state": "loaded", "type": "llm", "id": "small", "loaded_context_length": 4096},
        {"state": "loaded", "type": "llm", "id": "big", "loaded_context_length": 32768},
    ]
    ok, detail = dab.select_loaded_model(models, min_context=16384)
    assert ok is True
    assert "big" in detail


async def test_preflight_vertex_fails_without_a_project_id() -> None:
    with pytest.raises(dab.PreflightError, match="GCP_PROJECT_ID"):
        dab.preflight_vertex(_settings(GCP_PROJECT_ID=""))


async def test_preflight_vertex_passes_with_a_project_id() -> None:
    detail = dab.preflight_vertex(_settings(GCP_PROJECT_ID="my-proj"))
    assert "my-proj" in detail


async def test_preflight_claude_fails_without_a_key() -> None:
    with pytest.raises(dab.PreflightError, match="DEV_AGENT_ANTHROPIC_API_KEY"):
        dab.preflight_claude(_settings(DEV_AGENT_ANTHROPIC_API_KEY=""))


async def test_preflight_dispatches_to_the_right_backend_check() -> None:
    with pytest.raises(dab.PreflightError, match="GCP_PROJECT_ID"):
        await dab.preflight("vertex", _settings(GCP_PROJECT_ID=""))


def test_dev_agent_never_imports_llm_client() -> None:
    """CLAUDE.md: coding-model routing stays out of llm_client.py on purpose --
    a subprocess with tool access is not a chat_json/embed call. Checks for an
    actual import STATEMENT, not the string -- this module's own docstring
    explains why llm_client is deliberately unused, which a bare substring
    check would misread as a violation (same trap as the pipeline/retrieval
    and api/scheduler guards earlier in this project)."""
    import re
    from pathlib import Path

    source = Path(dab.__file__).read_text()
    importing = re.compile(r"^\s*(from\s+\S*llm_client\S*\s+import|import\s+\S*llm_client)", re.M)
    assert not importing.search(source)


# ─── git_ops.py, github_client.py, claude_runner.py, session_memory.py (Task 7)

from meeting_notes.dev_agent import git_ops, session_memory  # noqa: E402


def test_authed_remote_url_embeds_the_token() -> None:
    url = git_ops.authed_remote_url("acme", "repo", "gh-tok")
    assert url == "https://x-access-token:gh-tok@github.com/acme/repo.git"


async def test_create_worktree_removes_a_stale_worktree_first() -> None:
    """A previous failed attempt can leave a worktree/branch behind. The next
    attempt must not fail trying to create over it."""
    calls: list[list[str]] = []

    async def fake_run_git(args, cwd=None):
        calls.append(args)
        if args[:2] == ["worktree", "remove"]:
            return ""  # succeeds this time
        return ""

    original = git_ops._run_git
    git_ops._run_git = fake_run_git  # type: ignore[assignment]
    try:
        await git_ops.create_worktree("/repo", "/work/SCRUM-1", "agent/SCRUM-1")
    finally:
        git_ops._run_git = original  # type: ignore[assignment]

    kinds = [c[0] for c in calls]
    assert "fetch" in kinds

    add_index = next(i for i, c in enumerate(calls) if c[:2] == ["worktree", "add"])
    assert calls[add_index] == [
        "worktree", "add", "-b", "agent/SCRUM-1", "/work/SCRUM-1", "origin/main"
    ]
    # the stale-removal attempts happened before the add, not after
    assert any(c[:2] == ["worktree", "remove"] for c in calls[:add_index])


async def test_ensure_repo_cloned_always_clones_fresh() -> None:
    """Cloud Run Jobs have no persistent filesystem between executions -- there
    is never an existing checkout to fetch into, unlike v5's Docker Compose
    assumption."""
    calls: list[list[str]] = []

    async def fake_run_git(args, cwd=None):
        calls.append(args)
        return ""

    original = git_ops._run_git
    git_ops._run_git = fake_run_git  # type: ignore[assignment]
    try:
        await git_ops.ensure_repo_cloned("/repo", "acme", "widget", "tok")
    finally:
        git_ops._run_git = original  # type: ignore[assignment]

    assert calls == [["clone", git_ops.authed_remote_url("acme", "widget", "tok"), "/repo"]]


def test_files_from_diff_extracts_the_b_side() -> None:
    diff = (
        "diff --git a/meeting_notes/db.py b/meeting_notes/db.py\n"
        "index abc..def 100644\n"
        "diff --git a/tests/test_db.py b/tests/test_db.py\n"
    )
    assert session_memory.files_from_diff(diff) == ["meeting_notes/db.py", "tests/test_db.py"]


def test_files_from_diff_handles_no_diff() -> None:
    assert session_memory.files_from_diff("") == []


def test_build_memory_shapes_pr_opened_differently_from_failed() -> None:
    opened = session_memory.build_memory(
        {"key": "SCRUM-1", "summary": "x"}, outcome="pr_opened",
        pr={"html_url": "https://x/1"}, files_changed=["a.py"],
    )
    failed = session_memory.build_memory(
        {"key": "SCRUM-1", "summary": "x"}, outcome="failed", error="tests failed",
    )
    assert "Opened PR" in opened["work_completed"][0]
    assert opened["blockers"] == []
    assert failed["work_completed"] == []
    assert "tests failed" in failed["blockers"][0]


def test_build_memory_flags_a_low_confidence_verdict_as_a_next_action() -> None:
    class _Verdict:
        checked = True
        passed = False

    memory = session_memory.build_memory(
        {"key": "SCRUM-1", "summary": "x"}, outcome="pr_opened",
        pr={"html_url": "https://x/1"}, verdict=_Verdict(),
    )
    assert any("human review" in a.lower() for a in memory["next_actions"])


async def test_record_never_raises_when_persistence_fails() -> None:
    """Session memory is best-effort -- a failing save must not crash the run."""
    async def exploding_save(ticket_key, memory):
        raise RuntimeError("db down")

    memory = await session_memory.record(
        {"key": "SCRUM-1", "summary": "x"}, outcome="failed", error="e", save=exploding_save
    )
    assert memory["outcome"] == "failed"  # still returns the built memory


async def test_load_resume_context_returns_none_when_nothing_saved() -> None:
    async def empty_load(ticket_key):
        return None

    assert await session_memory.load_resume_context("SCRUM-1", load=empty_load) is None


async def test_load_resume_context_returns_the_saved_context() -> None:
    async def fake_load(ticket_key):
        return {"resume_context": "pick up where you left off"}

    result = await session_memory.load_resume_context("SCRUM-1", load=fake_load)
    assert result == "pick up where you left off"


# claude_runner and github_client are exercised via orchestrator tests (Task 8),
# where they are naturally injected as dependencies of process_ticket.


# ─── orchestrator.py (Task 8): the fix, end to end ─────────────────────────

from meeting_notes.dev_agent import orchestrator  # noqa: E402


def test_the_prompt_never_instructs_the_agent_to_merge() -> None:
    """The one rule with zero tolerance."""
    prompt = orchestrator.build_prompt({"key": "SCRUM-1", "summary": "x", "description": "y"})
    assert "do not merge" in prompt.lower() or "not merge" in prompt.lower()
    assert "gh pr merge" not in prompt
    assert "PR_URL:" in prompt


def test_the_prompt_includes_resume_context_when_given() -> None:
    prompt = orchestrator.build_prompt(
        {"key": "SCRUM-1", "summary": "x", "description": "y"},
        resume_context="finish the auth check you started",
    )
    assert "finish the auth check you started" in prompt


async def test_poll_never_resumes_a_shipped_run() -> None:
    """The end-to-end proof, not just the unit-level lifecycle/db tests. A
    SHIPPED run must not reach process_ticket at all."""
    processed: list[str] = []

    async def fake_get_active_run():
        return DevAgentRun(ticket_key="SCRUM-1", state=lifecycle.SHIPPED, attempt_count=1)

    async def fake_should_attempt(key, max_attempts):
        return False  # SHIPPED must fail this too -- the independent check

    async def fake_process_ticket(ticket, settings=None):
        processed.append(ticket["key"])

    async def fake_preflight(backend_name, settings):
        return "ok"

    async def fake_ensure_repo_cloned(*a, **kw):
        return None

    async def fake_find_sprint_candidates(settings=None):
        return []

    async def fake_get_issue_detail(key, settings=None):
        return {"key": key, "summary": "s"}

    await orchestrator.poll_and_process(
        _settings(),
        preflight=fake_preflight, ensure_repo_cloned=fake_ensure_repo_cloned,
        get_active_run=fake_get_active_run, should_attempt=fake_should_attempt,
        get_issue_detail=fake_get_issue_detail,
        find_sprint_candidates=fake_find_sprint_candidates, process_ticket=fake_process_ticket,
    )
    assert processed == [], "a SHIPPED run must never be resumed"


async def test_should_attempt_is_consulted_before_resuming_an_active_run() -> None:
    """Defence in depth (ADR-020): should_attempt() is an INDEPENDENT check,
    not merely trusted to agree with the exclusion query."""
    calls: list[str] = []

    async def fake_get_active_run():
        return DevAgentRun(ticket_key="SCRUM-1", state=lifecycle.IMPLEMENTING, attempt_count=1)

    async def fake_should_attempt(key, max_attempts):
        calls.append(key)
        return False

    async def fake_process_ticket(ticket, settings=None):
        raise AssertionError("must not run: should_attempt said no")

    await orchestrator.poll_and_process(
        _settings(),
        preflight=lambda b, s: _ok("preflight"),
        ensure_repo_cloned=lambda *a, **kw: _ok(None),
        get_active_run=fake_get_active_run, should_attempt=fake_should_attempt,
        get_issue_detail=lambda key, settings=None: _ok({"key": key}),
        find_sprint_candidates=lambda settings=None: _ok([]),
        process_ticket=fake_process_ticket,
    )
    assert calls == ["SCRUM-1"], "should_attempt must be consulted before resuming"


async def _ok(value):
    return value


async def test_a_pr_found_gates_the_outcome_not_the_success_flag() -> None:
    """v5's real SCRUM-50 failure mode: a run can push a branch, open a PR,
    and still report success=False (e.g. hits the turn limit on a later
    step). Dropping that PR and reverting to TO DO would lose good work."""
    transitions: list[str] = []
    finishes: list[tuple] = []

    async def fake_transition(key, status, settings=None):
        transitions.append(status)
        return True

    async def fake_finish(key, state, pr_url=None, pr_number=None, error=None):
        finishes.append((state, pr_url))

    async def fake_run_claude_code(*a, **kw):
        return ClaudeRunResult(success=False, returncode=1, result_text="hit turn limit")

    async def fake_find_open_pr(*a, **kw):
        return {"number": 7, "html_url": "https://github.com/x/y/pull/7"}

    await orchestrator.process_ticket(
        {"key": "SCRUM-50", "summary": "s"}, _settings(),
        claim_run=lambda *a: _ok(None),
        set_state=lambda *a: _ok(None),
        get_run=lambda key: _ok(DevAgentRun(ticket_key=key, state=lifecycle.IMPLEMENTING, attempt_count=1)),
        finish_run=fake_finish,
        transition_issue=fake_transition,
        add_comment=lambda *a, **kw: _ok(None),
        get_issue_detail=lambda key, settings=None: _ok({"key": key, "summary": "s"}),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=lambda *a, **kw: _ok(None),
        run_claude_code=fake_run_claude_code,
        find_open_pr=fake_find_open_pr,
        get_pr_diff=lambda *a: _ok("diff --git a/x b/x"),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
    )

    assert finishes and finishes[0][0] == lifecycle.SHIPPED, (
        "a PR that exists must ship even though result.success was False"
    )
    assert "In Review" in transitions
    assert "To Do" not in transitions, "good work must not be reverted to TO DO"


async def test_process_ticket_advances_through_every_lifecycle_state_on_success() -> None:
    states: list[str] = []

    async def fake_set_state(key, state):
        states.append(state)

    async def fake_run_claude_code(*a, **kw):
        return ClaudeRunResult(success=True, returncode=0, result_text="PR_URL: https://x/1")

    await orchestrator.process_ticket(
        {"key": "SCRUM-1", "summary": "s"}, _settings(),
        claim_run=lambda *a: _ok(None),
        set_state=fake_set_state,
        get_run=lambda key: _ok(None),
        finish_run=lambda *a, **kw: _ok(None),
        transition_issue=lambda *a, **kw: _ok(True),
        add_comment=lambda *a, **kw: _ok(None),
        get_issue_detail=lambda key, settings=None: _ok({"key": key, "summary": "s"}),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=lambda *a, **kw: _ok(None),
        run_claude_code=fake_run_claude_code,
        find_open_pr=lambda *a, **kw: _ok({"number": 1, "html_url": "https://x/1"}),
        get_pr_diff=lambda *a: _ok("diff"),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
    )

    assert states == [
        lifecycle.PLANNED, lifecycle.IMPLEMENTING, lifecycle.DEBUGGING,
        lifecycle.REVIEWING, lifecycle.SHIPPED,
    ]


async def test_a_missing_pr_marks_the_run_failed_and_records_session_memory() -> None:
    finishes: list[tuple] = []
    transitions: list[str] = []

    async def fake_finish(key, state, pr_url=None, pr_number=None, error=None):
        finishes.append((state, error))

    async def fake_transition(key, status, settings=None):
        transitions.append(status)
        return True

    async def fake_run_claude_code(*a, **kw):
        return ClaudeRunResult(success=False, returncode=1, result_text="tests never passed")

    await orchestrator.process_ticket(
        {"key": "SCRUM-2", "summary": "s"}, _settings(),
        claim_run=lambda *a: _ok(None),
        set_state=lambda *a: _ok(None),
        get_run=lambda key: _ok(None),
        finish_run=fake_finish,
        transition_issue=fake_transition,
        add_comment=lambda *a, **kw: _ok(None),
        get_issue_detail=lambda key, settings=None: _ok({"key": key, "summary": "s"}),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=lambda *a, **kw: _ok(None),
        run_claude_code=fake_run_claude_code,
        find_open_pr=lambda *a, **kw: _ok(None),  # no PR
        get_pr_diff=lambda *a: _ok(""),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
    )

    assert finishes[0][0] == lifecycle.FAILED
    assert "tests never passed" in finishes[0][1]
    assert "To Do" in transitions, "a genuine failure must return the ticket to the backlog"


async def test_the_worktree_is_cleaned_up_even_when_the_run_itself_raises() -> None:
    """The finally block: cleanup must run regardless of outcome.

    create_worktree is INSIDE the try block (claim_run, ahead of it, is not --
    matching v5's structure, since nothing exists to clean up before a
    worktree is ever created). Raising here is the realistic failure this
    guarantee exists for: claude_runner or any step after the worktree exists
    can blow up, and the worktree must not be leaked.
    """
    removed: list[str] = []

    async def fake_remove_worktree(repo_dir, work_dir, branch, ignore_errors=False):
        removed.append(branch)

    async def exploding_run_claude_code(*a, **kw):
        raise RuntimeError("subprocess crashed")

    await orchestrator.process_ticket(
        {"key": "SCRUM-3", "summary": "s"}, _settings(),
        claim_run=lambda *a: _ok(None),
        set_state=lambda *a: _ok(None),
        get_run=lambda key: _ok(None),
        finish_run=lambda *a, **kw: _ok(None),
        transition_issue=lambda *a, **kw: _ok(True),
        add_comment=lambda *a, **kw: _ok(None),
        get_issue_detail=lambda key, settings=None: _ok({"key": key, "summary": "s"}),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=fake_remove_worktree,
        run_claude_code=exploding_run_claude_code,
        find_open_pr=lambda *a, **kw: _ok(None),
        get_pr_diff=lambda *a: _ok(""),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
    )
    assert removed == ["agent/SCRUM-3"], "the worktree must not be leaked when the run crashes"
