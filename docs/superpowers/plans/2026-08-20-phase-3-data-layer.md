# Phase 3 Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the two I/O modules — `db.py` (Cloud SQL staging, claimed with `SKIP LOCKED`) and `graph_client.py` (Memgraph, the single home for generic Cypher) — plus `scripts/setup_memgraph.py`, and *prove* that two concurrent drains claim disjoint batches.

**Architecture:** `db.py` is a **rewrite, not a port**: v5's is dominated by Airbyte table-shape workarounds and has no `SKIP LOCKED` anywhere. ADR-018 collapses its four per-source getters into one claiming query, ADR-006 adds the row claiming, and ADR-015 adds dual-mode connection selection. `graph_client.py` *is* a port, scoped to the write path and the primitives Phases 5–7 need; the API read functions follow in Phase 8 where endpoint tests will actually exercise them. `setup_memgraph.py` owns every constraint and index, including the v1 provenance schema (ADR-008).

**Tech Stack:** Python 3.11+ · `asyncpg` · `cloud-sql-python-connector` · `neo4j` (Bolt) · `pytest` · Docker Compose for the live checks

## Global Constraints

Copied verbatim from `CLAUDE.md`.

- **DO NOT put SQL outside `meeting_notes/db.py`.**
- **DO NOT put generic Cypher outside `meeting_notes/graph_client.py`.** The memory modules may issue Cypher only for the node/edge types they own.
- **DO NOT put MAGE `CALL` procedures anywhere except `graph_algorithms.py`** (Phase 7).
- **DO NOT use `CREATE` in Cypher for unique nodes — always `MERGE`.**
- **DO NOT make sequential separate driver calls for related nodes — one ACID transaction.**
- DO NOT read `os.environ` outside `config.py`.
- DO NOT derive a provenance node id anywhere except the one helper that owns it. Writer/reader id drift cost real debugging time twice in v5.
- `@with_retry(max_attempts=3, base_delay=2.0)` on every external call.
- Type hints on all signatures; `ruff` line-length 110; Pydantic v2.
- Tests are mocked — the suite must run with no live GCP, no database, no LLM.
- One test file per phase: `tests/test_phase03_data_layer.py`.

---

## Scope: what is ported, deferred, and dropped

`memgraph_client.py` is 1181 lines across 37 functions. Porting all of it now would add ~20
functions with no consumer until Phase 8 and no way to test them beyond asserting a query
string contains `MERGE`. That is not coverage, it is theatre. The split below is by *who calls
it*, and every deferral is recorded rather than assumed.

| v5 function | Disposition |
|---|---|
| `get_driver`, `close_driver` | **Phase 3** — everything needs them |
| `create_indexes` | **Phase 3** → moves into `scripts/setup_memgraph.py` |
| `get_known_people` | **Phase 3** — `person_resolver` needs it (Phase 6) |
| `upsert_meeting_graph` | **Phase 3** — *the* write path, one transaction |
| `update_action_jira_key`, `get_open_actions_for_owner`, `link_action_mentioned_in`, `mark_action_needs_review`, `get_action_confidence`, `update_action_jira_status` | **Phase 3** — `jira_pusher` / `jira_sync` need them in Phase 6 |
| `merge_blocker` | **Phase 3** — review-queue write, small |
| `get_meetings_quality_inputs`, `set_meeting_quality` | **Phase 7** — nightly quality job, with `score_all_meetings` |
| 16 read/query functions (`get_timeline`, `get_person_graph`, `get_influential_nodes`, `get_all_communities`, …) plus `_group_meeting_provenance`, `_group_ticket_provenance`, `_fold_run` | **Phase 8** — consumed only by API endpoints, and testable properly there via `httpx.ASGITransport` |
| `write_run_provenance`, `write_commits_and_files`, `merge_ticket_resolved_by_pr` | **v2** — ADR-008 ships the provenance *schema* in v1 and leaves the *writers* for v2 |
| `migrate_schema_v5` | **Dropped** — a v5-specific one-off migration |

The provenance **constraints and indexes still ship in Phase 3** (`setup_memgraph.py`).
ADR-008 is explicit: provenance cannot be backfilled, so the schema must exist from day one
even though nothing writes to it yet.

---

## File Structure

