# Phase 11 Autonomous Dev Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port v5's autonomous Jira-ticket implementer, fixing the confirmed live `SHIPPED`
resume-loop bug and adapting three structural pieces (scheduling, SQL ownership, coding-model
routing) to rules the rest of v6 already holds to. Full reasoning: ADR-020.

**Architecture:** `meeting_notes/dev_agent/` is a new subpackage. It reuses `meeting_notes/db.py`
for all Postgres access (no second SQL module), reuses `meeting_notes/graph_client.py`'s
provenance writers, and owns its own coding-model routing (`backend.py`) deliberately separate
from `llm_client.py`. Scheduling is `jobs/dev_agent_poll.py` on Cloud Scheduler; manual
trigger/status are routes on the existing `api/` service.

**Tech Stack:** Python 3.11+ · `asyncio.subprocess` (spawns the `claude` CLI) · `httpx` ·
`pytest`

## Global Constraints

From `CLAUDE.md` and ADR-020.

- **The terminal lifecycle set has exactly one definition.** `SHIPPED` is terminal. Nothing
  spells "terminal" a second time.
- **`should_attempt()` is consulted before resuming any active run**, independent of the
  terminal-state exclusion — the second half of the ADR-020 fix.
- **DO NOT put SQL outside `meeting_notes/db.py`.** `dev_agent_runs` lives there.
- **DO NOT instantiate the coding-model client through `llm_client.py`.** `dev_agent/backend.py`
  owns it — a subprocess with tool access is not a `chat_json`/`embed` call.
- **DO NOT run an in-process scheduler.** `jobs/dev_agent_poll.py`, triggered by Cloud
  Scheduler.
- **The agent never merges its own PR.** `CLOSED` is written only by `/webhook/github`'s
  `pull_request.merged` handler — an actual human merge.
- **Every guardrail gate is a pure function** taking evidence, not touching the filesystem or
  network itself, so each is unit-testable with a planted violation.
- Type hints on all signatures; `@with_retry` on external HTTP calls; tests run with no live
  services except the explicitly-gated live-verification task.
- One test file for the phase: `tests/test_phase11_dev_agent.py`.

---

## The bug, precisely, and its fix

Confirmed by reading v5's code, not inferred (ADR-020):

```python
# lifecycle.py (v5) — SHIPPED is missing here
TERMINAL_STATES: Set[str] = {CLOSED, FAILED, NEEDS_HUMAN}

# db.py (v5) — the SAME three states, spelled a second time
"... WHERE state NOT IN ('CLOSED', 'FAILED', 'NEEDS_HUMAN') ..."

# orchestrator.py (v5) — resumes on that query alone, should_attempt() not consulted
active = await db.get_active_run()
if active is not None:
    await process_ticket(active_detail)   # <- no should_attempt() check here
```

A `SHIPPED` run's `state` column reads `'SHIPPED'`, which is *not* excluded by either the
Python set or the SQL literal, so every poll treats a successfully-shipped ticket as a crashed
run to resume. `db.start_run()`'s `ON CONFLICT ... attempt_count = attempt_count + 1` then
increments without bound. 61 `AgentRun` nodes for one ticket in the live graph.

**The fix has two independent parts, both required:**
1. `SHIPPED` joins `TERMINAL_STATES`, and `get_active_run()`'s SQL is built *from*
   `TERMINAL_STATES` rather than a second literal — one definition, not a corrected copy.
2. `poll_and_process()` calls `should_attempt()` on whatever `get_active_run()` returns before
   resuming it — so a future drift in the terminal set is caught by an independent check,
   not just fixed once.

---

## File Structure

| File | Responsibility |
|---|---|
| `meeting_notes/db.py` | Modify: add `dev_agent_runs` schema + queries |
| `meeting_notes/dev_agent/__init__.py` | Package docstring: what each module owns |
| `meeting_notes/dev_agent/lifecycle.py` | State machine, deterministic IDs, `SHIPPED` fix |
| `meeting_notes/dev_agent/models.py` | `DevAgentRun` (one `state` field, no parallel `status`), `JiraTicket`, `ClaudeRunResult` |
| `meeting_notes/dev_agent/guardrails.py` | 7 deterministic gates + LLM reviewer types |
| `meeting_notes/dev_agent/self_verify.py` | Diff-vs-ticket scoring |
| `meeting_notes/dev_agent/backend.py` | Coding-model routing: local / vertex / claude |
| `meeting_notes/dev_agent/git_ops.py` | Worktree per ticket |
| `meeting_notes/dev_agent/github_client.py` | Read-only: find PR, get diff |
| `meeting_notes/dev_agent/claude_runner.py` | Spawns headless `claude` |
| `meeting_notes/dev_agent/session_memory.py` | Resumable per-ticket memory |
| `meeting_notes/dev_agent/orchestrator.py` | `triage`, `process_ticket`, `poll_and_process` |
| `jobs/dev_agent_poll.py` | Thin Cloud Run Job entrypoint |
| `api/routers/dev_agent.py` | Manual trigger, preflight, run listing |
| `tests/test_phase11_dev_agent.py` | One test file for the phase |

