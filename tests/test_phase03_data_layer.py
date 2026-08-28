"""Phase 3 — the data layer. Runs with no Postgres and no Memgraph.

The claiming contract is asserted against the SQL itself; the *behavioural*
proof that two drains take disjoint batches needs a real Postgres because
SKIP LOCKED is server-side behaviour no mock can demonstrate. That test is
marked `integration` and lives at the bottom of this file.
"""

from __future__ import annotations

import os
import uuid

import pytest

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


# ─── integration: needs `make demo-up` ────────────────────────────────────────
# Excluded from the default run. Execute with:
#     .venv/bin/python -m pytest -m integration


def _local_settings() -> Settings:
    """Point at the local compose Postgres regardless of the developer's .env."""
    return Settings(
        _env_file=None,
        POSTGRES_HOST=os.environ.get("POSTGRES_HOST", "localhost"),
        POSTGRES_PORT=int(os.environ.get("POSTGRES_PORT", "55432")),
        POSTGRES_USER=os.environ.get("POSTGRES_USER", "meeting_notes"),
        POSTGRES_PASSWORD=os.environ.get("POSTGRES_PASSWORD", "local_dev_only"),
        POSTGRES_DB=os.environ.get("POSTGRES_DB", "meeting_memory"),
        CLOUD_SQL_CONNECTION_NAME="",
    )


@pytest.mark.integration
async def test_two_concurrent_claims_take_disjoint_batches() -> None:
    """The ADR-006 guarantee, proven against a real Postgres.

    SKIP LOCKED is server-side behaviour: no mock can demonstrate it, which is
    exactly why PHASE_PLAN says to prove this rather than assume it. Two
    transactions claim concurrently from the same pool of staged rows. With
    SKIP LOCKED they take disjoint sets; without it the second blocks on the
    first's row locks until it commits.
    """
    import asyncpg

    settings = _local_settings()
    pool = await asyncpg.create_pool(build_dsn(settings), min_size=2, max_size=4)
    marker = f"concurrency-{uuid.uuid4()}"
    try:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            for i in range(20):
                await conn.execute(
                    "INSERT INTO staged_records (source_id, source_type, payload) "
                    "VALUES ($1, 'email', '{}'::jsonb)",
                    f"{marker}-{i}",
                )

        # Two connections, two open transactions, overlapping in time.
        c1 = await pool.acquire()
        c2 = await pool.acquire()
        try:
            t1 = c1.transaction()
            t2 = c2.transaction()
            await t1.start()
            await t2.start()
            batch1 = await c1.fetch(CLAIM_SQL, 10)
            batch2 = await c2.fetch(CLAIM_SQL, 10)
            ids1 = {r["id"] for r in batch1}
            ids2 = {r["id"] for r in batch2}
            await t1.rollback()
            await t2.rollback()
        finally:
            await pool.release(c1)
            await pool.release(c2)

        assert ids1, "first drain claimed nothing"
        assert ids2, "second drain claimed nothing — it blocked instead of skipping"
        assert not (ids1 & ids2), (
            f"the two drains claimed {len(ids1 & ids2)} overlapping rows; "
            "the same meeting would be processed twice"
        )
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM staged_records WHERE source_id LIKE $1", f"{marker}-%")
        await pool.close()


@pytest.mark.integration
async def test_restaging_the_same_source_id_does_not_duplicate() -> None:
    """A connector re-run must stage no duplicates (PHASE_PLAN Phase 5)."""
    import asyncpg

    from meeting_notes.db import stage_record

    settings = _local_settings()
    pool = await asyncpg.create_pool(build_dsn(settings), min_size=1, max_size=2)
    source_id = f"dup-{uuid.uuid4()}"
    try:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

        first = await stage_record(source_id, "email", {"subject": "hi"}, pool=pool)
        second = await stage_record(source_id, "email", {"subject": "hi again"}, pool=pool)

        assert first is not None, "the first stage should insert"
        assert second is None, "the second stage should be a no-op, not a duplicate row"

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM staged_records WHERE source_id = $1", source_id
            )
        assert count == 1
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM staged_records WHERE source_id = $1", source_id)
        await pool.close()


# ─── graph client write path ──────────────────────────────────────────────────


