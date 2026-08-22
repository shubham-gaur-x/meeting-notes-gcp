"""Phase 11 — the autonomous dev agent (ADR-020).

Runs with no live services except the explicitly-gated live-verification
task, which this file does not contain — that task needs real GitHub/Jira
credentials and is run by hand per the plan, not simulated here.
"""

from __future__ import annotations

import json

import pytest

from meeting_notes.dev_agent import lifecycle
from meeting_notes.dev_agent.models import AgentRunResult, DevAgentRun

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
    with pytest.raises(lifecycle.IllegalTransitionError):
        lifecycle.assert_transition(lifecycle.TRIAGED, lifecycle.SHIPPED)


def test_assert_transition_passes_silently_for_a_legal_edge() -> None:
    lifecycle.assert_transition(lifecycle.TRIAGED, lifecycle.PLANNED)  # must not raise


def test_unknown_states_raise() -> None:
    with pytest.raises(lifecycle.IllegalTransitionError):
        lifecycle.assert_transition("NOT_A_STATE", lifecycle.PLANNED)
    with pytest.raises(lifecycle.IllegalTransitionError):
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
    assert gr.gate_secret_scan(
        ["token = ghp_abcdefghijklmnopqrstuvwxyz1234"]  # pragma: allowlist secret
    ).passed is False


def test_secret_scan_catches_a_private_key_header() -> None:
    assert gr.gate_secret_scan(
        ["-----BEGIN RSA PRIVATE KEY-----"]  # pragma: allowlist secret
    ).passed is False


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
    assert dab.select_backend(_settings(DEV_AGENT_LLM_BACKEND="gemini")) == "gemini"


def test_select_backend_defaults_to_gemini() -> None:
    assert dab.select_backend(_settings()) == "gemini"


def test_select_backend_rejects_an_unknown_value() -> None:
    with pytest.raises(ValueError, match="Invalid"):
        dab.select_backend(_settings(DEV_AGENT_LLM_BACKEND="groq"))


def test_select_backend_rejects_the_retired_claude_backends(tmp_path) -> None:
    """ADR-021 removed local/vertex/claude. They must fail loudly rather than
    silently routing a run at a backend that is no longer wired up."""
    for retired in ("local", "vertex", "claude"):
        with pytest.raises(ValueError, match="Invalid"):
            dab.select_backend(_settings(DEV_AGENT_LLM_BACKEND=retired))


def test_gemini_backend_pins_auth_to_vertex(tmp_path) -> None:
    """The CLI must not be able to reach the Code Assist (oauth-personal)
    path, which is what it picks by default and which is not billed to the
    GCP project."""
    env = dab.resolve_backend_env(
        "gemini",
        _settings(
            GCP_PROJECT_ID="my-proj",
            DEV_AGENT_GEMINI_LOCATION="global",
            DEV_AGENT_GEMINI_CLI_HOME=str(tmp_path / "home"),
        ),
    )
    assert env["GOOGLE_GENAI_USE_VERTEXAI"] == "1"
    assert env["GOOGLE_CLOUD_PROJECT"] == "my-proj"
    assert env["GOOGLE_CLOUD_LOCATION"] == "global"


def test_gemini_backend_empties_the_api_key(tmp_path) -> None:
    """An AI Studio key in the parent environment would redirect billing away
    from the GCP project without any visible error."""
    env = dab.resolve_backend_env(
        "gemini", _settings(DEV_AGENT_GEMINI_CLI_HOME=str(tmp_path / "home"))
    )
    assert env["GEMINI_API_KEY"] == ""


def test_gemini_backend_uses_its_own_cli_home(tmp_path) -> None:
    """Without an owned GEMINI_CLI_HOME the CLI reads the developer's
    ~/.gemini/settings.json, whose selectedType wins over the environment --
    observed live routing a Vertex-configured run to Code Assist instead."""
    home = tmp_path / "gemini-home"
    env = dab.resolve_backend_env("gemini", _settings(DEV_AGENT_GEMINI_CLI_HOME=str(home)))
    assert env["GEMINI_CLI_HOME"] == str(home)
    written = json.loads((home / ".gemini" / "settings.json").read_text())
    assert written["security"]["auth"]["selectedType"] == "vertex-ai"


def test_ensure_cli_home_overwrites_a_stale_auth_selection(tmp_path) -> None:
    home = tmp_path / "gemini-home"
    (home / ".gemini").mkdir(parents=True)
    (home / ".gemini" / "settings.json").write_text(
        json.dumps({"security": {"auth": {"selectedType": "oauth-personal"}}})
    )
    dab.ensure_cli_home(_settings(DEV_AGENT_GEMINI_CLI_HOME=str(home)))
    written = json.loads((home / ".gemini" / "settings.json").read_text())
    assert written["security"]["auth"]["selectedType"] == "vertex-ai"


