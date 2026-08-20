# Phase 5 Connectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four connectors that fetch from Gmail, Calendar, Meet and Jira and stage rows into `staged_records` — incrementally, idempotently, and with a loud failure when the token dies.

**Architecture:** One `Source` protocol: given a watermark, fetch what changed and stage it. Every source shares one OAuth token helper and one watermark store, so incremental behaviour is implemented once rather than four times. `jobs/ingest_*.py` are thin `main()` entrypoints — all logic lives in `meeting_notes/sources/`.

**Tech Stack:** Python 3.11+ · `httpx.AsyncClient` · `asyncpg` · `pytest`

## Global Constraints

From `CLAUDE.md`.

- **DO NOT use synchronous `requests`** — always `httpx.AsyncClient`.
- **DO NOT put SQL outside `db.py`** — watermark accessors go there, not in a source.
- **DO NOT put Jira REST calls outside `jira_client.py`.**
- DO NOT read `os.environ` outside `config.py`.
- **`jobs/` contains entrypoints only.** If a job file grows past ~50 lines, the logic belongs in the package.
- `@with_retry(max_attempts=3, base_delay=2.0)` on every external call.
- **Never pass `event=` as a structlog kwarg** — it collides with the reserved field and raises `TypeError` at call time. This was a real production 500 in v5. Use `source_event=`.
- Deterministic ids: `uuid5_id(namespace, value)`, re-derived identically everywhere.
- All connector tests mocked; **no live credentials in the suite**.
- One test file for the phase: `tests/test_phase05_connectors.py`.

---

## What is a port and what is new

v5 leaned on Airbyte for Gmail, Calendar and Jira, so most of this phase has no v5 equivalent.

| Module | Status | Note |
|---|---|---|
| `sources/base.py` | **New** | v5's `TranscriptSource` is a *read-already-staged-rows* seam (33 lines), not a fetch-from-upstream one. Same name, different concept — the v6 protocol fetches and stages. |
| `sources/gmail.py` | **New** | Airbyte did this |
| `sources/calendar.py` | **New** | Airbyte did this |
| `sources/jira.py` | **New**, over a ported client | |
| `jira_client.py` | **Port** (239 lines) | The ONLY file with Jira REST |
| `sources/meet.py` | **Port** of `meet_ingest.py` (123 lines) | Pub/Sub pull; the one connector v5 owned |
| `google_auth.py` | **New**, extracted | `scripts/auth_spike.py` already refreshes tokens correctly, but lives in `scripts/`; connectors need it in the package |

---

## File Structure

| File | Responsibility |
|---|---|
| `meeting_notes/google_auth.py` | Refresh-token → access-token, with a loud expiry error. |
| `meeting_notes/sources/base.py` | The `Source` protocol + `stage_all` helper. |
| `meeting_notes/sources/{gmail,calendar,jira,meet}.py` | One per source. |
| `meeting_notes/jira_client.py` | The ONLY file with Jira REST. |
| `meeting_notes/db.py` | Modify: watermark accessors (deferred here from Phase 3). |
| `jobs/ingest_{gmail,calendar,jira,meet}.py` | Thin entrypoints. |
| `jobs/refresh_tokens.py` | Token refresh with an alert on failure. |
| `tests/test_phase05_connectors.py` | One test file for the phase. |

---

### Task 1: Watermarks and the `Source` protocol

**Files:**
- Modify: `meeting_notes/db.py`
- Create: `meeting_notes/sources/base.py`, `meeting_notes/sources/__init__.py`

**Interfaces:**
- Produces: `db.get_watermark(source_type)`, `db.set_watermark(source_type, value)`, `Source` protocol, `stage_all(source, pool)`

The watermark table shipped in Phase 3's migration; its accessors were deferred to here.

- [ ] **Step 1: Write the failing tests** — a fresh source has no watermark; setting then getting round-trips; `stage_all` stages every fetched record and advances the watermark **only after** staging succeeds (advancing first would silently skip records on a mid-batch failure).
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 2: `google_auth.py`

**Files:**
- Create: `meeting_notes/google_auth.py`

**Interfaces:**
- Produces: `TokenExpired`, `get_access_token(settings, *, transport=None)`