class FakeTx:
    """Records every Cypher statement instead of running it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.committed = False

    async def run(self, cypher: str, **params: object) -> None:
        self.calls.append((cypher, dict(params)))

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self) -> FakeTx:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def cypher(self) -> str:
        return "\n".join(c for c, _ in self.calls)


class FakeSession:
    def __init__(self, tx: FakeTx) -> None:
        self._tx = tx

    async def begin_transaction(self) -> FakeTx:
        return self._tx

    async def run(self, cypher: str, **params: object):  # type: ignore[no-untyped-def]
        class _Empty:
            def __aiter__(self):  # type: ignore[no-untyped-def]
                return self

            async def __anext__(self):  # type: ignore[no-untyped-def]
                raise StopAsyncIteration

        return _Empty()

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeDriver:
    def __init__(self, tx: FakeTx) -> None:
        self._tx = tx

    def session(self) -> FakeSession:
        return FakeSession(self._tx)


def _meeting(**over: object):  # type: ignore[no-untyped-def]
    from meeting_notes.models import ExtractedMeeting

    base = {
        "title": "Weekly sync",
        "kind": "meeting",
        "platform": "meet",
        "date": "2026-08-20",
        "summary": "we synced",
    }
    base.update(over)
    return ExtractedMeeting.model_validate(base)


async def test_the_whole_meeting_is_written_in_one_transaction() -> None:
    """CLAUDE.md: one ACID transaction per meeting. Sequential separate driver
    calls would leave a half-written meeting behind on failure."""
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(topics=["Budget"], decisions=["ship it"]),
        "src-1",
        driver=FakeDriver(tx),
        known_people=[],
    )
    assert tx.committed, "the transaction was never committed"
    assert len(tx.calls) > 1, "expected several statements inside the one transaction"


async def test_unique_nodes_are_merged_never_created() -> None:
    """CLAUDE.md: DO NOT use CREATE for unique nodes — always MERGE."""
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(topics=["Budget"], decisions=["ship it"], action_items=[{"owner": "a", "task": "t"}]),
        "src-1",
        driver=FakeDriver(tx),
        known_people=[],
    )
    body = tx.cypher()
    assert "MERGE (m:Meeting" in body
    import re

    assert not re.search(r"\bCREATE\s+\((?!.*ON CREATE)", body), "found a bare CREATE for a node"


async def test_topic_merge_key_is_normalised() -> None:
    """CLAUDE.md: the Topic MERGE key is lowercased and stripped. Raw case
    fragmented one real topic across several nodes in v5 and silently
    understated every insight query."""
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(topics=["  Budget Planning  "]), "src-1", driver=FakeDriver(tx), known_people=[]
    )
    topic_params = [p for c, p in tx.calls if "Topic" in c]
    assert topic_params
    assert topic_params[0]["name"] == "budget planning"


async def test_action_owner_is_resolved_so_assigned_to_can_form() -> None:
    """Regression test for MIGRATION_FROM_V5.md bug #1.

    v5 bound `owner_email = action.owner if "@" in action.owner else None`.
    The extractor emits display names, so that was almost always None,
    OPTIONAL MATCH (p:Person {email: null}) matched nothing, and the live
    ASSIGNED_TO edge count was ZERO. The owner now goes through the same
    person resolution the attendees do.
    """
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(action_items=[{"owner": "Alice Smith", "task": "ship it"}]),
        "src-1",
        driver=FakeDriver(tx),
        known_people=[{"name": "Alice Smith", "email": "alice@corp.com", "tracked": True}],
    )
    action_params = [p for c, p in tx.calls if "ActionItem" in c]
    assert action_params
    assert action_params[0]["owner_email"] == "alice@corp.com", (
        "the display-name owner was not resolved; ASSIGNED_TO will never form"
    )


async def test_an_unresolvable_action_owner_leaves_owner_email_null() -> None:
    """No match must not invent an email — it just means no ASSIGNED_TO edge."""
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(action_items=[{"owner": "Nobody Known", "task": "t"}]),
        "src-1",
        driver=FakeDriver(tx),
        known_people=[],
    )
    action_params = [p for c, p in tx.calls if "ActionItem" in c]
    assert action_params[0]["owner_email"] is None


async def test_unresolved_attendees_are_held_for_review_not_dropped() -> None:
    """CLAUDE.md: attendees are never silently dropped."""
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(attendees=[{"name": "Ghost Person"}]),
        "src-1",
        driver=FakeDriver(tx),
        known_people=[],
    )
    assert "PersonReview" in tx.cypher()


async def test_meeting_id_is_deterministic_from_the_source_id() -> None:
    """Re-processing the same record must MERGE onto the same Meeting."""
    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    tx = FakeTx()
    returned = await graph_client.upsert_meeting_graph(
        _meeting(), "src-1", driver=FakeDriver(tx), known_people=[]
    )
    assert returned == uuid5_id("meeting", "src-1")


# ─── memgraph schema (ADR-008) ────────────────────────────────────────────────


def test_every_core_and_memory_label_is_constrained() -> None:
    """CLAUDE.md's schema: every node has a unique id. A label with no
    constraint silently permits duplicates that MERGE cannot collapse."""
    from scripts.setup_memgraph import statements

    body = "\n".join(statements(embedding_dimension=768))
    for label in (
        "Meeting", "Person", "Organization", "Topic", "Decision", "ActionItem",
        "Fact", "Preference", "Procedure", "ProcedureStep", "MemorySession",
        "PersonReview", "Blocker",
    ):
        assert label in body, f"{label} has no constraint or index"


def test_provenance_labels_ship_in_v1_even_though_writers_are_v2() -> None:
    """ADR-008: provenance cannot be backfilled. A merge that happens before
    the schema exists is lost forever, so the schema ships now and only the
    writers wait for v2."""
    from scripts.setup_memgraph import statements

    body = "\n".join(statements(embedding_dimension=768))
    for label in ("Ticket", "PullRequest", "AgentRun", "Commit", "FileChange"):
        assert label in body, f"provenance label {label} missing — ADR-008 requires it in v1"


def test_both_vector_indexes_use_the_configured_dimension() -> None:
    """CLAUDE.md: 768 in both backends because the indexes are built for 768.
    Hardcoding a different number silently breaks semantic search."""
    from scripts.setup_memgraph import statements

    vector = [s for s in statements(embedding_dimension=768) if "VECTOR INDEX" in s.upper()]
    assert len(vector) >= 2, "expected a Meeting and a Fact vector index"
    assert all('"dimension": 768' in s for s in vector)


def test_vector_dimension_follows_settings_rather_than_being_hardcoded() -> None:
    """If someone migrates the indexes, the setting is the single knob."""
    from scripts.setup_memgraph import statements

    vector = [s for s in statements(embedding_dimension=1024) if "VECTOR INDEX" in s.upper()]
    assert vector and all('"dimension": 1024' in s for s in vector)


def test_statements_are_individually_runnable() -> None:
    """Memgraph takes one statement per run(); a semicolon-joined blob fails."""
    from scripts.setup_memgraph import statements

    for s in statements(embedding_dimension=768):
        assert ";" not in s, f"statement contains a semicolon: {s[:60]}"


async def test_blockers_are_written_inside_the_same_transaction() -> None:
    """The Blocker writer that existed (`merge_blocker`) opened its OWN session,
    which would have made the blocker a sequential separate driver call —
    exactly what CLAUDE.md forbids — and nothing called it anyway. Blockers
    belong in the meeting's one transaction, beside decisions."""
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(blockers=[{"text": "waiting on the SOW", "raised_by": "a@b.c"}]),
        "src-1",
        driver=FakeDriver(tx),
        known_people=[],
    )

    cypher = tx.cypher()
    assert "Blocker" in cypher, "no Blocker node written"
    assert "RAISES_BLOCKER" in cypher, "the blocker is not linked to the meeting"
    assert "MERGE (b:Blocker" in cypher, "unique nodes are MERGEd, never CREATEd"
    assert tx.committed

    written = [p for c, p in tx.calls if "Blocker" in c]
    assert written and written[0]["text"] == "waiting on the SOW"
    assert written[0]["raised_by"] == "a@b.c"