def test_resolve_backend_env_covers_all_valid_backends(tmp_path) -> None:
    """v5 stated this as a discipline explicitly; assert it directly rather
    than trusting the tests above happen to cover everything."""
    for name in dab.VALID_BACKENDS:
        env = dab.resolve_backend_env(
            name,
            _settings(GCP_PROJECT_ID="p", DEV_AGENT_GEMINI_CLI_HOME=str(tmp_path / name)),
        )
        assert "GEMINI_API_KEY" in env


def test_model_for_run_reads_the_gemini_model_setting() -> None:
    s = _settings(DEV_AGENT_GEMINI_MODEL="gemini-3-pro-preview")
    assert dab.model_for_run("gemini", s) == "gemini-3-pro-preview"


def test_model_for_run_returns_none_when_unset() -> None:
    assert dab.model_for_run("gemini", _settings(DEV_AGENT_GEMINI_MODEL="")) is None


async def test_preflight_gemini_fails_without_a_project_id() -> None:
    with pytest.raises(dab.PreflightError, match="GCP_PROJECT_ID"):
        dab.preflight_gemini(_settings(GCP_PROJECT_ID=""))


async def test_preflight_gemini_fails_without_a_location() -> None:
    """The 3.x models are served only from "global"; an empty location would
    fail at run time with a bare model-not-found."""
    with pytest.raises(dab.PreflightError, match="DEV_AGENT_GEMINI_LOCATION"):
        dab.preflight_gemini(_settings(GCP_PROJECT_ID="p", DEV_AGENT_GEMINI_LOCATION=""))


async def test_preflight_gemini_passes_with_a_project_id() -> None:
    detail = dab.preflight_gemini(_settings(GCP_PROJECT_ID="my-proj"))
    assert "my-proj" in detail


async def test_preflight_dispatches_to_the_right_backend_check() -> None:
    with pytest.raises(dab.PreflightError, match="GCP_PROJECT_ID"):
        await dab.preflight("gemini", _settings(GCP_PROJECT_ID=""))


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


# ─── git_ops.py, github_client.py, gemini_runner.py, session_memory.py (Task 7)

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


# github_client is exercised via orchestrator tests (Task 8), where it is
# naturally injected as a dependency of process_ticket.


# ─── gemini_runner.py (ADR-021): parsing the CLI's JSON result ─────────────

from meeting_notes.dev_agent import gemini_runner  # noqa: E402


def test_turns_are_summed_across_models() -> None:
    stats = {
        "models": {
            "gemini-3-pro-preview": {"api": {"totalRequests": 3}},
            "gemini-3.7-flash": {"api": {"totalRequests": 2}},
        }
    }
    assert gemini_runner._turns_from_stats(stats) == 5


def test_turns_tolerate_a_missing_or_malformed_stats_block() -> None:
    """The CLI's stats shape is not a contract we control."""
    assert gemini_runner._turns_from_stats(None) is None
    assert gemini_runner._turns_from_stats({}) is None
    assert gemini_runner._turns_from_stats({"models": "nope"}) is None
    assert gemini_runner._turns_from_stats({"models": {"m": {}}}) is None


def test_parse_result_rejects_non_object_json() -> None:
    """A bare JSON array or string is not a result envelope."""
    assert gemini_runner._parse_result("[1, 2]") is None
    assert gemini_runner._parse_result("not json at all") is None
    assert gemini_runner._parse_result('{"response": "hi"}') == {"response": "hi"}


class _FakeProc:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self._out = stdout.encode()
        self._err = stderr.encode()
        self.returncode = returncode

    async def communicate(self):
        return self._out, self._err

    def kill(self) -> None: ...

    async def wait(self) -> None: ...


def _fake_spawn(monkeypatch, proc):
    async def spawn(*a, **kw):
        return proc

    monkeypatch.setattr(gemini_runner.asyncio, "create_subprocess_exec", spawn)


def _runner_settings(tmp_path):
    return _settings(GCP_PROJECT_ID="p", DEV_AGENT_GEMINI_CLI_HOME=str(tmp_path / "home"))


async def test_run_agent_reports_failure_when_the_cli_reports_an_error(
    monkeypatch, tmp_path
) -> None:
    """Observed live: the CLI edited the file correctly and STILL emitted
    {"error": {"type": "INVALID_STREAM"}} on exit. The runner records what the
    CLI claimed -- it is the ORCHESTRATOR that must gate the outcome on
    whether a PR exists rather than on this flag (ADR-020)."""
    payload = json.dumps(
        {
            "response": "",
            "error": {"type": "INVALID_STREAM", "message": "empty response"},
            "stats": {"models": {"m": {"api": {"totalRequests": 4}}}},
        }
    )
    _fake_spawn(monkeypatch, _FakeProc(payload, returncode=0))
    result = await gemini_runner.run_agent(
        str(tmp_path), "do the thing", 60, settings=_runner_settings(tmp_path)
    )
    assert result.success is False
    assert "empty response" in result.result_text
    assert result.num_turns == 4