| File | Responsibility |
|---|---|
| `meeting_notes/db.py` | Cloud SQL. The ONLY file with SQL. Migration, staging, `SKIP LOCKED` claiming. |
| `meeting_notes/graph_client.py` | Memgraph. The ONLY file with generic Cypher. Driver + write path. |
| `scripts/setup_memgraph.py` | Constraints, indexes, both 768-dim vector indexes, provenance schema. |
| `tests/test_phase03_data_layer.py` | One test file for the phase. |
| `Makefile` | Modify: `migrate` target points at the real module. |

---

### Task 1: `db.py` — connection, schema, claiming

**Files:**
- Create: `meeting_notes/db.py`
- Test: `tests/test_phase03_data_layer.py`

**Interfaces:**
- Produces: `get_pool()`, `close_pool()`, `apply_migrations(conn)`, `stage_record(...)`, `claim_batch(limit)`, `mark_processed(record_id)`, `SCHEMA_SQL`, `CLAIM_SQL`

**This is a rewrite.** What does *not* come across from v5, and why:

- `sync_airbyte_jira_to_staging()` — a documented no-op wrapper around Airbyte.
- `_jira_airbyte_table()` — discovers a hash-suffixed Airbyte table via `information_schema`.
- The Airbyte branches in `get_unprocessed_emails` / `get_unprocessed_events` / `get_unprocessed_jira_issues` — all four getters collapse into one `claim_batch` (ADR-018).
- The `ALTER TABLE … ADD COLUMN processed` calls against Airbyte's tables in `create_staging_tables`.
- `create_staging_tables()` itself as a *heartbeat*: schema is a migration run once, not something re-asserted on every drain (`PHASE_PLAN` Phase 3 task 1).
- `mark_processed(table, record_id)` loses its `table` parameter and its table-name allow-list. There is one table now.

**What is genuinely new:** `SELECT … FOR UPDATE SKIP LOCKED` (ADR-006). v5 has none — it does
a plain `WHERE processed = false LIMIT n`, which is safe only because v5 ran a single
container. Cloud Run Jobs can overlap, so this is the defence.

- [ ] **Step 1: Write the failing tests**

```python
"""Phase 3 — the data layer. Runs with no Postgres and no Memgraph.

The claiming contract is asserted against the SQL itself plus a fake pool;
the *behavioural* proof that two drains take disjoint batches needs a real
Postgres and lives in Task 5, gated behind a marker.
"""

from __future__ import annotations

import pytest

from meeting_notes.db import CLAIM_SQL, SCHEMA_SQL, build_dsn


def test_claim_uses_skip_locked() -> None:
    """ADR-006. Without SKIP LOCKED two overlapping Cloud Run Jobs block each
    other or, worse, take the same rows."""
    normalized = " ".join(CLAIM_SQL.split()).upper()
    assert "FOR UPDATE" in normalized
    assert "SKIP LOCKED" in normalized


def test_claim_filters_on_processed_and_limits() -> None:
    normalized = " ".join(CLAIM_SQL.split()).upper()
    assert "PROCESSED = FALSE" in normalized
    assert "LIMIT" in normalized


def test_schema_creates_one_staging_table_not_four() -> None:
    """ADR-018: one table with a JSONB payload."""
    up = SCHEMA_SQL.upper()
    assert "CREATE TABLE IF NOT EXISTS STAGED_RECORDS" in up
    assert "PAYLOAD JSONB" in up
    for gone in ("RAW_EMAILS", "RAW_CALENDAR_EVENTS", "RAW_MEET_TRANSCRIPTS", "RAW_JIRA_ISSUES"):
        assert gone not in up, f"{gone} is a v5 table; ADR-018 replaced it"


def test_schema_has_no_airbyte_residue() -> None:
    """MIGRATION_FROM_V5.md §4 — no table discovery, no _airbyte_ columns."""
    up = SCHEMA_SQL.upper()
    for residue in ("AIRBYTE", "INFORMATION_SCHEMA", "MESSAGES_DETAILS", "RAW_GCAL_EVENTS"):
        assert residue not in up


def test_schema_indexes_the_claiming_predicate() -> None:
    """The claim runs every drain; an unindexed processed flag makes it a
    sequential scan as staging grows."""
    assert "IDX_STAGED_RECORDS_UNPROCESSED" in SCHEMA_SQL.upper()


def test_source_id_is_unique_so_reingestion_does_not_duplicate() -> None:
    """Re-running a connector must stage no duplicates (PHASE_PLAN Phase 5)."""
    up = SCHEMA_SQL.upper()
    assert "UNIQUE" in up and "SOURCE_ID" in up


def test_build_dsn_uses_the_settings_not_the_environment() -> None:
    from meeting_notes.config import Settings

    s = Settings(_env_file=None, POSTGRES_USER="u", POSTGRES_PASSWORD="p", POSTGRES_HOST="h")
    assert build_dsn(s).startswith("postgresql://u:p@h:")


def test_build_dsn_never_leaks_the_password_in_logs() -> None:
    """v5 logged dsn.split('@')[1] deliberately. Keep that discipline."""
    from meeting_notes.db import safe_dsn_label
    from meeting_notes.config import Settings

    s = Settings(_env_file=None, POSTGRES_PASSWORD="hunter2-leakcanary")
    assert "leakcanary" not in safe_dsn_label(s)
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: No module named 'meeting_notes.db'`

