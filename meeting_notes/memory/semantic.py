"""Semantic memory — durable facts, preferences, and relationship weights.

Owns `Fact`, `Preference`, `HAS_FACT`, `PREFERS`, `KNOWS` and `INTERESTED_IN`,
and issues Cypher only for those (CLAUDE.md's documented exception).

Facts are **corroborated, not just stored**: a fact MERGEs on its normalised
text, so the same fact observed in a second meeting lands on the same node and
raises its confidence (0.3 on create, +0.1 per re-observation, capped at 1.0).
That is what makes this memory rather than a log.

**One v5 bug is fixed here.** v5's `strengthen_relationships` matched
`Topic {name: $topic}` using the raw-cased topic straight off the extractor,
but the write path stores topic names lowercased and stripped (v5 commit
`dcbb2d2` fixed the write side and `get_topic_graph`'s read side — it never
touched this file). So any topic with capitals matched zero rows and the
`INTERESTED_IN` edge silently never formed. Verified against real v6 data:
all 61 stored Topic names are lowercase, while the extractor emits
"Budget Planning". Same class as MIGRATION bug #1 — a silent zero-edge.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.models import ExtractedMeeting
from meeting_notes.utils import strip_json_fences, uuid5_id

log = structlog.get_logger()

FACT_SYSTEM = (
    "Extract 3-5 durable facts from this meeting summary. "
    "A fact is something persistently true about a person, project, or topic — "
    "not a one-time event. Respond ONLY with a JSON array of strings. "
    'Example: ["Alice leads the backend team", "The API migration is Q3"]'
)

PREF_SYSTEM = (
    "Given this person's meeting history context, infer 1-2 preferences about how they work. "
    "Respond ONLY with a JSON array of objects: "
    '[{"category": "string", "value": "string"}]. '
    "Categories: communication_style, meeting_frequency, topic_interest, "
    "work_pattern, timezone_preference. Be specific, not generic."
)


def normalise_topic(name: str) -> str:
    """The Topic MERGE key: lowercased and stripped.

    Must match `graph_client.upsert_meeting_graph` exactly. Deriving it in one
    named place is deliberate — CLAUDE.md calls writer/reader key drift a
    known v5 bug class, and this function is the reader side of it.
    """
    return (name or "").lower().strip()


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


async def _chat(system: str, user: str, settings: Settings | None, chat: Any) -> Any:
    """Both prompts here ask for a JSON ARRAY, so this uses `chat_list`.

    Routing them through `chat_json` silently discarded every correct answer:
    the object parser rejects a bare array, so fact extraction produced ZERO
    facts across the whole corpus while the model was responding perfectly.
    Found in a live backfill log.
    """
    if chat is None:
        from meeting_notes import llm_client

        chat = llm_client.chat_list
    return await chat(system, user, temperature=0.0, settings=settings)


def _parse_list(raw: Any) -> list[Any]:
    """Tolerate a model returning a bare array, or an object wrapping one.

    `chat_json` promises a dict, but these prompts ask for a JSON *array*, so
    the seam's object-only parse returns None for a well-formed answer. Both
    shapes are accepted rather than discarding good output.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for value in raw.values():
            if isinstance(value, list):
                return value
    if isinstance(raw, str):
        try:
            parsed = json.loads(strip_json_fences(raw))
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


async def extract_facts(
    meeting: ExtractedMeeting,
    meeting_id: str,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    chat: Any = None,
) -> int:
    """Extract durable facts and MERGE them, raising confidence on re-observation."""
    settings = settings or get_settings()
    try:
        raw = await _chat(FACT_SYSTEM, meeting.summary, settings, chat)
        facts = _parse_list(raw)
    except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
        log.warning("semantic.extract_facts_failed", meeting_id=meeting_id, error=str(exc))
        return 0

    driver = driver or _driver()
    now = datetime.now(UTC).isoformat()
    count = 0

    async with driver.session() as session:
        for fact_text in facts:
            if not isinstance(fact_text, str) or not fact_text.strip():
                continue
            text = fact_text.strip()
            try:
                await session.run(
                    """
                    MERGE (f:Fact {id: $fact_id})
                    ON CREATE SET f.text = $text,
                                  f.confidence = 0.3,
                                  f.source_count = 1,
                                  f.created_at = $now
                    ON MATCH SET  f.source_count = f.source_count + 1,
                                  f.confidence = CASE
                                      WHEN f.confidence + 0.1 > 1.0 THEN 1.0
                                      ELSE f.confidence + 0.1
                                  END,
                                  f.updated_at = $now
                    WITH f
                    MATCH (m:Meeting {id: $meeting_id})
                    MERGE (m)-[:HAS_FACT]->(f)
                    """,
                    fact_id=uuid5_id("fact", text.lower()),
                    text=text,
                    now=now,
                    meeting_id=meeting_id,
                )
                count += 1
            except Exception as exc:  # noqa: BLE001 - one bad fact must not sink the rest
                log.warning("semantic.fact_write_failed", error=str(exc))

    log.info("semantic.facts_extracted", meeting_id=meeting_id, count=count)
    return count


