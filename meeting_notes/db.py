"""Cloud SQL staging — the ONLY module in this package containing SQL.

Deliberately a REWRITE of v5's `transform_service/db.py`, not a port. v5's is
shaped end to end by Airbyte: it discovers a hash-suffixed Jira table through
`information_schema`, ALTERs Airbyte's own tables to add a `processed` flag,
and has one getter per source each with an "Airbyte table preferred, ours as
fallback" branch. None of that survives — v6 owns every connector
(MIGRATION_FROM_V5.md §4).

Three ADRs shape what replaced it:

* **ADR-018** — one `staged_records` table with a JSONB payload instead of
  four typed raw tables, so there is one claiming query and one drain path.
* **ADR-006** — rows are *claimed* with `SELECT ... FOR UPDATE SKIP LOCKED`.
  v5 had no such thing; a plain `WHERE processed = false LIMIT n` was safe
  only because v5 ran a single container. Cloud Run Jobs can overlap.
* **ADR-015** — connection mode is chosen from configuration: the Cloud SQL
  connector when `CLOUD_SQL_CONNECTION_NAME` is set, a plain DSN otherwise.
  That is a connection-acquisition branch, not a second query path. Every
  query below runs unmodified against both.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.dev_agent.lifecycle import TERMINAL_STATES
from meeting_notes.dev_agent.models import DevAgentRun
from meeting_notes.models import SourceType, StagedRecord

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


# ─── schema ───────────────────────────────────────────────────────────────────
# Applied once as a migration (`make migrate`), NOT re-asserted on every drain
# the way v5's create_staging_tables() was. Every statement is IF NOT EXISTS so
# re-running is a no-op rather than an error.

SCHEMA_SQL = """
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