async def test_run_agent_succeeds_on_a_clean_result(monkeypatch, tmp_path) -> None:
    payload = json.dumps(
        {"response": "PR_URL: https://x/1", "stats": {"models": {"m": {"api": {"totalRequests": 7}}}}}
    )
    _fake_spawn(monkeypatch, _FakeProc(payload, returncode=0))
    result = await gemini_runner.run_agent(
        str(tmp_path), "do the thing", 60, settings=_runner_settings(tmp_path)
    )
    assert result.success is True
    assert result.result_text == "PR_URL: https://x/1"
    assert result.num_turns == 7


async def test_run_agent_prefers_the_json_error_over_stderr_on_nonzero_exit(
    monkeypatch, tmp_path
) -> None:
    """stderr is frequently just terminal warnings; the useful message is in
    the JSON on stdout even when the process exits nonzero."""
    payload = json.dumps({"error": {"type": "AUTH", "message": "the real reason"}})
    _fake_spawn(
        monkeypatch, _FakeProc(payload, stderr="Warning: 256-color not detected", returncode=1)
    )
    result = await gemini_runner.run_agent(
        str(tmp_path), "x", 60, settings=_runner_settings(tmp_path)
    )
    assert result.success is False
    assert result.returncode == 1
    assert "the real reason" in result.result_text


async def test_run_agent_survives_unparseable_output(monkeypatch, tmp_path) -> None:
    """A zero exit with non-JSON stdout must not crash the run."""
    _fake_spawn(monkeypatch, _FakeProc("total gibberish", returncode=0))
    result = await gemini_runner.run_agent(
        str(tmp_path), "x", 60, settings=_runner_settings(tmp_path)
    )
    assert result.success is True
    assert "gibberish" in result.result_text


async def test_run_oneshot_extracts_the_response_field(monkeypatch, tmp_path) -> None:
    """The CLI's field is `response`; Claude Code's was `result`. A silent
    mismatch here would return None and make self-verify abstain forever."""
    _fake_spawn(monkeypatch, _FakeProc(json.dumps({"response": "0.9"}), returncode=0))
    got = await gemini_runner.run_oneshot("score it", 30, settings=_runner_settings(tmp_path))
    assert got == "0.9"


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

    async def fake_find_sprint_candidates(settings=None):
        return []

    async def fake_get_issue_detail(key, settings=None):
        return {"key": key, "summary": "s"}

    await orchestrator.poll_and_process(
        _settings(),
        preflight=fake_preflight,
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
        get_active_run=fake_get_active_run, should_attempt=fake_should_attempt,
        get_issue_detail=lambda key, settings=None: _ok({"key": key}),
        find_sprint_candidates=lambda settings=None: _ok([]),
        process_ticket=fake_process_ticket,
    )
    assert calls == ["SCRUM-1"], "should_attempt must be consulted before resuming"


async def _ok(value):
    return value