Refreshing is already solved in `scripts/auth_spike.py`; this is the package-resident version the
connectors and `jobs/refresh_tokens.py` share.

**The expiry path is an exit criterion**, so it gets its own test: an `invalid_grant` response
must raise `TokenExpired` naming `make auth-spike ARGS=--reconsent`, never return `None` and
let a connector quietly stage zero rows.

- [ ] **Step 1: Write the failing tests** — a good refresh returns a token; `invalid_grant`
  raises `TokenExpired` with the remediation; the refresh token is never logged.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 3: `sources/gmail.py`

**Files:**
- Create: `meeting_notes/sources/gmail.py`

Incremental by `internalDate`, watermark = the newest `internalDate` seen. Messages are listed
then fetched; the body is base64url in nested MIME parts, which is the fiddly part and gets its
own tests.

- [ ] **Step 1: Write the failing tests** — the query carries the watermark; a plain-text body
  decodes; a nested multipart body decodes; a message with no body does not crash; staging is
  keyed on the Gmail message id so a re-run stages nothing new.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 4: `sources/calendar.py`

**Files:**
- Create: `meeting_notes/sources/calendar.py`

Incremental by `updatedMin`. Attendees and the description carry the useful signal.

- [ ] **Step 1: Write the failing tests** — `updatedMin` is sent; an all-day event (`date`
  rather than `dateTime`) does not crash; a cancelled event is skipped; attendees survive.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 5: `jira_client.py` and `sources/jira.py`

**Files:**
- Create: `meeting_notes/jira_client.py`, `meeting_notes/sources/jira.py`

Port the client from v5. JQL by `updated >= watermark`. **When `JIRA_ENABLED` is false the
source is a clean no-op, not an error** — tiers 0 and 1 must run the pipeline fully without a
Jira account.

- [ ] **Step 1: Write the failing tests** — disabled Jira stages nothing and does not raise;
  the JQL carries the watermark; issues stage with their key as `source_id`.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 6: `sources/meet.py`

**Files:**
- Create: `meeting_notes/sources/meet.py`

Port `meet_ingest.py`. Pub/Sub **pull**, not push — no inbound endpoint, and it is the pattern
v5 already proved. **An unset `MEET_PUBSUB_SUBSCRIPTION` disables transcript ingestion cleanly
as a no-op**, per `.env.example`.

- [ ] **Step 1: Write the failing tests** — no subscription configured is a no-op; a
  `fileGenerated` event decodes; transcript entries are joined into text; messages are acked
  **only after** staging succeeds.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 7: `jobs/` entrypoints

**Files:**
- Create: `jobs/ingest_{gmail,calendar,jira,meet}.py`, `jobs/refresh_tokens.py`

Thin `main()` only. A job file past ~50 lines means logic leaked out of the package.

- [ ] **Step 1: Write the failing test** — assert every job file is under 50 lines and contains
  no business logic beyond wiring. That rule is easy to erode silently, so it gets a test.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 8: Live verification

Needs `sync-up` (Cloud SQL) and a valid OAuth token, so it costs money and time — run it once,
deliberately, at the end.

- [ ] **Step 1: `make sync-up ENV=personal`**
- [ ] **Step 2: Run each connector against the real Onix account** and confirm rows land.
- [ ] **Step 3: Re-run every connector** and confirm **zero** new rows — the idempotency exit
  criterion, proven rather than assumed.
- [ ] **Step 4: Deliberately corrupt the token** and confirm a visible alert rather than a
  silent zero-row success.
- [ ] **Step 5: `make sync-down ENV=personal`**, then mark the phase done and run
  `graphify . --update`.

---

## Self-review notes

- **Spec coverage:** PHASE_PLAN tasks 1-8 map to Tasks 1-7; all four exit criteria are in
  Task 8, with idempotency and the token alert proven live rather than asserted.
- **Shared concerns are implemented once** — one token helper, one watermark store, one
  `stage_all` — rather than four times with three subtle variations.
- **Both "disabled" paths are no-ops, not errors** (Jira without credentials, Meet without a
  subscription), because tier 0 must run the whole pipeline with neither.
- **The watermark advances only after staging succeeds.** The reverse order loses records
  permanently on a mid-batch failure, and that is invisible until someone asks why a week of
  meetings is missing.