-- Per-source ingestion watermarks. The table ships with this migration
-- because adding it later would be a second migration; its accessors are
-- Phase 5, with the connectors that need them.
CREATE TABLE IF NOT EXISTS watermarks (
    source_type TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Phase 11 (ADR-020): the dev agent's own run tracking. One `state` column,
# not v5's parallel `state` + `status` pair -- two overlapping vocabularies
# for "is this run done" is exactly the kind of duplicated source of truth
# that let them drift and produce the SHIPPED resume-loop bug. `state` is
# always one of meeting_notes.dev_agent.lifecycle.ALL_STATES.
DEV_AGENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dev_agent_runs (
    ticket_key    TEXT PRIMARY KEY,
    state         TEXT NOT NULL,
    branch_name   TEXT,
    pr_url        TEXT,
    pr_number     INTEGER,
    error         TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    state_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# The other half of the ADR-020 fix: this set is TERMINAL_STATES itself, not
# a second spelling of it. v5 hardcoded 'CLOSED','FAILED','NEEDS_HUMAN' a
# second time in this exact query and it silently drifted from
# TERMINAL_STATES (which was missing SHIPPED) -- that drift, not a typo, was
# the bug. Building the SQL from the constant makes the two unable to
# disagree by construction.
ACTIVE_RUN_EXCLUDED_STATES = TERMINAL_STATES

_active_run_placeholders = ", ".join(f"${i + 1}" for i in range(len(ACTIVE_RUN_EXCLUDED_STATES)))
_GET_ACTIVE_DEV_AGENT_RUN_SQL = f"""
SELECT * FROM dev_agent_runs
WHERE state NOT IN ({_active_run_placeholders})
ORDER BY started_at DESC NULLS LAST
LIMIT 1
"""

_GET_DEV_AGENT_RUN_SQL = "SELECT * FROM dev_agent_runs WHERE ticket_key = $1"

_CLAIM_DEV_AGENT_RUN_SQL = """
INSERT INTO dev_agent_runs (ticket_key, state, branch_name, attempt_count, started_at)
VALUES ($1, $2, $3, 1, now())
ON CONFLICT (ticket_key) DO UPDATE
SET state         = EXCLUDED.state,
    branch_name   = EXCLUDED.branch_name,
    attempt_count = dev_agent_runs.attempt_count + 1,
    started_at    = now(),
    finished_at   = NULL,
    error         = NULL
"""

_FINISH_DEV_AGENT_RUN_SQL = """
UPDATE dev_agent_runs
SET state       = $2,
    pr_url      = $3,
    pr_number   = $4,
    error       = $5,
    finished_at = now()
WHERE ticket_key = $1
"""

_SET_DEV_AGENT_STATE_SQL = "UPDATE dev_agent_runs SET state = $2 WHERE ticket_key = $1"

_SET_DEV_AGENT_SESSION_MEMORY_SQL = """
UPDATE dev_agent_runs SET state_payload = $2::jsonb WHERE ticket_key = $1
"""

# ─── the claim (ADR-006) ──────────────────────────────────────────────────────
# ORDER BY fetched_at so a steadily-arriving source cannot keep jumping the
# queue and leave older rows unprocessed forever. SKIP LOCKED is what makes two
# concurrent drains take disjoint batches instead of blocking or overlapping.
# Must be run inside a transaction — the row locks are held until it commits.

CLAIM_SQL = """
SELECT id, source_id, source_type, payload, fetched_at, processed
FROM staged_records
WHERE processed = FALSE
ORDER BY fetched_at
FOR UPDATE SKIP LOCKED
LIMIT $1
"""

_INSERT_SQL = """
INSERT INTO staged_records (source_id, source_type, payload)
VALUES ($1, $2, $3::jsonb)
ON CONFLICT (source_type, source_id) DO NOTHING
RETURNING id
"""

LIST_BY_TYPE_SQL = """
SELECT id, source_id, source_type, payload, fetched_at, processed
FROM staged_records
WHERE source_type = $1
ORDER BY fetched_at
"""

DELETE_STAGED_SQL = "DELETE FROM staged_records WHERE source_id = ANY($1::text[])"

_MARK_PROCESSED_SQL = """
UPDATE staged_records
SET processed = TRUE, processed_at = now()
WHERE id = $1::uuid
"""

_GET_WATERMARK_SQL = "SELECT value FROM watermarks WHERE source_type = $1"

_SET_WATERMARK_SQL = """
INSERT INTO watermarks (source_type, value)
VALUES ($1, $2)
ON CONFLICT (source_type) DO UPDATE SET value = $2, updated_at = now()
"""


# ─── connection (ADR-015) ─────────────────────────────────────────────────────


def uses_cloud_sql_connector(settings: Settings) -> bool:
    """True when the Cloud SQL connector should be used instead of a plain DSN."""
    return bool(settings.cloud_sql_connection_name.strip())


def build_dsn(settings: Settings) -> str:
    """Plain-Postgres DSN. Only used when the Cloud SQL connector is not."""
    return (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def safe_dsn_label(settings: Settings) -> str:
    """A host/db label safe to log. Never contains the password.

    v5 logged `dsn.split("@")[1]` for exactly this reason; making it a named
    function means the discipline survives someone reformatting the log line.
    """
    if uses_cloud_sql_connector(settings):
        return f"cloudsql:{settings.cloud_sql_connection_name}/{settings.postgres_db}"
    return f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"


async def get_pool(settings: Settings | None = None) -> asyncpg.Pool:
    """Process-wide connection pool, created on first use."""
    global _pool
    if _pool is not None:
        return _pool

    settings = settings or get_settings()

    if uses_cloud_sql_connector(settings):
        # Imported lazily: tier 0 runs against local Postgres and must not need
        # the GCP connector installed or credentialed.
        from google.cloud.sql.connector import Connector, IPTypes

        connector = Connector(refresh_strategy="lazy")

        async def _connect() -> asyncpg.Connection:
            conn: asyncpg.Connection = await connector.connect_async(
                settings.cloud_sql_connection_name,
                "asyncpg",
                user=settings.postgres_user,
                password=settings.postgres_password,
                db=settings.postgres_db,
                ip_type=IPTypes.PUBLIC,
            )
            return conn

        _pool = await asyncpg.create_pool(connect=_connect, min_size=2, max_size=10)
    else:
        _pool = await asyncpg.create_pool(build_dsn(settings), min_size=2, max_size=10)

    log.info("db.pool_created", target=safe_dsn_label(settings))
    return _pool


async def close_pool() -> None:
    """Close the pool. Cloud Run Jobs are short-lived; leaking it holds server slots."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ─── operations ───────────────────────────────────────────────────────────────


async def apply_migrations(pool: asyncpg.Pool | None = None) -> None:
    """Apply the schema. Idempotent — safe to run against an existing database."""
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
        await conn.execute(DEV_AGENT_SCHEMA_SQL)
    log.info("db.migrations_applied")


async def stage_record(
    source_id: str,
    source_type: SourceType,
    payload: dict[str, Any],
    pool: asyncpg.Pool | None = None,
) -> str | None:
    """Stage one raw record. Returns its id, or None if already staged.

    The ON CONFLICT DO NOTHING is what makes re-running a connector safe:
    (source_type, source_id) is unique, so a re-fetch stages no duplicate.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_INSERT_SQL, source_id, source_type, json.dumps(payload))
    return str(row["id"]) if row else None


async def claim_batch(limit: int, pool: asyncpg.Pool | None = None) -> list[StagedRecord]:
    """Claim up to `limit` unprocessed records (ADR-006).

    Rows stay locked for the life of the transaction opened here, so two
    concurrent drains take disjoint batches. Note the batch is returned after
    the transaction commits: the caller processes records it has claimed and
    marks each one done individually, so a slow record does not hold locks
    across the whole batch.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch(CLAIM_SQL, limit)
    return [
        StagedRecord(
            id=str(r["id"]),
            source_id=r["source_id"],
            source_type=r["source_type"],
            payload=json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"],
            fetched_at=r["fetched_at"].isoformat(),
            processed=r["processed"],
        )
        for r in rows
    ]


async def list_staged_by_type(
    source_type: str, pool: asyncpg.Pool | None = None
) -> list[StagedRecord]:
    """Every staged row for one source, processed or not.

    Used by the email-thread consolidation, which has to see the whole set to
    group it -- `claim_batch` deliberately hands out a locked subset and is
    the wrong tool for a migration.
    """
    pool = pool or await get_pool()
    rows = await pool.fetch(LIST_BY_TYPE_SQL, source_type)
    return [
        StagedRecord(
            id=str(r["id"]),
            source_id=r["source_id"],
            source_type=r["source_type"],
            payload=json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"],
            fetched_at=r["fetched_at"].isoformat(),
            processed=r["processed"],
        )
        for r in rows
    ]


async def get_staged_payload(source_id: str, pool: asyncpg.Pool | None = None) -> dict[str, Any] | None:
    """Retrieve raw staged payload for a given source_id."""
    pool = pool or await get_pool()
    row = await pool.fetchrow(
        "SELECT payload FROM staged_records WHERE source_id = $1 LIMIT 1", source_id
    )
    if not row:
        return None
    raw = row["payload"]
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {"text": raw}
    return raw


async def replace_staged_records(
    source_type: str,
    old_ids: list[str],
    new_records: list[tuple[str, dict[str, Any]]],
    pool: asyncpg.Pool | None = None,
) -> int:
    """Swap a set of staged rows for a different set, in ONE transaction.

    Deleting first and inserting after without a transaction would, on a
    failure between the two, lose the source data outright -- there is no
    other copy of a staged payload once the rows are gone.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as con, con.transaction():
        if old_ids:
            await con.execute(DELETE_STAGED_SQL, old_ids)
        for source_id, payload in new_records:
            await con.execute(_INSERT_SQL, source_id, source_type, json.dumps(payload))
    return len(new_records)


async def mark_processed(record_id: str, pool: asyncpg.Pool | None = None) -> None:
    """Mark one staged record done.

    v5 took a `table` argument and validated it against an allow-list of six
    table names. ADR-018 leaves one table, so there is nothing to disambiguate.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_MARK_PROCESSED_SQL, record_id)


async def get_watermark(source_type: str, pool: asyncpg.Pool | None = None) -> str | None:
    """The last watermark this source reached, or None if it has never run."""
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        value: str | None = await conn.fetchval(_GET_WATERMARK_SQL, source_type)
    return value


async def set_watermark(source_type: str, value: str, pool: asyncpg.Pool | None = None) -> None:
    """Advance a source's watermark.

    Called only after every record in a batch has staged — see
    `sources.base.stage_all` for why that ordering matters.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SET_WATERMARK_SQL, source_type, value)


# ─── dev_agent_runs (Phase 11, ADR-020) ───────────────────────────────────────
# All Postgres access for the dev agent goes through these functions.
# meeting_notes/dev_agent/* owns no SQL of its own (CLAUDE.md: one SQL module).


def _row_to_dev_agent_run(row: Any) -> DevAgentRun:
    return DevAgentRun(**dict(row))


async def claim_dev_agent_run(
    ticket_key: str, state: str, branch_name: str, pool: asyncpg.Pool | None = None
) -> None:
    """Start (or restart) a run. `attempt_count` increments on every claim of an
    already-known ticket_key — a fresh attempt after FAILED, or a resume."""
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_CLAIM_DEV_AGENT_RUN_SQL, ticket_key, state, branch_name)