async def test_a_meeting_with_no_blockers_writes_none() -> None:
    from meeting_notes import graph_client

    tx = FakeTx()
    await graph_client.upsert_meeting_graph(
        _meeting(), "src-2", driver=FakeDriver(tx), known_people=[]
    )
    assert "Blocker" not in tx.cypher()


async def test_db_exposes_reading_and_replacing_staged_records() -> None:
    """Consolidating per-message email rows into per-thread rows needs to read
    a source's staged rows and swap them for a smaller set. Both are SQL, so
    both live in db.py -- a migration script writing its own would be the
    second SQL-owning module CLAUDE.md forbids."""
    from meeting_notes import db

    assert hasattr(db, "list_staged_by_type")
    assert hasattr(db, "replace_staged_records")


def test_resolve_owner_email_matches_attendee_roster_first() -> None:
    from meeting_notes.graph_client import _resolve_owner_email
    from meeting_notes.models import Attendee
    from meeting_notes.person_resolver import Roster

    attendees = [
        Attendee(name="Michael Baylard", email="michael.baylard@onixnet.com"),
        Attendee(name="Katrisa Brock", email="katrisa.brock@onixnet.com"),
    ]
    roster = Roster([])

    # 1. Full name match
    assert _resolve_owner_email("Michael Baylard", roster, [], attendees=attendees) == "michael.baylard@onixnet.com"
    # 2. First name / given name match
    assert _resolve_owner_email("Katrisa", roster, [], attendees=attendees) == "katrisa.brock@onixnet.com"
    # 3. Email local-part match
    assert _resolve_owner_email("michael.baylard", roster, [], attendees=attendees) == "michael.baylard@onixnet.com"
    # 4. Exact email match
    assert _resolve_owner_email("michael.baylard@onixnet.com", roster, [], attendees=attendees) == "michael.baylard@onixnet.com"
    # 5. Non-person / unresolvable team
    assert _resolve_owner_email("All delivery associates", roster, [], attendees=attendees) is None
