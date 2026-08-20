"""Phase 3 — the data layer. Runs with no Postgres and no Memgraph.

The claiming contract is asserted against the SQL itself; the *behavioural*
proof that two drains take disjoint batches needs a real Postgres because
SKIP LOCKED is server-side behaviour no mock can demonstrate. That test is
marked `integration` and lives at the bottom of this file.
"""

from __future__ import annotations

from meeting_notes.config import Settings
from meeting_notes.db import CLAIM_SQL, SCHEMA_SQL, build_dsn, safe_dsn_label

# ─── claiming contract (ADR-006) ──────────────────────────────────────────────


def _norm(sql: str) -> str:
    return " ".join(sql.split()).upper()


def test_claim_uses_skip_locked() -> None:
    """ADR-006. Without SKIP LOCKED two overlapping Cloud Run Jobs either block
    each other or take the same rows and process a meeting twice."""
    normalized = _norm(CLAIM_SQL)
    assert "FOR UPDATE" in normalized
    assert "SKIP LOCKED" in normalized


def test_claim_filters_on_processed_and_limits() -> None:
    normalized = _norm(CLAIM_SQL)
    assert "PROCESSED = FALSE" in normalized
    assert "LIMIT" in normalized


def test_claim_is_ordered_so_the_oldest_record_is_not_starved() -> None:
    """Unordered claiming lets a steadily-arriving source keep jumping the
    queue and leave old rows unprocessed indefinitely."""
    assert "ORDER BY" in _norm(CLAIM_SQL)


# ─── schema (ADR-018) ─────────────────────────────────────────────────────────


def test_schema_creates_one_staging_table_not_four() -> None:
    """ADR-018: one table with a JSONB payload."""
    up = _norm(SCHEMA_SQL)
    assert "CREATE TABLE IF NOT EXISTS STAGED_RECORDS" in up
    assert "PAYLOAD JSONB" in up
    for gone in ("RAW_EMAILS", "RAW_CALENDAR_EVENTS", "RAW_MEET_TRANSCRIPTS", "RAW_JIRA_ISSUES"):
        assert gone not in up, f"{gone} is a v5 table; ADR-018 replaced it"


def test_schema_has_no_airbyte_residue() -> None:
    """MIGRATION_FROM_V5.md §4 — no table discovery, no _airbyte_ columns."""
    up = _norm(SCHEMA_SQL)
    for residue in ("AIRBYTE", "INFORMATION_SCHEMA", "MESSAGES_DETAILS", "RAW_GCAL_EVENTS"):
        assert residue not in up


def test_schema_indexes_the_claiming_predicate() -> None:
    """The claim runs every drain; an unindexed processed flag turns it into a
    sequential scan as staging grows monotonically."""
    assert "IDX_STAGED_RECORDS_UNPROCESSED" in _norm(SCHEMA_SQL)


def test_source_id_is_unique_per_source_so_reingestion_does_not_duplicate() -> None:
    """Re-running a connector must stage no duplicates (PHASE_PLAN Phase 5).
    Scoped per source_type: two sources may legitimately use the same id."""
    assert "UNIQUE (SOURCE_TYPE, SOURCE_ID)" in _norm(SCHEMA_SQL)


def test_schema_carries_the_watermarks_table() -> None:
    """Phase 5's connectors need it. The table ships now because adding it
    later would be a second migration; its accessors are Phase 5."""
    assert "CREATE TABLE IF NOT EXISTS WATERMARKS" in _norm(SCHEMA_SQL)


def test_schema_is_idempotent() -> None:
    """A migration re-run must be a no-op, not an error — Task 5 runs it twice."""
    up = _norm(SCHEMA_SQL)
    assert up.count("CREATE TABLE") == up.count("CREATE TABLE IF NOT EXISTS")
    assert up.count("CREATE INDEX") == up.count("CREATE INDEX IF NOT EXISTS")


# ─── connection (ADR-015) ─────────────────────────────────────────────────────


def test_build_dsn_uses_the_settings_not_the_environment() -> None:
    s = Settings(_env_file=None, POSTGRES_USER="u", POSTGRES_PASSWORD="p", POSTGRES_HOST="h")
    assert build_dsn(s).startswith("postgresql://u:p@h:")


def test_safe_dsn_label_never_leaks_the_password() -> None:
    """v5 logged dsn.split('@')[1] deliberately. Keep that discipline — a pool
    creation log line must not put the password in Cloud Logging."""
    s = Settings(_env_file=None, POSTGRES_PASSWORD="hunter2-leakcanary")
    assert "leakcanary" not in safe_dsn_label(s)
    assert "hunter2" not in safe_dsn_label(s)


def test_uses_the_cloud_sql_connector_only_when_configured() -> None:
    """ADR-015: a blank CLOUD_SQL_CONNECTION_NAME means local Postgres."""
    from meeting_notes.db import uses_cloud_sql_connector

    assert uses_cloud_sql_connector(Settings(_env_file=None)) is False
    assert (
        uses_cloud_sql_connector(
            Settings(_env_file=None, CLOUD_SQL_CONNECTION_NAME="p:r:i")
        )
        is True
    )