async def _gates_pass(*a, **kw):
    """Gates green. Tests that are not about the guardrails inject this so the
    real gate runner does not try to run pytest in a stub worktree."""
    return [gr.GateResult(name="all", passed=True, evidence="clean")]


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

    async def fake_run_agent(*a, **kw):
        return AgentRunResult(success=False, returncode=1, result_text="hit turn limit")

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
        ensure_repo_cloned=lambda *a, **kw: _ok(None),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=lambda *a, **kw: _ok(None),
        run_agent=fake_run_agent,
        find_open_pr=fake_find_open_pr,
        get_pr_diff=lambda *a: _ok("diff --git a/x b/x"),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
        run_gates=_gates_pass,
        review_pr=lambda *a, **kw: _ok(None),
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

    async def fake_run_agent(*a, **kw):
        return AgentRunResult(success=True, returncode=0, result_text="PR_URL: https://x/1")

    await orchestrator.process_ticket(
        {"key": "SCRUM-1", "summary": "s"}, _settings(),
        claim_run=lambda *a: _ok(None),
        set_state=fake_set_state,
        get_run=lambda key: _ok(None),
        finish_run=lambda *a, **kw: _ok(None),
        transition_issue=lambda *a, **kw: _ok(True),
        add_comment=lambda *a, **kw: _ok(None),
        get_issue_detail=lambda key, settings=None: _ok({"key": key, "summary": "s"}),
        ensure_repo_cloned=lambda *a, **kw: _ok(None),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=lambda *a, **kw: _ok(None),
        run_agent=fake_run_agent,
        find_open_pr=lambda *a, **kw: _ok({"number": 1, "html_url": "https://x/1"}),
        get_pr_diff=lambda *a: _ok("diff"),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
        run_gates=_gates_pass,
        review_pr=lambda *a, **kw: _ok(None),
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

    async def fake_run_agent(*a, **kw):
        return AgentRunResult(success=False, returncode=1, result_text="tests never passed")

    await orchestrator.process_ticket(
        {"key": "SCRUM-2", "summary": "s"}, _settings(),
        claim_run=lambda *a: _ok(None),
        set_state=lambda *a: _ok(None),
        get_run=lambda key: _ok(None),
        finish_run=fake_finish,
        transition_issue=fake_transition,
        add_comment=lambda *a, **kw: _ok(None),
        get_issue_detail=lambda key, settings=None: _ok({"key": key, "summary": "s"}),
        ensure_repo_cloned=lambda *a, **kw: _ok(None),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=lambda *a, **kw: _ok(None),
        run_agent=fake_run_agent,
        find_open_pr=lambda *a, **kw: _ok(None),  # no PR
        get_pr_diff=lambda *a: _ok(""),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
        run_gates=_gates_pass,
        review_pr=lambda *a, **kw: _ok(None),
    )

    assert finishes[0][0] == lifecycle.FAILED
    assert "tests never passed" in finishes[0][1]
    assert "To Do" in transitions, "a genuine failure must return the ticket to the backlog"


async def test_the_worktree_is_cleaned_up_even_when_the_run_itself_raises() -> None:
    """The finally block: cleanup must run regardless of outcome.

    create_worktree is INSIDE the try block (claim_run, ahead of it, is not --
    matching v5's structure, since nothing exists to clean up before a
    worktree is ever created). Raising here is the realistic failure this
    guarantee exists for: the coding runner or any step after the worktree exists
    can blow up, and the worktree must not be leaked.
    """
    removed: list[str] = []

    async def fake_remove_worktree(repo_dir, work_dir, branch, ignore_errors=False):
        removed.append(branch)

    async def exploding_run_agent(*a, **kw):
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
        ensure_repo_cloned=lambda *a, **kw: _ok(None),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=fake_remove_worktree,
        run_agent=exploding_run_agent,
        find_open_pr=lambda *a, **kw: _ok(None),
        get_pr_diff=lambda *a: _ok(""),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
        run_gates=_gates_pass,
        review_pr=lambda *a, **kw: _ok(None),
    )
    assert removed == ["agent/SCRUM-3"], "the worktree must not be leaked when the run crashes"


# ─── guardrails wired into the run (the ADR-020 safety net) ────────────────────


_DIFF = """diff --git a/meeting_notes/thing.py b/meeting_notes/thing.py
index 111..222 100644
--- a/meeting_notes/thing.py
+++ b/meeting_notes/thing.py
@@ -1,2 +1,4 @@
 existing line
+def added():
+    return 1
-removed line
diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1 +1,2 @@
+leftpad
"""


def test_parse_diff_extracts_files_added_lines_and_dependency_lines() -> None:
    facts = gr.parse_diff(_DIFF)
    assert facts.changed_files == ["meeting_notes/thing.py", "requirements.txt"]
    assert "def added():" in "\n".join(facts.added_lines)
    assert "+++ b/" not in "".join(facts.added_lines), "the ++ header is not an added line"
    assert facts.changed_lines >= 3, "additions and deletions both count toward the budget"
    assert any("leftpad" in ln for ln in facts.added_dependency_lines)


def test_parse_diff_is_the_one_definition_of_changed_files() -> None:
    """session_memory.files_from_diff and the gates must agree on what changed;
    two parsers would let the budget gate and the memory record disagree."""
    from meeting_notes.dev_agent import session_memory as sm

    assert sm.files_from_diff(_DIFF) == gr.parse_diff(_DIFF).changed_files


def test_evaluate_gates_returns_every_gate() -> None:
    results = gr.evaluate_gates(
        diff=_DIFF, ticket_description="", file_contents={},
        tests=(0, "ok"), lint=(0, ""), typecheck=(0, ""),
    )
    assert {r.name for r in results} == {
        "tests_green", "lint_type_clean", "diff_budget",
        "protected_paths", "no_new_deps", "secret_scan", "module_boundaries",
    }


def test_evaluate_gates_fails_when_the_test_command_failed() -> None:
    results = gr.evaluate_gates(
        diff="", ticket_description="", file_contents={},
        tests=(1, "2 failed"), lint=(0, ""), typecheck=(0, ""),
    )
    assert gr.all_passed(results) is False
    assert "tests_green" in {g.name for g in gr.failed_gates(results)}


