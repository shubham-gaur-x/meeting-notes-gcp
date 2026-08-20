# Phase 6 Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One pipeline that takes a staged record all the way to a graph write and, where warranted, a Jira ticket — the milestone phase: `staged → classified → routed → extracted → graph → Jira`.

**Architecture:** ADR-010's collapse: one `pipeline.process(record, adapter)` instead of three near-identical copies. Each source contributes a small `Adapter` that shapes a `staged_records` payload into classifier input, router input, and extractor context — the pipeline itself never branches on source type. `jira_pusher` gates on confidence and dedup before creating anything; `jira_sync` is the reverse direction, syncing Jira status back into the graph.

**Tech Stack:** Python 3.11+ · the Phase 2-5 modules already built · `pytest`

## Global Constraints

From `CLAUDE.md`.

- **One ACID transaction per meeting** — already true of `graph_client.upsert_meeting_graph`; the pipeline must not split it.
- **DO NOT call `memory/retrieval.py` from `pipeline.py`.** Retrieval is query-time only (not built until Phase 7, so this is a boundary to respect going forward, not a task here).
- **DO NOT put Jira REST calls outside `jira_client.py`.**
- `ActionItem.confidence` and `Decision.confidence` gate side effects. Below `JIRA_CONFIDENCE_THRESHOLD`, write the node with `jira_status = needs_review` and surface it in the review queue instead of creating a Jira ticket.
- `@with_retry(max_attempts=3, base_delay=2.0)` on every external call.
- Never pass `event=` as a structlog kwarg.
- One test file for the phase: `tests/test_phase06_pipeline.py`.

---

## What already exists, and one fix needed before starting

**Bug #1 (`ASSIGNED_TO`) is already fixed** — Phase 3's `graph_client.upsert_meeting_graph`
resolves `action.owner` through `person_resolver` before writing, and the Phase 3 smoke write
proved a live `ASSIGNED_TO` edge forming from a display name. This plan does not re-do that
work; Task 5's live check re-confirms it end-to-end rather than assuming it still holds.

**Two real gaps found reading v5 closely, fixed in Task 1 before anything is built on them:**

1. `graph_client.get_open_actions_for_owner` has no `exclude_id`. v5's dedup candidate query
   excludes the action currently being evaluated (`a.id <> $exclude_id`) because by the time
   `jira_pusher` runs, `upsert_meeting_graph` has already written *every* action item in the
   meeting — including the one being deduped. Without the exclusion, an item can match
   itself at similarity 1.0 and silently link `MENTIONED_IN` to its own node.
2. `graph_client.update_action_jira_status` returns `None`. v5's returns whether a node was
   actually matched, derived from the write summary's counters rather than guessed — `jira_sync`
   needs this so its matched/unmatched counters mean something instead of always reporting a
   match.

---

## File Structure

| File | Responsibility |
|---|---|
| `meeting_notes/graph_client.py` | Modify: the two fixes above. |
| `meeting_notes/jira_client.py` | Modify: add `create_issue`, sprint lookup/move. |
| `meeting_notes/pipeline.py` | The one `process(record, adapter)`, plus one `Adapter` per source. |
| `meeting_notes/jira_pusher.py` | Confidence gate → dedup gate → create → link. |
| `meeting_notes/jira_sync.py` | Jira status → graph, the reverse direction. |
| `jobs/pipeline_drain.py` | Thin entrypoint: claim a batch, process each, mark done. |
| `tests/test_phase06_pipeline.py` | One test file for the phase. |

---

### Task 1: Fix the two `graph_client.py` gaps

**Files:**
- Modify: `meeting_notes/graph_client.py`
- Test: `tests/test_phase06_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_get_open_actions_for_owner_excludes_the_given_id() -> None:
    """Without exclude_id, an item can match itself at similarity 1.0 -- by
    the time jira_pusher runs, upsert_meeting_graph already wrote it."""
    ...

async def test_update_action_jira_status_reports_whether_it_matched() -> None:
    """jira_sync's matched/unmatched counters must mean something."""
    ...

async def test_update_action_jira_status_reports_false_for_an_unknown_key() -> None:
    """A Jira ticket created outside this pipeline is real signal, not a bug."""
    ...
```

- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 2: `pipeline.py` — the collapse

**Files:**
- Create: `meeting_notes/pipeline.py`

**Interfaces:**
- Produces: `Adapter` protocol (`text`, `classify_context`, `router_title`, `router_body`,
  `extract_context`), `EmailAdapter`, `CalendarAdapter`, `MeetAdapter`, `process(record, adapter)`

