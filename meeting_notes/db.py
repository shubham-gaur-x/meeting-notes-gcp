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

_MARK_PROCESSED_SQL = """
UPDATE staged_records
SET processed = TRUE, processed_at = now()
WHERE id = $1::uuid
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


async def mark_processed(record_id: str, pool: asyncpg.Pool | None = None) -> None:
    """Mark one staged record done.

    v5 took a `table` argument and validated it against an allow-list of six
    table names. ADR-018 leaves one table, so there is nothing to disambiguate.
    """
    pool = pool or await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_MARK_PROCESSED_SQL, record_id)