---

### Task 1: `meeting_notes/db.py` — `dev_agent_runs`

**Files:** Modify `meeting_notes/db.py`

One `state` column (the lifecycle state), not v5's parallel `state` + `status` pair — two
fields tracking overlapping "is this done" facts is exactly the kind of drift that produced
the bug this phase exists to fix, so this is a deliberate simplification, not a mechanical
port.

- [ ] **Step 1: Write the failing tests** — schema is idempotent (same pattern as
  `test_schema_is_idempotent` in Phase 3); `claim_dev_agent_run` upserts and increments
  `attempt_count`; `get_active_dev_agent_run` excludes every state in a parameterised
  terminal set, not a hardcoded one.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 2: `lifecycle.py` — the fix, as a regression test first

**Files:** Create `meeting_notes/dev_agent/lifecycle.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_shipped_is_terminal() -> None:
    """The bug, precisely. v5 confirmed 61 AgentRun nodes for one ticket because
    this was false."""
    assert lifecycle.is_terminal(lifecycle.SHIPPED) is True


def test_every_terminal_state_is_excluded_from_the_active_query() -> None:
    """get_active_dev_agent_run's SQL must be BUILT FROM TERMINAL_STATES, not a
    second hardcoded list -- the drift between two spellings of the same fact
    is the root cause, not a coincidence."""
    from meeting_notes.db import ACTIVE_RUN_EXCLUDED_STATES

    assert ACTIVE_RUN_EXCLUDED_STATES == lifecycle.TERMINAL_STATES


def test_shipped_only_transitions_to_closed() -> None:
    assert lifecycle.can_transition(lifecycle.SHIPPED, lifecycle.CLOSED)
    assert not lifecycle.can_transition(lifecycle.SHIPPED, lifecycle.IMPLEMENTING)


def test_illegal_transitions_raise() -> None:
    with pytest.raises(lifecycle.IllegalTransition):
        lifecycle.assert_transition(lifecycle.TRIAGED, lifecycle.SHIPPED)


def test_debugging_can_loop_back_to_implementing() -> None:
    """The self-fix loop."""
    assert lifecycle.can_transition(lifecycle.DEBUGGING, lifecycle.IMPLEMENTING)


def test_reviewing_can_loop_back_to_implementing() -> None:
    """The review-feedback loop."""
    assert lifecycle.can_transition(lifecycle.REVIEWING, lifecycle.IMPLEMENTING)


def test_any_active_state_can_escalate_to_needs_human() -> None:
    for state in lifecycle.ALL_STATES - lifecycle.TERMINAL_STATES:
        assert lifecycle.can_transition(state, lifecycle.NEEDS_HUMAN)


def test_deterministic_ids_are_stable() -> None:
    assert lifecycle.run_id("SCRUM-1", 1) == lifecycle.run_id("SCRUM-1", 1)
    assert lifecycle.run_id("SCRUM-1", 1) != lifecycle.run_id("SCRUM-1", 2)
```

- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement** — port v5's state machine with `SHIPPED` added to
  `TERMINAL_STATES`.
- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit**

---

### Task 3: `models.py`

**Files:** Create `meeting_notes/dev_agent/models.py`

- [ ] `DevAgentRun` — one `state` field (`lifecycle.ALL_STATES`), no parallel `status`.
  `JiraTicket`, `ClaudeRunResult` — port as-is.
- [ ] Test: `state_payload` coerces a JSON string (asyncpg returns JSONB as `str`) and a dict
  equally.

---

### Task 4: `guardrails.py` — seven gates, each with a planted violation

**Files:** Create `meeting_notes/dev_agent/guardrails.py`

Port v5's seven gates. Every gate gets a test that plants the exact violation it exists to
catch — a gate with only a "passes when clean" test hasn't proven anything.

- [ ] **Step 1: Write the failing tests** — one pair per gate (passes / planted violation):
  tests green/red, lint+type clean/dirty, diff budget within/over, protected paths clean/
  touches `.env`, no-new-deps clean/unpinned-without-opt-in, secret scan clean/plants an
  `sk-` token, module boundaries clean/plants a Cypher string in a file not allowed to hold
  it. Plus: `all_passed` and `failed_gates` on a mixed list.
- [ ] **Step 2-5:** run-fail → port → run-pass → commit.

---

### Task 5: `self_verify.py`

**Files:** Create `meeting_notes/dev_agent/self_verify.py`

- [ ] Test: `VerifyVerdict.passed` requires `checked AND addresses AND confidence >=
  threshold` — each condition independently, so a test can prove the gate isn't satisfied by
  any two of three.
