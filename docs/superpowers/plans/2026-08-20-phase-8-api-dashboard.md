# Phase 8 API and Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything built so far becomes something you can look at — a FastAPI service on Cloud Run with every v5 endpoint, a four-tab dashboard, HMAC-verified webhooks, and zero APScheduler.

**Architecture:** `api/` holds routers and nothing else; all logic stays in `meeting_notes/`. The ~16 graph read functions Phase 3 deferred here land first, because every endpoint is a thin wrapper over one. Auth reuses `access_control.py` from Phase 2 rather than inventing a second model.

**Tech Stack:** FastAPI · `httpx.ASGITransport` · Cloud Run (`min-instances=0`) · single-file HTML dashboard, no build step

## Global Constraints

From `CLAUDE.md` and `MIGRATION_FROM_V5.md`.

- **DO NOT use APScheduler or any in-process scheduler.** v5's `main.py` has 17 references; v6 must have zero. Scheduling is Cloud Scheduler → Cloud Run Jobs.
- **`api/` contains entrypoints only.** A route that grows past a few lines means logic belongs in the package.
- **DO NOT put generic Cypher outside `graph_client.py`.**
- **Never pass `event=` to structlog** — it collides with the reserved message field and raises `TypeError` at call time. Use `github_event=`. This was a real production 500 in v5, caught only because a route function was never itself exercised by a test.
- **`Person.tracked` gates per-person analytics.** `/graph/insights/influential` must respect it — the governance promise.
- **Every route needs an `httpx.ASGITransport` test driving the real ASGI app** (`MIGRATION_FROM_V5.md` #3) — not a direct call to the handler function, which is exactly how v5 missed the `event=` bug.
- Type hints on all signatures; tests run with no live services.
- One test file for the phase: `tests/test_phase08_api.py`.

---

## Endpoint inventory: ported, deferred, dropped

v5's `main.py` exposes 28 routes. Not all should exist in v6.

| Route | Disposition |
|---|---|
| `/health` | **Port**, minus the LM Studio ping — v6 has four backends, so it checks the configured one |
| `/dashboard` | **Port** |
| `/graph/meetings/recent`, `/graph/person/{email}`, `/graph/topic/{name}`, `/graph/actions/open`, `/graph/timeline`, `/graph/digest/weekly` | **Port** |
| `/review/actions`, `/review/people`, `/review/blockers` | **Port** — the review queues are the confidence-gating payoff |
| `/graph/insights/influential`, `/communities`, `/bridges`, `/node/{id}` | **Port**, with the `tracked` gate on `influential` |
| `/graph/memory/query`, `/memory/person/{email}`, `/memory/sessions` | **Port** — Phase 7 built the functions behind these |
| `/graph/search/meetings`, `/graph/search/facts` | **Port** |
| `/graph/procedures`, `/graph/procedures/{name}` | **Port** |
| `/meetings/quality` | **Port**, needs the two quality graph functions Phase 3 deferred |
| `/graph/provenance/{meeting_id}`, `/by-ticket/{key}` | **Port the readers.** They return empty until v2 writes provenance — that is honest and expected (ADR-008), not a bug |
| `/webhook/github` | **Port**, HMAC-verified |
| `/webhook/jira` | **New** — `PHASE_PLAN` task 3 |
| `/webhook/airbyte` | **DROPPED** — there is no Airbyte in v6 |
| `/agent/actions/run` | **DEFERRED to v2** — `action_agent` is out of scope (ADR-008) |

---

### Task 1: The deferred graph read functions

**Files:** Modify `meeting_notes/graph_client.py`

Phase 3 deferred these here on the reasoning that they are only callable by the API and are
testable properly once endpoints exist. That bill comes due now.

- [ ] `get_recent_meetings`, `get_timeline`, `get_person_graph`, `get_topic_graph`,
  `get_open_actions`
- [ ] `get_actions_needing_review`, `get_person_reviews`, `get_open_blockers`
- [ ] `get_influential_nodes` (**tracked-gated**), `get_all_communities`,
  `get_community_members`, `get_bridge_nodes`, `get_node_insights`
- [ ] `get_meeting_provenance`, `get_ticket_provenance` + the three fold helpers
- [ ] `get_meetings_quality_inputs`, `set_meeting_quality`, `get_meetings_quality_ranked`
- [ ] **Topic lookup must normalise** — `get_topic_graph` is the read side of the same key
  that bit `INTERESTED_IN` in Phase 7. Use `normalise_topic`.
- [ ] Tests: each returns shaped data from a fake driver; `get_influential_nodes` filters
  untracked people.

---

### Task 2: GitHub webhook verification

**Files:** Create `meeting_notes/github_webhook.py`

- [ ] `verify_signature(body, header, secret)` — constant-time HMAC-SHA256 compare.
- [ ] **An unset secret must not silently accept in production.** v5 defaulted to accept when
  the secret was unset, which is a reasonable dev default and a bad deployed one. v6 accepts
  only when the secret is unset **and** the settings say local.
- [ ] Tests: valid signature passes; tampered body fails; wrong secret fails; missing header
  with a configured secret fails.

---

### Task 3: `api/main.py` and routers

**Files:** Create `api/main.py`, `api/routers/*.py`

- [ ] App factory, CORS, structured logging, lifespan that closes the graph driver.
- [ ] Routers grouped by concern: `graph`, `review`, `insights`, `memory`, `webhooks`.
- [ ] **Auth on query endpoints** via `access_control.resolve_principal` / `authorize`.
  Webhooks stay public but HMAC-verified.
- [ ] **Zero APScheduler.** A test asserts the string appears nowhere in `api/`.

---

### Task 4: Dashboard

**Files:** Create `api/static/dashboard.html`

- [ ] Port v5's single-file page (263 lines, no build step).
- [ ] Point it at v6 routes; keep all four tabs.

---

### Task 5: Every route under `httpx.ASGITransport`

**Files:** `tests/test_phase08_api.py`

This is the criterion `MIGRATION_FROM_V5.md` #3 exists for: v5's tests called handler
functions directly, so a `structlog` `event=` collision inside a route was never exercised and
reached production as a 500.

- [ ] Drive the **real ASGI app** for every route, with graph calls injected.
- [ ] Assert `/graph/insights/influential` excludes untracked people.
- [ ] Assert the webhook rejects a bad signature with 401.
- [ ] Assert no route passes `event=` to structlog — a static check over `api/`.

---

### Task 6: Live verification

- [ ] `make demo-up`, run the API against the real 95-meeting graph.
- [ ] **Open the dashboard in a browser** and confirm all four tabs render with no console
  errors — `PHASE_PLAN` says check in a browser, not just in tests.
- [ ] Confirm `/graph/insights/influential` returns aggregates, not untracked names.
- [ ] `make demo-down`, mark the phase done, `graphify . --update`.

Cloud Run deployment (task 4 of the phase) is **deferred to Phase 9** with the rest of the
deploy work: it needs the ephemeral tier up, and the API is verifiable locally against the
same graph.

---

## Self-review notes

- **Scope is explicit about what is not built:** `/webhook/airbyte` is dropped outright,
  `/agent/actions/run` waits for v2, and the provenance readers ship returning empty because
  ADR-008 puts their writers in v2.
- **The `event=` trap is addressed twice** — once as a rule, once as a static test — because
  the v5 incident happened specifically where tests were not looking.
- **The topic-normalisation bug from Phase 7 has a read-side twin** in `get_topic_graph`, and
  this plan names it rather than rediscovering it.
