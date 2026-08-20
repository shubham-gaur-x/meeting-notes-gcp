"""Memgraph — the ONLY module in this package containing generic Cypher.

Ported from v5's `transform_service/memgraph_client.py`, scoped to the write
path and the primitives Phases 5-7 need. The ~16 read/query functions that
only the API calls follow in Phase 8, where endpoint tests can actually
exercise them; the three provenance *writers* are v2 per ADR-008, though the
provenance schema itself ships now in `scripts/setup_memgraph.py`.

Two changes from v5:

* **Bug #1 from MIGRATION_FROM_V5.md is fixed here.** v5 bound
  ``owner_email = action.owner if "@" in action.owner else None``. The
  extractor emits display names, so that was almost always None,
  ``OPTIONAL MATCH (p:Person {email: null})`` matched nothing, and the live
  ``ASSIGNED_TO`` edge count was **zero**. Action owners now go through the
  same person resolution the attendees already did.
* **Roster and known people are injected**, not fetched from configuration
  inside the write. v5 called `load_roster()`, which read `os.environ`
  directly — forbidden by CLAUDE.md, and it made the write path untestable
  without a live database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase

from meeting_notes import person_resolver
from meeting_notes.config import Settings, get_settings
from meeting_notes.models import Attendee, ExtractedMeeting
from meeting_notes.person_resolver import Roster
from meeting_notes.utils import uuid5_id, with_retry

log = structlog.get_logger()

_driver: AsyncDriver | None = None


def get_driver(settings: Settings | None = None) -> AsyncDriver:
    """Process-wide Bolt driver, created on first use."""
    global _driver
    if _driver is None:
        settings = settings or get_settings()
        uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
        auth = (
            (settings.memgraph_user, settings.memgraph_password) if settings.memgraph_user else None
        )
        _driver = AsyncGraphDatabase.driver(uri, auth=auth)
        log.info("memgraph.driver_created", uri=uri)
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def get_known_people(driver: Any | None = None) -> list[dict[str, Any]]:
    """Existing Person nodes, for probabilistic resolution (email, name, tracked)."""
    driver = driver or get_driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Person) WHERE p.email IS NOT NULL
            RETURN p.email AS email, p.name AS name, coalesce(p.tracked, false) AS tracked
            """
        )
        return [dict(r) async for r in result]


def _resolve_owner_email(
    owner: str, roster: Roster, known_people: list[dict[str, Any]]
) -> str | None:
    """Canonical email for an action item's owner, or None.

    This is the fix for bug #1. The extractor writes display names, so matching
    on `"@" in owner` — which is what v5 did — resolves almost nothing and the
    ASSIGNED_TO edge never forms. Running the owner through the same resolver
    the attendees use turns a name into the canonical email the MERGE needs.

    Returns None when the owner cannot be resolved: no email is invented, the
    edge simply does not form, and the ActionItem still exists with its raw
    `owner` string intact for a human to read.
    """
    if not owner:
        return None
    resolution = person_resolver.resolve(
        Attendee(name=owner, email=owner if "@" in owner else None),
        roster,
        known_people=known_people,
    )
    return resolution.email if resolution.status == "resolved" else None