async def _process(ticket, *, diff, run_gates, **over):
    """process_ticket with every dependency stubbed, overridable per test."""
    calls = {"finishes": [], "states": [], "comments": [], "transitions": []}

    async def fake_finish(key, state, pr_url=None, pr_number=None, error=None):
        calls["finishes"].append((state, pr_url, error))

    async def fake_set_state(key, state):
        calls["states"].append(state)

    async def fake_comment(key, text, settings=None):
        calls["comments"].append(text)

    async def fake_transition(key, status, settings=None):
        calls["transitions"].append(status)
        return True

    kwargs = dict(
        claim_run=lambda *a: _ok(None),
        set_state=fake_set_state,
        get_run=lambda key: _ok(DevAgentRun(ticket_key=key, state=lifecycle.REVIEWING, attempt_count=1)),
        finish_run=fake_finish,
        transition_issue=fake_transition,
        add_comment=fake_comment,
        get_issue_detail=lambda key, settings=None: _ok({"key": key, "summary": "s"}),
        ensure_repo_cloned=lambda *a, **kw: _ok(None),
        create_worktree=lambda *a: _ok(None),
        remove_worktree=lambda *a, **kw: _ok(None),
        run_agent=lambda *a, **kw: _ok(AgentRunResult(success=True, returncode=0, result_text="done")),
        find_open_pr=lambda *a, **kw: _ok({"number": 9, "html_url": "https://gh/x/pull/9"}),
        get_pr_diff=lambda *a: _ok(diff),
        verify_pr=lambda *a, **kw: _ok(self_verify.VerifyVerdict()),
        write_run_provenance=lambda **kw: _ok("run-id"),
        load_resume_context=lambda key: _ok(None),
        record_session_memory=lambda *a, **kw: _ok({}),
        run_gates=run_gates,
        review_pr=lambda *a, **kw: _ok(None),
    )
    kwargs.update(over)
    await orchestrator.process_ticket(ticket, _settings(), **kwargs)
    return calls


async def test_a_clean_gate_run_still_ships() -> None:
    async def gates_pass(*a, **kw):
        return [gr.GateResult(name="secret_scan", passed=True, evidence="clean")]

    calls = await _process({"key": "SCRUM-1", "summary": "s"}, diff=_DIFF, run_gates=gates_pass)
    assert calls["finishes"][0][0] == lifecycle.SHIPPED
    assert lifecycle.NEEDS_HUMAN not in calls["states"]


async def test_a_failing_gate_blocks_shipping_and_escalates_to_a_human() -> None:
    """The whole point of the safety net: a PR that trips a deterministic gate
    must never be recorded as SHIPPED."""
    async def gates_fail(*a, **kw):
        return [
            gr.GateResult(name="secret_scan", passed=False, evidence="1 possible secret(s)"),
            gr.GateResult(name="tests_green", passed=True, evidence="passed"),
        ]

    calls = await _process({"key": "SCRUM-2", "summary": "s"}, diff=_DIFF, run_gates=gates_fail)

    assert calls["finishes"], "the run must be finished, not left active"
    state, pr_url, _ = calls["finishes"][0]
    assert state == lifecycle.NEEDS_HUMAN, f"expected NEEDS_HUMAN, got {state}"
    assert lifecycle.SHIPPED not in calls["states"], "a failed gate must not ship"
    assert pr_url == "https://gh/x/pull/9", "the PR must be recorded, not discarded"


async def test_a_failing_gate_names_the_gate_in_the_jira_comment() -> None:
    async def gates_fail(*a, **kw):
        return [gr.GateResult(name="protected_paths", passed=False, evidence="touched: .env")]

    calls = await _process({"key": "SCRUM-4", "summary": "s"}, diff=_DIFF, run_gates=gates_fail)
    blob = "\n".join(calls["comments"])
    assert "protected_paths" in blob, "a human needs to know WHICH gate failed"
    assert ".env" in blob, "and the evidence behind it"


async def test_a_failing_gate_does_not_revert_the_ticket_to_to_do() -> None:
    """The PR is real work. It goes to review for a human, not back to the
    backlog -- the same reasoning the PR-found path already applies."""
    async def gates_fail(*a, **kw):
        return [gr.GateResult(name="secret_scan", passed=False, evidence="x")]

    calls = await _process({"key": "SCRUM-5", "summary": "s"}, diff=_DIFF, run_gates=gates_fail)
    assert "To Do" not in calls["transitions"]
    assert "In Review" in calls["transitions"]