async def strengthen_relationships(
    meeting: ExtractedMeeting, meeting_id: str, *, driver: Any = None
) -> None:
    """Strengthen KNOWS and INTERESTED_IN weights. Pure Cypher, no LLM call."""
    emails = [a.email for a in meeting.attendees if a.email]
    if not emails:
        return

    driver = driver or _driver()
    now = datetime.now(UTC).isoformat()

    async with driver.session() as session:
        # KNOWS: every co-attendee pair, once each (email1 < email2).
        await session.run(
            """
            UNWIND $emails AS email1
            UNWIND $emails AS email2
            WITH email1, email2 WHERE email1 < email2
            MATCH (p1:Person {email: email1}), (p2:Person {email: email2})
            MERGE (p1)-[k:KNOWS]->(p2)
            ON CREATE SET k.weight = 1, k.created_at = $now
            ON MATCH SET  k.weight = k.weight + 1, k.updated_at = $now
            """,
            emails=emails,
            now=now,
        )

        for topic_name in meeting.topics:
            await session.run(
                """
                UNWIND $emails AS email
                MATCH (p:Person {email: email}), (t:Topic {name: $topic})
                MERGE (p)-[i:INTERESTED_IN]->(t)
                ON CREATE SET i.weight = 1, i.created_at = $now
                ON MATCH SET  i.weight = i.weight + 1, i.updated_at = $now
                """,
                emails=emails,
                # Normalised, matching the write path. Raw case here matched
                # zero rows in v5 and the edge silently never formed.
                topic=normalise_topic(topic_name),
                now=now,
            )

    log.info(
        "semantic.relationships_strengthened",
        meeting_id=meeting_id,
        pairs=len(emails) * (len(emails) - 1) // 2,
        topics=len(meeting.topics),
    )


async def consolidate(driver: Any = None) -> dict[str, int]:
    """Nightly: raise confidence on well-corroborated facts."""
    driver = driver or _driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:Fact)
            WHERE f.source_count % 3 = 0 AND f.confidence < 1.0
            SET f.confidence = CASE
                WHEN f.confidence + 0.2 > 1.0 THEN 1.0
                ELSE f.confidence + 0.2
            END
            RETURN count(f) AS boosted
            """
        )
        record = await result.single()
        boosted = record["boosted"] if record else 0

    log.info("semantic.consolidate_done", facts_boosted=boosted)
    return {"facts_boosted": int(boosted)}


async def _consolidate_one(
    person: dict[str, Any],
    driver: Any,
    settings: Settings | None,
    chat: Any,
    *,
    history: int,
    now: str,
) -> int:
    """Infer and write one person's preferences. Returns how many were written.

    Every failure here is contained to this person on purpose: a batch pass
    over 25 people must not lose 24 of them because one had a malformed reply
    or a write hiccup.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[:ATTENDED]->(m:Meeting)
            RETURN m.title AS title, coalesce(m.summary, '') AS summary
            ORDER BY m.date DESC
            LIMIT $history
            """,
            email=person["email"],
            history=history,
        )
        recent = [dict(r) async for r in result]

    if not recent:
        return 0

    context = f"Person: {person['name']} <{person['email']}>\n" + "\n".join(
        f"- {r['title']}: {r['summary'][:180]}" for r in recent
    )
    try:
        prefs = _parse_list(await _chat(PREF_SYSTEM, context, settings, chat))
    except Exception as exc:  # noqa: BLE001 - one person must not sink the pass
        log.warning("semantic.preferences_failed", email=person["email"], error=str(exc))
        return 0

    written = 0
    async with driver.session() as session:
        for pref in prefs:
            if not isinstance(pref, dict):
                continue
            category, value = pref.get("category"), pref.get("value")
            if not category or not value:
                continue
            try:
                await session.run(
                    """
                    MATCH (p:Person {email: $email})
                    MERGE (pref:Preference {id: $pref_id})
                    ON CREATE SET pref.category = $category, pref.created_at = $now
                    SET pref.value = $value, pref.updated_at = $now
                    MERGE (p)-[:PREFERS]->(pref)
                    """,
                    email=person["email"],
                    pref_id=uuid5_id("preference", f"{person['email']}:{category}"),
                    category=category,
                    value=value,
                    now=now,
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("semantic.preference_write_failed", error=str(exc))
    return written


async def consolidate_preferences(
    driver: Any = None,
    *,
    settings: Settings | None = None,
    chat: Any = None,
    max_people: int = 25,
    history: int = 12,
) -> dict[str, int]:
    """Nightly: infer working preferences once per person, from their history.

    A per-meeting version was removed: it was the wrong granularity — it
    would spend one LLM call per attendee per meeting to re-derive the same
    stable traits, and "how this person likes to work" is not a per-meeting
    property anyway. This runs once per person over their recent meetings.

    (It was also never wired to anything, so the Preference layer sat empty
    while the rest of semantic memory filled up.)
    """
    settings = settings or get_settings()
    driver = driver or _driver()
    now = datetime.now(UTC).isoformat()

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Person)-[:ATTENDED]->(m:Meeting)
            WITH p, count(m) AS meetings
            WHERE meetings >= 2
            RETURN p.email AS email, p.name AS name, meetings
            ORDER BY meetings DESC
            LIMIT $max_people
            """,
            max_people=max_people,
        )
        people = [dict(r) async for r in result]

    written = 0
    for person in people:
        written += await _consolidate_one(
            person, driver, settings, chat, history=history, now=now
        )

    log.info("semantic.preferences_consolidated", people=len(people), written=written)
    return {"people": len(people), "preferences": written}