@with_retry(max_attempts=3, base_delay=1.0)
async def upsert_meeting_graph(
    meeting: ExtractedMeeting,
    source_id: str,
    *,
    driver: Any | None = None,
    roster: Roster | None = None,
    known_people: list[dict[str, Any]] | None = None,
) -> str:
    """MERGE a whole meeting into the graph in ONE transaction.

    Meeting, People, Organizations, Topics, Decisions and ActionItems all
    commit together or not at all (CLAUDE.md). Reads — resolving attendees —
    happen before the transaction opens.
    """
    now = datetime.now(UTC).isoformat()
    meeting_id = uuid5_id("meeting", source_id)

    driver = driver or get_driver()
    roster = roster if roster is not None else Roster([])
    if known_people is None:
        known_people = await get_known_people(driver)

    # Resolve attendees BEFORE the write: deterministic email normalisation and
    # roster first, fuzzy name match second. Unresolved attendees are held for
    # review, never silently dropped.
    resolved, reviews = person_resolver.resolve_attendees(
        meeting.attendees, roster, known_people=known_people
    )

    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            await tx.run(
                """
                MERGE (m:Meeting {id: $id})
                ON CREATE SET m.created_at = $now, m.relevance_weight = 1.0
                SET m.title = $title,
                    m.kind = $kind,
                    m.platform = $platform,
                    m.date = $date,
                    m.duration_minutes = $duration,
                    m.summary = $summary,
                    m.sentiment = $sentiment,
                    m.follow_up_needed = $follow_up,
                    m.confidence = $confidence,
                    m.source_id = $source_id,
                    m.updated_at = $now
                """,
                id=meeting_id,
                title=meeting.title,
                kind=meeting.kind,
                platform=meeting.platform,
                date=str(meeting.date),
                duration=meeting.duration_minutes,
                summary=meeting.summary,
                sentiment=meeting.sentiment,
                follow_up=meeting.follow_up_needed,
                confidence=meeting.confidence,
                source_id=source_id,
                now=now,
            )

            for res in resolved:
                email = res.email or ""
                person_id = uuid5_id("person", email)
                domain = email.split("@")[-1] if "@" in email else "unknown"
                org_id = uuid5_id("org", domain)

                await tx.run(
                    """
                    MERGE (p:Person {email: $email})
                    ON CREATE SET p.created_at = $now, p.tracked = $tracked
                    SET p.name = $name, p.id = $person_id, p.updated_at = $now,
                        p.tracked = CASE WHEN $tracked THEN true ELSE coalesce(p.tracked, false) END

                    MERGE (o:Organization {domain: $domain})
                    ON CREATE SET o.created_at = $now
                    SET o.id = $org_id, o.updated_at = $now

                    WITH p, o
                    MERGE (p)-[:WORKS_AT]->(o)

                    WITH p
                    MATCH (m:Meeting {id: $meeting_id})
                    MERGE (p)-[:ATTENDED {role: $role}]->(m)
                    """,
                    email=email,
                    name=res.name,
                    person_id=person_id,
                    tracked=res.tracked,
                    domain=domain,
                    org_id=org_id,
                    role=res.role,
                    meeting_id=meeting_id,
                    now=now,
                )

            # Unresolved attendees are HELD for review, never silently dropped.
            for rev in reviews:
                review_id = uuid5_id("person-review", f"{source_id}:{rev.name}:{rev.role}")
                await tx.run(
                    """
                    MERGE (r:PersonReview {id: $id})
                    ON CREATE SET r.created_at = $now
                    SET r.name = $name, r.role = $role, r.reason = $reason,
                        r.status = 'pending', r.updated_at = $now
                    WITH r
                    MATCH (m:Meeting {id: $meeting_id})
                    MERGE (m)-[:NEEDS_REVIEW]->(r)
                    """,
                    id=review_id,
                    name=rev.name,
                    role=rev.role,
                    reason=rev.reason,
                    meeting_id=meeting_id,
                    now=now,
                )

            # Topic MERGE key is normalised (lowercase + strip) to match the id's
            # normalisation. Using the raw-case name created a second Topic node
            # per case variant — with a colliding .id, since both hash to the same
            # uuid5 — fragmenting one real topic and understating it in every
            # insight query, which all key off these nodes.
            for topic_name in meeting.topics:
                norm_name = topic_name.lower().strip()
                await tx.run(
                    """
                    MERGE (t:Topic {name: $name})
                    ON CREATE SET t.created_at = $now
                    SET t.id = $topic_id, t.updated_at = $now

                    WITH t
                    MATCH (m:Meeting {id: $meeting_id})
                    MERGE (m)-[:DISCUSSED]->(t)
                    """,
                    name=norm_name,
                    topic_id=uuid5_id("topic", norm_name),
                    meeting_id=meeting_id,
                    now=now,
                )

            for i, decision in enumerate(meeting.decisions):
                await tx.run(
                    """
                    MERGE (d:Decision {id: $id})
                    ON CREATE SET d.created_at = $now
                    SET d.text = $text, d.confidence = $confidence, d.updated_at = $now

                    WITH d
                    MATCH (m:Meeting {id: $meeting_id})
                    MERGE (m)-[:PRODUCED]->(d)
                    """,
                    id=uuid5_id("decision", f"{source_id}:{i}"),
                    text=decision.text,
                    confidence=decision.confidence,
                    meeting_id=meeting_id,
                    now=now,
                )

            for i, action in enumerate(meeting.action_items):
                await tx.run(
                    """
                    MERGE (a:ActionItem {id: $id})
                    ON CREATE SET a.created_at = $now
                    SET a.task = $task,
                        a.owner = $owner,
                        a.due = $due,
                        a.done = $done,
                        a.priority = $priority,
                        a.is_engineering_task = $is_engineering_task,
                        a.confidence = $confidence,
                        a.updated_at = $now

                    WITH a
                    MATCH (m:Meeting {id: $meeting_id})
                    MERGE (m)-[:FOLLOWS_UP]->(a)

                    WITH a
                    OPTIONAL MATCH (p:Person {email: $owner_email})
                    FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (a)-[:ASSIGNED_TO]->(p)
                    )
                    """,
                    id=uuid5_id("action", f"{source_id}:{i}:{action.task}"),
                    task=action.task,
                    owner=action.owner,
                    due=str(action.due) if action.due else None,
                    done=action.done,
                    priority=action.priority,
                    is_engineering_task=action.is_engineering_task,
                    confidence=action.confidence,
                    meeting_id=meeting_id,
                    # Bug #1: resolved, not a naive "@" check on a display name.
                    owner_email=_resolve_owner_email(action.owner, roster, known_people),
                    now=now,
                )

            await tx.commit()

    log.info(
        "memgraph.meeting_upserted",
        meeting_id=meeting_id,
        title=meeting.title,
        attendees=len(meeting.attendees),
        reviews=len(reviews),
        topics=len(meeting.topics),
        actions=len(meeting.action_items),
    )
    return meeting_id