- [ ] **Step 3: Implement**

`get_pool()` branches on `cloud_sql_connection_name` per ADR-015 — Cloud SQL connector when
set, plain DSN when blank. **All SQL stays in this file**; the branch is connection
acquisition only, not a second query path.

Schema (one table, ADR-018), plus a `watermarks` table the Phase 5 connectors will need —
the table ships now because adding it later is a second migration, but its accessors are
Phase 5:

```sql
CREATE TABLE IF NOT EXISTS staged_records (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id    TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    payload      JSONB NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed    BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    UNIQUE (source_type, source_id)
);

-- Partial index: the claim only ever looks at unprocessed rows, and staging
-- grows monotonically. A full index would keep indexing rows nothing reads.
CREATE INDEX IF NOT EXISTS idx_staged_records_unprocessed
    ON staged_records (fetched_at) WHERE processed = FALSE;

CREATE TABLE IF NOT EXISTS watermarks (
    source_type TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

The claim (ADR-006):

```sql
SELECT id, source_id, source_type, payload, fetched_at, processed
FROM staged_records
WHERE processed = FALSE
ORDER BY fetched_at
FOR UPDATE SKIP LOCKED
LIMIT $1
```

- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit**

---

### Task 2: `graph_client.py` — driver and the write path

**Files:**
- Create: `meeting_notes/graph_client.py`
- Test: `tests/test_phase03_data_layer.py`

**Interfaces:**
- Produces: `get_driver()`, `close_driver()`, `get_known_people()`, `upsert_meeting_graph(meeting, resolutions)`, and the six action/Jira helpers listed in the scope table.

Port from `transform_service/memgraph_client.py`. `upsert_meeting_graph` is ~195 lines and is
the one that matters: it MERGEs Meeting, People, Organizations, Topics, Decisions and
ActionItems **in a single transaction**. Do not split it into sequential driver calls.

**Two v5 bugs to fix during this port**, both from `MIGRATION_FROM_V5.md`:

1. **Bug #1 — `ASSIGNED_TO` never forms.** The Cypher does
   `OPTIONAL MATCH (p:Person {email: $owner_email})` where `owner_email` is only non-null when
   `"@" in action.owner`; the extractor emits display names, so the live edge count is **zero**.
   The fix belongs in Phase 6 (resolve `action.owner` through `person_resolver` before the
   write), but `upsert_meeting_graph` must *accept* a resolved owner email so Phase 6 has
   somewhere to put it. Leave a test asserting the parameter exists.
2. **Topic MERGE key must be lowercased and stripped** (`CLAUDE.md`). Using raw case fragmented
   single topics across multiple nodes in v5 and silently understated every insight query.

- [ ] **Step 1: Write the failing tests** — driven by a fake driver/session so no Memgraph is
  needed. Assert: one transaction rather than N calls; `MERGE` not `CREATE` for every unique
  node; the topic key is normalised; `upsert_meeting_graph` takes a resolved-owner parameter.
- [ ] **Step 2-5:** run-fail → port → run-pass → commit.

---

### Task 3: `scripts/setup_memgraph.py`

**Files:**
- Create: `scripts/setup_memgraph.py`
- Test: `tests/test_phase03_data_layer.py`

Owns every constraint and index. Must include, per `CLAUDE.md` and ADR-008:

- Uniqueness constraints on `id` for every node label in the core, memory, review and
  **provenance** vocabularies.
- Both **768-dimensional** vector indexes. The dimension is fixed by
  `settings.embedding_dimension`; hardcoding a different number silently breaks semantic search.
- The v1 provenance constraints — `Ticket`, `PullRequest`, `AgentRun`, `Commit`, `FileChange`,
  `Blocker` — even though their writers are v2.

- [ ] **Step 1: Write the failing tests** — assert every label in `CLAUDE.md`'s schema appears
  in the generated statements, that the vector indexes use `settings.embedding_dimension`, and
  that the provenance labels are present (the ADR-008 promise).
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 4: Makefile and docs

- [ ] `migrate` target runs the real migration module rather than a placeholder.
- [ ] `setup-memgraph` target already points at `scripts.setup_memgraph`; verify it runs.
- [ ] Record the Phase 8 / v2 deferrals from the scope table in `docs/PHASE_PLAN.md`.

---

### Task 5: Live verification — the exit criteria

Everything above runs with no services. These three do not, and `PHASE_PLAN` demands them.
They use the **local Docker stack**, not GCP, so they cost nothing.

- [ ] **Step 1: Bring the local stack up**

```bash
make demo-up
```

- [ ] **Step 2: Schema applies cleanly to a fresh Postgres and a fresh Memgraph**

```bash
make migrate
make setup-memgraph
```
Both must be **idempotent** — run each twice and confirm the second run is a no-op rather
than an error.

- [ ] **Step 3: PROVE two concurrent drains claim disjoint batches**

This is the exit criterion `PHASE_PLAN` explicitly says to prove rather than assume. It needs
a real Postgres because `SKIP LOCKED` is server-side behaviour that no mock can demonstrate.
Mark it so the default suite stays service-free:

```python
@pytest.mark.integration
async def test_two_concurrent_claims_take_disjoint_batches() -> None:
    """The ADR-006 guarantee, proven against a real Postgres.

    Two transactions claim concurrently from a pool of staged rows. With
    SKIP LOCKED they take disjoint sets; without it one blocks or they
    overlap and the same meeting is processed twice.
    """
    await _seed(20)
    async with pool.acquire() as c1, pool.acquire() as c2:
        async with c1.transaction(), c2.transaction():
            batch1 = await c1.fetch(CLAIM_SQL, 10)
            batch2 = await c2.fetch(CLAIM_SQL, 10)

    ids1 = {r["id"] for r in batch1}
    ids2 = {r["id"] for r in batch2}
    assert ids1 and ids2
    assert not (ids1 & ids2), "the two drains claimed overlapping rows"