async def test_a_planted_secret_in_the_diff_blocks_the_ship_through_the_real_gates() -> None:
    """End-to-end through the REAL gate evaluation -- only the shell commands
    are stubbed. Guards against the gates being wired up but fed nothing."""
    leaked = (
        "diff --git a/app/cfg.py b/app/cfg.py\n"
        "--- a/app/cfg.py\n+++ b/app/cfg.py\n"
        '@@ -0,0 +1 @@\n+AWS_KEY = "AKIA' + "A" * 16 + '"\n'
    )

    async def real_gates(work_dir, diff, ticket_description, settings=None):
        return gr.evaluate_gates(
            diff=diff, ticket_description=ticket_description, file_contents={},
            tests=(0, "ok"), lint=(0, ""), typecheck=(0, ""),
        )

    calls = await _process({"key": "SCRUM-6", "summary": "s"}, diff=leaked, run_gates=real_gates)
    assert calls["finishes"][0][0] == lifecycle.NEEDS_HUMAN
    assert "secret_scan" in "\n".join(calls["comments"])


async def test_gate_failure_is_not_fatal_to_the_run_bookkeeping() -> None:
    """If the gate step itself raises, the run must still be finished rather
    than left active forever -- an unfinished run is what the poller resumes."""
    async def gates_explode(*a, **kw):
        raise RuntimeError("ruff not installed in the worktree")

    calls = await _process({"key": "SCRUM-7", "summary": "s"}, diff=_DIFF, run_gates=gates_explode)
    assert calls["finishes"], "a crashing gate step must not leave the run active"
    assert calls["finishes"][0][0] in (lifecycle.NEEDS_HUMAN, lifecycle.FAILED)


async def test_gate_commands_run_under_the_jobs_own_interpreter() -> None:
    """`ruff`/`mypy`/`pytest` are not on PATH in a bare worktree -- they live
    in the venv or image that is running the job. Resolving a leading
    `python` to sys.executable is what stops every gate returning 127 and
    escalating every PR for the wrong reason. Found live: `ruff check .`
    exited 127 with "No such file or directory: 'ruff'".
    """
    import sys

    from meeting_notes.dev_agent import gate_runner as grn

    code, out = await grn.run_command("python -c \"import sys; print(sys.executable)\"", ".")
    assert code == 0, f"the interpreter must resolve, got {code}: {out}"
    assert out.strip() == sys.executable, (
        f"expected the running interpreter {sys.executable}, got {out.strip()}"
    )


async def test_gate_command_defaults_go_through_the_interpreter() -> None:
    """If a default shells out to a bare `ruff`, it breaks the moment the
    worktree has no venv on PATH -- which is the normal case."""
    s = _settings()
    for cmd in (s.dev_agent_test_command, s.dev_agent_lint_command,
                s.dev_agent_typecheck_command):
        assert cmd.split()[0] in ("python", "python3"), (
            f"{cmd!r} must run through the interpreter, not a bare console script"
        )


# ─── the independent LLM reviewer (ADR-020 layer 2) ───────────────────────────


def _verdict_json(verdict="approve", findings=None):
    return json.dumps({"verdict": verdict, "findings": findings or []})


async def test_the_reviewer_parses_an_approval() -> None:
    from meeting_notes.dev_agent import reviewer

    async def fake_oneshot(prompt, **kw):
        return _verdict_json("approve")

    v = await reviewer.review_pr(
        {"key": "SCRUM-1", "summary": "s"}, "diff", [], run_oneshot=fake_oneshot
    )
    assert v.checked is True
    assert v.verdict == "approve"
    assert v.blocking is False


async def test_a_high_severity_finding_blocks() -> None:
    """The reviewer is the second layer of the safety net, not a second
    advisory comment -- ADR-022 rejected adding another of those."""
    from meeting_notes.dev_agent import reviewer

    async def fake_oneshot(prompt, **kw):
        return _verdict_json("request_changes", [
            {"severity": "high", "file": "a.py", "issue": "drops the transaction"},
        ])

    v = await reviewer.review_pr({"key": "K", "summary": "s"}, "d", [], run_oneshot=fake_oneshot)
    assert v.blocking is True
    assert "drops the transaction" in v.summary()


async def test_only_low_severity_findings_do_not_block() -> None:
    """A nit must not hold up a PR a human is going to read anyway."""
    from meeting_notes.dev_agent import reviewer

    async def fake_oneshot(prompt, **kw):
        return _verdict_json("request_changes", [
            {"severity": "low", "file": "a.py", "issue": "naming nit"},
        ])

    v = await reviewer.review_pr({"key": "K", "summary": "s"}, "d", [], run_oneshot=fake_oneshot)
    assert v.blocking is False, "a low-severity nit must not block"
    assert v.checked is True


async def test_an_unreachable_reviewer_does_not_block() -> None:
    """Asymmetry with the deterministic gates, and deliberate: an unrunnable
    GATE is a failure because its absence hides a fact it could have checked
    cheaply. An unreachable LLM is an availability problem, the seven gates
    have already run, and a human still reviews before any merge -- so an
    outage must not halt the pipeline.
    """
    from meeting_notes.dev_agent import reviewer

    async def dead_oneshot(prompt, **kw):
        raise RuntimeError("model unreachable")

    v = await reviewer.review_pr({"key": "K", "summary": "s"}, "d", [], run_oneshot=dead_oneshot)
    assert v.checked is False
    assert v.blocking is False