- [ ] Test: verification never raises on a malformed model response — it degrades to
  `checked=False`, and `.passed` is then `False` regardless of the other fields.

---

### Task 6: `backend.py` — local, vertex (new), claude

**Files:** Create `meeting_notes/dev_agent/backend.py`

**Deliberately separate from `llm_client.py`** (CLAUDE.md) — this routes an `asyncio.subprocess`
invocation of the `claude` CLI, not a `chat_json`/`embed` call.

- [ ] **Step 1: Write the failing tests** — `resolve_backend_env` invariants per backend,
  unit-tested for all values (matching v5's own stated discipline): `local` empties
  `ANTHROPIC_API_KEY` so a real key in the parent env can never route to api.anthropic.com;
  `claude` sets the real key; **`vertex`** (new) sets `CLAUDE_CODE_USE_VERTEX=1` plus
  `ANTHROPIC_VERTEX_PROJECT_ID`/`CLOUD_ML_REGION` from `Settings`, no API key at all —
  authentication is Application Default Credentials, the same path `llm_client.py`'s
  `_vertex_auth_header()` already proved this session.
- [ ] Test: `preflight("vertex")` fails with an actionable message when `gcp_project_id` is
  blank, mirroring `preflight_local`'s LM Studio message.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 7: `git_ops.py`, `github_client.py`, `claude_runner.py`, `session_memory.py`

**Files:** Create all four

Port with one adaptation: v5 assumed a long-lived `REPO_DIR` bind-mounted into a Docker
Compose service. Cloud Run Jobs get a fresh, ephemeral filesystem per execution, so
`REPO_DIR`/`WORK_ROOT` default under `/tmp` and `ensure_repo_cloned` always does a fresh clone
rather than assuming a prior `fetch` will find anything — the "repo already exists, just
fetch" branch becomes dead code in this environment and should be removed, not kept as an
unreachable path.

- [ ] **Step 1: Write the failing tests** — `git_ops`: worktree create/remove sequence via an
  injected command runner (no real git); a stale worktree from a previous failed attempt is
  force-removed before creating the new one. `github_client`: `find_open_pr` returns `None` on
  an empty list, the first PR on a non-empty one. `claude_runner`: JSON parse of `claude`'s
  output, timeout handling, the "prefer parsed result, fall back to raw stdout, then stderr"
  error-detail chain. `session_memory`: `files_from_diff` extracts the `b/` side of each
  `diff --git` line; `build_memory` shapes a `pr_opened` vs `failed` outcome differently.
- [ ] **Step 2-5:** run-fail → port/adapt → run-pass → commit.

---

### Task 8: `orchestrator.py` — with the fix wired all the way through

**Files:** Create `meeting_notes/dev_agent/orchestrator.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_poll_never_resumes_a_shipped_run() -> None:
    """The end-to-end proof, not just the unit-level lifecycle/db tests above.
    A SHIPPED run must not reach process_ticket at all."""
    processed: list[str] = []

    async def fake_get_active_run():
        return DevAgentRun(ticket_key="SCRUM-1", state=lifecycle.SHIPPED, attempt_count=1)

    async def fake_process_ticket(ticket):
        processed.append(ticket["key"])

    await orchestrator.poll_and_process(
        get_active_run=fake_get_active_run, process_ticket=fake_process_ticket,
        should_attempt=lambda key, max_attempts: False,  # SHIPPED must fail this too
        find_sprint_candidates=lambda: [],
    )
    assert processed == [], "a SHIPPED run must never be resumed"


async def test_should_attempt_is_consulted_even_if_the_state_filter_somehow_missed_it() -> None:
    """Defence in depth, per ADR-020: should_attempt() is an INDEPENDENT check,
    not merely a second copy of the same terminal-state test."""
    async def fake_get_active_run():
        return DevAgentRun(ticket_key="SCRUM-1", state=lifecycle.IMPLEMENTING, attempt_count=1)

    calls = []
    await orchestrator.poll_and_process(
        get_active_run=fake_get_active_run,
        should_attempt=lambda key, max_attempts: calls.append(key) or False,
        process_ticket=lambda t: (_ for _ in ()).throw(AssertionError("must not run")),
        find_sprint_candidates=lambda: [],
    )
    assert calls == ["SCRUM-1"], "should_attempt must be consulted before resuming"


async def test_a_pr_found_gates_the_outcome_not_the_success_flag() -> None:
    """v5's real SCRUM-50 failure mode: a run can push a branch, open a PR, and
    still report success=False (e.g. hits the turn limit on a post-PR step).
    Dropping that PR and reverting to TO DO loses good work."""
    ...


async def test_process_ticket_advances_through_every_lifecycle_state_on_success() -> None:
    ...


async def test_a_missing_pr_marks_the_run_failed_and_records_session_memory() -> None:
    ...


async def test_the_prompt_never_instructs_the_agent_to_merge() -> None:
    """The one rule with zero tolerance."""
    prompt = orchestrator.build_prompt({"key": "SCRUM-1", "summary": "x", "description": "y"})
    assert "do not merge" in prompt.lower() or "not merge" in prompt.lower()
    assert "gh pr merge" not in prompt
```

- [ ] **Step 2-5:** run-fail → port with dependencies injected for testability → run-pass →
  commit.

---

### Task 9: `jobs/dev_agent_poll.py`

**Files:** Create `jobs/dev_agent_poll.py`

Thin entrypoint. No scheduler inside it — Cloud Scheduler owns the cadence.

- [ ] Test: `main()` calls `orchestrator.poll_and_process()` exactly once and returns its exit
  code; no `apscheduler` import anywhere in the file (static check, same pattern as the `api/`
  scheduler guard from Phase 8).

---

### Task 10: `/webhook/github` writes `CLOSED` on merge

**Files:** Modify `api/routers/webhooks.py`

Phase 8 built this acknowledge-only because ADR-008 deferred provenance writers to v2. This
phase un-defers exactly that write path — and only that one; other provenance writers stay
deferred.

- [ ] Test: a `pull_request` event with `action=closed, merged=true` transitions the matching
  `AgentRun`'s Jira ticket state to `CLOSED` and writes `RESOLVED_BY` (`Ticket → PullRequest`).
  A `closed, merged=false` event (a rejected PR) does not.
- [ ] Test: an event for a PR with no matching `AgentRun` is a no-op, not an error — most
  merged PRs on the repo are human work, not the agent's.

---

### Task 11: `api/routers/dev_agent.py`

**Files:** Create `api/routers/dev_agent.py`

- [ ] `POST /dev-agent/trigger/{ticket_key}` — bypasses triage filters, matching v5's
  `make dev-agent-trigger`.
- [ ] `GET /dev-agent/preflight` — the selected backend's readiness, with the actionable
  message `backend.preflight()` produces.
- [ ] `GET /dev-agent/runs` — recent runs, for a dashboard tab.
- [ ] Test via `httpx.ASGITransport`, per the Phase 8 convention — not a direct handler call.

---

### Task 12: Live verification — explicitly gated, not assumed

This is the task ADR-020 exists to take seriously: v5's checkpoint doc claimed nothing and was
honest about being blocked. This plan does the same rather than asserting success it hasn't
earned.

- [ ] **Confirm prerequisites before attempting anything:** a `GITHUB_TOKEN` with `repo`
  scope, `GITHUB_OWNER`/`GITHUB_REPO` pointed at a real repository the agent may open a real
  PR against, a Jira sprint ticket labelled for the agent, and Vertex billing headroom. If any
  is missing, **stop and say so** rather than simulating a run.
- [ ] `backend.preflight("vertex")` succeeds against the real project.
- [ ] One real ticket, end to end: triage finds it, a worktree is created, `claude_runner`
  produces a diff, a PR actually appears on GitHub, guardrails run against the real diff,
  self-verify scores it, the Jira ticket moves to the review status, and the run's state lands
  on `SHIPPED` — verified by querying `dev_agent_runs` directly, not by trusting the log line.
- [ ] **Prove the fix under the condition that caused the bug:** run `poll_and_process()`
  again immediately after the ticket above ships. Confirm `get_active_run()` returns `None`
  and no second `AgentRun` node was created — the direct antidote to "61 nodes for one
  ticket."
- [ ] Mark the phase done in `docs/PHASE_PLAN.md` only after this task actually ran, with the
  real ticket key and PR URL recorded. `graphify . --update`.

---

## Self-review notes

- **The bug fix is tested at three levels**, not one: `lifecycle.is_terminal` (the state
  machine itself), `ACTIVE_RUN_EXCLUDED_STATES == TERMINAL_STATES` (the SQL derives from the
  same source rather than a second copy), and `poll_and_process` end-to-end (a `SHIPPED` run
  never reaches `process_ticket`, and `should_attempt` is independently consulted). Fixing it
  in only one place would leave the other two able to drift again exactly as they did before.
- **Every guardrail gate has a planted-violation test**, not just a happy-path one — a gate
  that only proves it passes clean code hasn't proven it catches anything.
- **Task 12 is written to be honest under pressure to claim success.** ADR-020's entire
  justification is that v5's "it'll work eventually" checkpoint was never verified. Repeating
  that pattern here — writing "done" without a real ticket and a real PR — would undermine the
  reason this phase exists at all.
- **Scope boundaries hold:** `action_agent` is not touched; `/webhook/github` gains exactly one
  new write path (the merge → CLOSED transition this phase specifically needs), not a general
  provenance-writer rollout.