```

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["integration: needs the local Docker stack (make demo-up)"]
```

and run it explicitly: `.venv/bin/python -m pytest -m integration`.

- [ ] **Step 4: One smoke write against the real Memgraph**

Write a meeting through `upsert_meeting_graph`, then verify with a Cypher count — not by
reading the code.

- [ ] **Step 5: Tear the stack down** — `make demo-down`

- [ ] **Step 6: Mark the phase done** in `docs/PHASE_PLAN.md` and run `graphify . --update`.

---

## Self-review notes

- **Phase plan coverage:** task 1 → Task 1, task 2 → Task 2, task 3 → Task 3. All three exit
  criteria are in Task 5, and the concurrency one is proven against a real Postgres because
  `SKIP LOCKED` cannot be demonstrated with a mock.
- **`db.py` is a rewrite and the plan says so**, rather than pretending a port. Every v5 piece
  that does not come across is listed with its reason.
- **Scope is cut by consumer, not by convenience:** ~16 read functions defer to Phase 8 where
  endpoint tests can exercise them, and three provenance writers defer to v2 per ADR-008 —
  while the provenance *schema* still ships now, because it cannot be backfilled.
- **Two known v5 bugs are addressed in the port**: the `ASSIGNED_TO` parameter gap (fixed
  fully in Phase 6) and the Topic case-fragmentation MERGE key.