One function, not three. `process` takes a `StagedRecord` and its adapter and runs:
classify → gate on threshold → route → extract → gate on `None` → graph write → push to Jira.
Every step logs which record and which step, matching v5's bound-logger pattern.

**The Meet adapter keeps v5's one real behavioural difference**: a transcript is strong
signal on its own, so it skips the classifier's score gate when transcript text is present —
only the fallback (no transcript, title/description only) is scored normally.

- [ ] **Step 1: Write the failing tests** — a low-score record is marked processed and does
  nothing further; a failed extraction is marked processed, not retried (temperature 0); a
  successful record reaches the graph write; the Meet adapter bypasses the score gate when
  transcript text is present.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 3: `jira_client.py` additions

**Files:**
- Modify: `meeting_notes/jira_client.py`

**Interfaces:**
- Produces: `create_issue(...)`, `active_sprint_id()`, `move_to_sprint(key, sprint_id)`

Port from v5's `jira_pusher.py`, where these currently live inline rather than in the client —
a boundary violation this phase corrects, since `CLAUDE.md` says all Jira REST lives in
`jira_client.py`.

- [ ] **Step 1: Write the failing tests** — priority maps to Jira's three levels; a
  non-engineering task gets the `meeting-action-item` label, an engineering one does not;
  a high-priority issue is moved to the active sprint, others are not; a sprint-move failure
  does not fail issue creation (the issue already exists and is more valuable un-sprinted
  than lost).
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 4: `jira_pusher.py` and `jira_sync.py`

**Files:**
- Create: `meeting_notes/jira_pusher.py`, `meeting_notes/jira_sync.py`

Port from v5's `jira_pusher.py` and `jira_agent.py`. Confidence gate first, dedup gate
second, using the Task 1 `exclude_id` fix and `llm_client.embed` in place of v5's
`vector_memory.embed_text` (Phase 7 territory, not yet built — the embedding call is
inlined here for now).

- [ ] **Step 1: Write the failing tests** — below-threshold items are marked `needs_review`
  and create no ticket (exit criterion); a near-duplicate links `MENTIONED_IN` and comments
  rather than opening a second ticket (exit criterion); disabled Jira or a missing token is a
  clean no-op; `jira_sync` marks a staged Jira record processed exactly once whether or not it
  matched a node.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 5: `jobs/pipeline_drain.py` and live verification

**Files:**
- Create: `jobs/pipeline_drain.py`

Thin entrypoint: `db.claim_batch` → `pipeline.process` per record with the adapter selected by
`source_type` → `db.mark_processed`.

**150 real records are already staged locally from Phase 5** (50 emails, 100 calendar
events) — no new ingestion needed for this check, and no Cloud SQL spend, matching the
Phase 5 precedent of proving against local Postgres.

- [ ] **Step 1: `make demo-up`**, run `pipeline_drain` against the real staged Onix data with
  `LLM_BACKEND=vertex`.
- [ ] **Step 2: Verify with a Cypher count, not by reading the code** — `ASSIGNED_TO` edges
  exist; a Meeting node has `DISCUSSED`/`PRODUCED`/`FOLLOWS_UP` edges as appropriate.
- [ ] **Step 3: Confidence gating, live** — find or construct a low-confidence action item and
  confirm it reaches `needs_review` with no Jira call attempted.
- [ ] **Step 4: Dedup, live** — process the same recurring action item twice (two staged
  records) and confirm the second links `MENTIONED_IN` rather than duplicating.
- [ ] **Step 5: The Jira leg.** No `JIRA_API_TOKEN` is configured in this environment. Steps 2-4
  prove everything up to and including the confidence/dedup gates against real data; the literal
  "graph → Jira ticket" hop needs a decision — see below — before it can be proven live rather
  than by mocked test alone.
- [ ] **Step 6: `make demo-down`**, mark the phase done, `graphify . --update`.

---

## Self-review notes

- **Spec coverage:** PHASE_PLAN tasks 1-4 map to Tasks 2-4; bug #1 is confirmed rather than
  re-fixed, since Phase 3 already did the work; all four exit criteria are addressed in
  Task 5, with the Jira-creation leg flagged as needing a credential decision rather than
  silently skipped.
- **Two real bugs fixed before they could bite `jira_pusher`**, both found reading v5's
  `get_open_actions_for_owner` and `update_action_jira_status` closely rather than porting
  blind.
- **The Meet adapter's classifier bypass is deliberate**, carried from v5: a real transcript
  is strong signal that should not be discarded by a text-classifier score built for shorter
  inputs like email subjects.