# ─── action / Jira helpers (consumed by jira_pusher and jira_sync in Phase 6) ──


async def update_action_jira_key(action_id: str, jira_key: str, driver: Any | None = None) -> None:
    driver = driver or get_driver()
    async with driver.session() as session:
        await session.run(
            "MATCH (a:ActionItem {id: $id}) SET a.jira_key = $key, a.jira_status = 'created'",
            id=action_id,
            key=jira_key,
        )


async def get_open_actions_for_owner(
    owner_email: str, *, exclude_id: str, driver: Any | None = None
) -> list[dict[str, Any]]:
    """Same-owner open items, the dedup candidate set jira_pusher scores against.

    `exclude_id` matters: by the time jira_pusher runs, upsert_meeting_graph
    has already written every action item in the meeting, including the one
    currently being evaluated. Without excluding it, an item can match itself
    at similarity 1.0 and link MENTIONED_IN to its own node (v5 excluded this
    for the same reason, via a.id <> $exclude_id).
    """
    driver = driver or get_driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:ActionItem)-[:ASSIGNED_TO]->(p:Person {email: $email})
            WHERE coalesce(a.done, false) = false AND a.id <> $exclude_id
            RETURN a.id AS id, a.task AS task, a.jira_key AS jira_key, a.embedding AS embedding
            """,
            email=owner_email,
            exclude_id=exclude_id,
        )
        return [dict(r) async for r in result]


async def link_action_mentioned_in(
    action_id: str, meeting_id: str, driver: Any | None = None
) -> None:
    """Recurring mention of an existing item — link it rather than duplicating."""
    driver = driver or get_driver()
    async with driver.session() as session:
        await session.run(
            """
            MATCH (a:ActionItem {id: $action_id})
            MATCH (m:Meeting {id: $meeting_id})
            MERGE (a)-[:MENTIONED_IN]->(m)
            """,
            action_id=action_id,
            meeting_id=meeting_id,
        )


async def mark_action_needs_review(action_id: str, reason: str, driver: Any | None = None) -> None:
    """Below JIRA_CONFIDENCE_THRESHOLD: write the node, create no ticket."""
    driver = driver or get_driver()
    async with driver.session() as session:
        await session.run(
            """
            MATCH (a:ActionItem {id: $id})
            SET a.jira_status = 'needs_review', a.review_reason = $reason
            """,
            id=action_id,
            reason=reason,
        )


async def get_action_confidence(action_id: str, driver: Any | None = None) -> float | None:
    driver = driver or get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:ActionItem {id: $id}) RETURN a.confidence AS confidence", id=action_id
        )
        async for record in result:
            value = record["confidence"]
            return float(value) if value is not None else None
        return None


async def update_action_jira_status(
    jira_key: str, status: str, done: bool, driver: Any | None = None
) -> bool:
    """Jira status syncing back into the graph. Returns whether a node matched.

    Derived from the write summary's counters rather than guessed — jira_sync
    needs to know whether this key existed in the graph so its matched/
    unmatched batch counters mean something. A silent no-op used to be
    reported as a match in an earlier draft of this file; a Jira ticket
    created outside this pipeline is real signal, not a bug, and jira_sync's
    caller should be able to tell the two apart.
    """
    driver = driver or get_driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:ActionItem {jira_key: $key})
            SET a.jira_status = $status, a.done = $done
            """,
            key=jira_key,
            status=status,
            done=done,
        )
        summary = await result.consume()
        return bool(summary.counters.properties_set)


async def merge_blocker(
    meeting_id: str, text: str, raised_by: str | None = None, driver: Any | None = None
) -> str:
    """A blocker raised in a meeting. Deterministic id so re-processing MERGEs."""
    driver = driver or get_driver()
    blocker_id = uuid5_id("blocker", f"{meeting_id}:{text}")
    now = datetime.now(UTC).isoformat()
    async with driver.session() as session:
        await session.run(
            """
            MERGE (b:Blocker {id: $id})
            ON CREATE SET b.created_at = $now, b.status = 'open'
            SET b.text = $text, b.raised_by = $raised_by, b.updated_at = $now
            WITH b
            MATCH (m:Meeting {id: $meeting_id})
            MERGE (m)-[:RAISES_BLOCKER]->(b)
            """,
            id=blocker_id,
            text=text,
            raised_by=raised_by,
            meeting_id=meeting_id,
            now=now,
        )
    return blocker_id