async def finish_dev_agent_run(
    ticket_key: str,
    state: str,
    pr_url: str | None = None,
    pr_number: int | None = None,
    error: str | None = None,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Close out a run in a terminal state, recording the PR it produced.

    `finished_at` is stamped here and nowhere else, so "is this run over" has
    one answer in the database as well as one in `lifecycle.TERMINAL_STATES`.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_FINISH_DEV_AGENT_RUN_SQL, ticket_key, state, pr_url, pr_number, error)


async def set_dev_agent_state(
    ticket_key: str, state: str, pool: asyncpg.Pool | None = None
) -> None:
    """Persist a lifecycle transition. Callers validate the edge themselves via
    `dev_agent.lifecycle` — this function writes whatever state it is given."""
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SET_DEV_AGENT_STATE_SQL, ticket_key, state)


async def get_dev_agent_run(
    ticket_key: str, pool: asyncpg.Pool | None = None
) -> DevAgentRun | None:
    """This ticket's run, whatever state it is in, or None if never attempted."""
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_DEV_AGENT_RUN_SQL, ticket_key)
    return _row_to_dev_agent_run(row) if row else None


async def get_active_dev_agent_run(pool: asyncpg.Pool | None = None) -> DevAgentRun | None:
    """The single non-terminal run to resume, if any (one active run at a time).

    Excludes every state in ACTIVE_RUN_EXCLUDED_STATES == TERMINAL_STATES —
    the ADR-020 fix. A run in any of those states, including SHIPPED, is done
    and must not be picked up again here.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_ACTIVE_DEV_AGENT_RUN_SQL, *ACTIVE_RUN_EXCLUDED_STATES)
    return _row_to_dev_agent_run(row) if row else None


async def should_attempt_dev_agent_run(
    ticket_key: str, max_attempts: int, pool: asyncpg.Pool | None = None
) -> bool:
    """Whether a NEW attempt on this ticket is allowed.

    The second, independent half of the ADR-020 fix: a caller resuming a run
    found by `get_active_dev_agent_run` must ALSO pass this check, not rely on
    the exclusion list alone. A terminal state (including SHIPPED) always
    returns False, regardless of attempt_count.
    """
    run = await get_dev_agent_run(ticket_key, pool=pool)
    if run is None:
        return True
    if run.state in TERMINAL_STATES:
        if run.state == "FAILED":
            return run.attempt_count < max_attempts
        return False
    # An active, non-terminal state (e.g. IMPLEMENTING) means a run is already
    # in flight — do not start a second one on top of it.
    return False


async def get_dev_agent_session_memory(
    ticket_key: str, pool: asyncpg.Pool | None = None
) -> dict[str, Any] | None:
    """The resumable record a retry reads, or None.

    Lives in Postgres rather than on the graph's AgentRun node because the
    resume read happens BEFORE a run, on a failed attempt where no PR — and
    so no AgentRun node — exists yet.
    """
    run = await get_dev_agent_run(ticket_key, pool=pool)
    return run.state_payload if run else None


async def set_dev_agent_session_memory(
    ticket_key: str, memory: dict[str, Any], pool: asyncpg.Pool | None = None
) -> None:
    """Persist what this attempt learned, for the next one to read."""
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SET_DEV_AGENT_SESSION_MEMORY_SQL, ticket_key, json.dumps(memory))


async def list_recent_dev_agent_runs(
    limit: int = 50, pool: asyncpg.Pool | None = None
) -> list[DevAgentRun]:
    """Recent runs, newest first — the dashboard's dev-agent panel."""
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM dev_agent_runs ORDER BY created_at DESC LIMIT $1", limit
        )
    return [_row_to_dev_agent_run(r) for r in rows]


def _main() -> int:
    """`make migrate` — apply the schema, then report what exists.

    A thin entrypoint so the migration is runnable without a separate script;
    all the logic above stays importable and testable.
    """
    import asyncio

    async def run() -> int:
        settings = get_settings()
        print(f"  applying schema to {safe_dsn_label(settings)}")
        pool = await get_pool(settings)
        try:
            await apply_migrations(pool)
            async with pool.acquire() as conn:
                tables = await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
                )
                staged = await conn.fetchval("SELECT count(*) FROM staged_records")
            print("  tables: " + ", ".join(t["tablename"] for t in tables))
            print(f"  staged_records rows: {staged}")
        finally:
            await close_pool()
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(_main())