async def test_unparseable_reviewer_output_does_not_block() -> None:
    from meeting_notes.dev_agent import reviewer

    async def junk(prompt, **kw):
        return "I think this looks fine to me!"

    v = await reviewer.review_pr({"key": "K", "summary": "s"}, "d", [], run_oneshot=junk)
    assert v.checked is False
    assert v.blocking is False


async def test_the_reviewer_is_shown_the_gate_evidence() -> None:
    """ADR-020: the reviewer gets ticket, diff AND gate evidence. Without the
    gate results it re-derives what the deterministic layer already knows."""
    from meeting_notes.dev_agent import reviewer

    seen = {}

    async def capture(prompt, **kw):
        seen["prompt"] = prompt
        return _verdict_json("approve")

    await reviewer.review_pr(
        {"key": "K", "summary": "s"}, "the diff",
        [gr.GateResult(name="secret_scan", passed=True, evidence="clean")],
        run_oneshot=capture,
    )
    assert "secret_scan" in seen["prompt"]
    assert "the diff" in seen["prompt"]


async def test_a_blocking_review_escalates_the_run_to_a_human() -> None:
    """End to end through process_ticket: gates green, reviewer says no."""
    from meeting_notes.dev_agent import reviewer as rv

    async def blocking_review(*a, **kw):
        return rv.ReviewOutcome(
            checked=True, verdict="request_changes",
            findings=[rv.ReviewFinding(severity="high", file="x.py", issue="unsafe")],
        )

    calls = await _process(
        {"key": "SCRUM-8", "summary": "s"}, diff=_DIFF,
        run_gates=_gates_pass, review_pr=blocking_review,
    )
    assert calls["finishes"][0][0] == lifecycle.NEEDS_HUMAN
    assert lifecycle.SHIPPED not in calls["states"]
    assert "unsafe" in "\n".join(calls["comments"])


async def test_an_approving_review_ships() -> None:
    from meeting_notes.dev_agent import reviewer as rv

    async def approving(*a, **kw):
        return rv.ReviewOutcome(checked=True, verdict="approve")

    calls = await _process(
        {"key": "SCRUM-9", "summary": "s"}, diff=_DIFF,
        run_gates=_gates_pass, review_pr=approving,
    )
    assert calls["finishes"][0][0] == lifecycle.SHIPPED


def test_the_cli_home_settings_land_where_the_cli_actually_reads_them(tmp_path) -> None:
    """The CLI reads `<GEMINI_CLI_HOME>/.gemini/settings.json`, not
    `<GEMINI_CLI_HOME>/settings.json`.

    Found live: writing it at the root left the agent unauthenticated and
    `gemini` exited 41 with "Please set an Auth method in your
    /tmp/dev-agent/gemini-home/.gemini/settings.json". Every reviewer and
    self-verify call silently returned None, so both LLM layers of the safety
    net were dead while looking configured.
    """
    import json as _json

    home = tmp_path / "cli-home"
    dab.ensure_cli_home(_settings(DEV_AGENT_GEMINI_CLI_HOME=str(home)))

    target = home / ".gemini" / "settings.json"
    assert target.exists(), f"settings.json must be at {target}, the path the CLI reads"
    assert (
        _json.loads(target.read_text())["security"]["auth"]["selectedType"] == "vertex-ai"
    )


_FENCED = '```json\n{"verdict": "approve", "findings": []}\n```'


async def test_the_reviewer_survives_markdown_fences() -> None:
    """CLAUDE.md: models wrap JSON in ```json fences despite being told not to,
    and the defence must be kept. Confirmed live -- the real CLI returned
    exactly `'```json\\n{...}\\n```'`, so a bare json.loads left every real
    review unparsed and the layer silently dead."""
    from meeting_notes.dev_agent import reviewer

    async def fenced(prompt, **kw):
        return _FENCED

    v = await reviewer.review_pr({"key": "K", "summary": "s"}, "d", [], run_oneshot=fenced)
    assert v.checked is True, "a fenced reply must still parse"
    assert v.verdict == "approve"


async def test_self_verify_survives_markdown_fences() -> None:
    """Same defect, same cause: self_verify has been in the run path since
    Task 5 doing a bare json.loads, so every live verdict was `checked=False`."""
    async def fenced(prompt, **kw):
        return '```json\n{"addresses": true, "confidence": 0.9, "reason": "ok"}\n```'

    v = await self_verify.verify_pr({"key": "K"}, "d", run_oneshot=fenced)
    assert v.checked is True, "a fenced reply must still parse"
    assert v.passed is True


# ─── the repo comes from the ticket, not from one global setting ──────────────


def test_repo_is_read_from_the_ticket_description() -> None:
    """One agent serves many repos, so the target cannot be a single global
    setting. The ticket says where its work belongs."""
    from meeting_notes.dev_agent.orchestrator import repo_for_ticket

    s = _settings(GITHUB_OWNER="fallback", GITHUB_REPO="fallback-repo")
    for description in (
        "Fix the retry loop.\nrepo: acme/widgets",
        "Fix the retry loop. Repo: acme/widgets",
        "See https://github.com/acme/widgets for context.",
        "repository: acme/widgets",
    ):
        assert repo_for_ticket({"description": description}, s) == ("acme", "widgets"), (
            f"did not parse a repo from: {description!r}"
        )


def test_repo_falls_back_to_settings_when_the_ticket_says_nothing() -> None:
    from meeting_notes.dev_agent.orchestrator import repo_for_ticket

    s = _settings(GITHUB_OWNER="fallback", GITHUB_REPO="fallback-repo")
    assert repo_for_ticket({"description": "no repo here"}, s) == ("fallback", "fallback-repo")


def test_a_github_url_with_extra_path_still_parses() -> None:
    """`.git`, a trailing slash, or a deep link must not become part of the name."""
    from meeting_notes.dev_agent.orchestrator import repo_for_ticket

    s = _settings(GITHUB_OWNER="f", GITHUB_REPO="f")
    for url in (
        "https://github.com/acme/widgets.git",
        "https://github.com/acme/widgets/",
        "https://github.com/acme/widgets/issues/12",
    ):
        assert repo_for_ticket({"description": url}, s) == ("acme", "widgets"), url


def test_the_prompt_targets_the_ticket_repo() -> None:
    """The agent opens the PR itself via `gh`, so the prompt has to name the
    right repo or the PR lands in whatever the worktree's origin happens to be."""
    from meeting_notes.dev_agent.orchestrator import build_prompt

    prompt = build_prompt(
        {"key": "K-1", "summary": "s", "description": "repo: acme/widgets"},
        repo=("acme", "widgets"),
    )
    assert "acme/widgets" in prompt


# ─── engineering tickets have to be findable by the agent ─────────────────────


async def test_an_engineering_task_is_labelled_for_the_agent() -> None:
    """find_sprint_candidates selects on the `dev-agent` label, and create_issue
    labelled only NON-engineering items -- so an engineering ticket was created
    unlabelled and the agent could never pick it up. The two halves disagreed
    about how a coding task is marked."""
    from meeting_notes import jira_client

    captured: dict = {}

    async def transport(method, url, headers, params, body):
        captured.update(body or {})
        return 201, {"key": "MNV-1"}

    await jira_client.create_issue(
        summary="Add a retry", description="repo: acme/widgets", priority="medium",
        sprint_id=None, is_engineering_task=True,
        settings=_settings(JIRA_DOMAIN="x.atlassian.net"), transport=transport,
    )
    assert "dev-agent" in captured["fields"].get("labels", []), (
        "an engineering task must carry the label the agent selects on"
    )


async def test_the_clone_and_the_pr_lookup_use_the_ticket_repo() -> None:
    """Cloning once per poll cannot work when the repo comes from the ticket:
    the poll runs before any ticket is chosen. The clone moves inside
    process_ticket, into a directory keyed by the repo so two repos do not
    fight over one checkout."""
    cloned: list[tuple] = []
    pr_lookups: list[tuple] = []

    async def fake_clone(repo_dir, owner, repo, token):
        cloned.append((repo_dir, owner, repo))

    async def fake_find_pr(owner, repo, branch, token, **kw):
        pr_lookups.append((owner, repo))
        return {"number": 5, "html_url": f"https://github.com/{owner}/{repo}/pull/5"}

    calls = await _process(
        {"key": "K-9", "summary": "s", "description": "repo: acme/widgets"},
        diff=_DIFF, run_gates=_gates_pass,
        ensure_repo_cloned=fake_clone, find_open_pr=fake_find_pr,
        get_issue_detail=lambda key, settings=None: _ok(
            {"key": key, "summary": "s", "description": "repo: acme/widgets"}),
    )

    assert cloned, "the ticket's repo was never cloned"
    assert cloned[0][1:] == ("acme", "widgets"), f"cloned the wrong repo: {cloned}"
    assert "acme" in cloned[0][0] and "widgets" in cloned[0][0], (
        f"checkout dir must be keyed by repo, got {cloned[0][0]!r}"
    )
    assert pr_lookups and pr_lookups[0] == ("acme", "widgets")
    assert calls["finishes"][0][0] == lifecycle.SHIPPED
