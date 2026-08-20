"""Procedural memory — recognising the recurring shapes of meetings.

Owns `Procedure`, `ProcedureStep`, `FOLLOWS_PROCEDURE`, `HAS_STEP` and
`NEXT_STEP`, and issues Cypher only for those (CLAUDE.md).

Pattern matching is deliberately pure Python: no LLM, no Cypher, so it is
deterministic and cheap enough to run on every processed meeting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from meeting_notes.models import ExtractedMeeting
from meeting_notes.utils import uuid5_id

log = structlog.get_logger()

MATCH_CONFIDENCE = 0.8

KNOWN_PROCEDURE_PATTERNS: dict[str, dict[str, Any]] = {
    "sprint_planning": {
        "kind": ["meeting"],
        "min_attendees": 3,
        "topic_keywords": ["sprint", "backlog", "velocity", "story points", "standup"],
    },
    "client_review": {
        "topic_keywords": ["client", "demo", "feedback", "presentation", "review"],
        "requires_multi_org": True,
    },
    "one_on_one": {"max_attendees": 2, "min_attendees": 2},
    "incident_response": {
        "topic_keywords": ["incident", "outage", "bug", "hotfix", "urgent", "down", "p0", "p1"],
    },
    "project_kickoff": {
        "topic_keywords": ["kickoff", "onboarding", "new project", "launch", "initiation"],
    },
    "retrospective": {
        "topic_keywords": ["retro", "retrospective", "what went well", "improvements", "lessons"],
    },
}


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


def matches_pattern(meeting: ExtractedMeeting, pattern: dict[str, Any]) -> bool:
    """Does this meeting fit one procedure pattern? Pure, synchronous, testable."""
    topics_lower = [t.lower() for t in meeting.topics]
    attendee_count = len(meeting.attendees)

    if "kind" in pattern and meeting.kind not in pattern["kind"]:
        return False
    if "min_attendees" in pattern and attendee_count < pattern["min_attendees"]:
        return False
    if "max_attendees" in pattern and attendee_count > pattern["max_attendees"]:
        return False

    if "topic_keywords" in pattern:
        if not any(
            keyword in topic for keyword in pattern["topic_keywords"] for topic in topics_lower
        ):
            return False

    if pattern.get("requires_multi_org"):
        domains = {
            a.email.split("@")[-1]
            for a in meeting.attendees
            if a.email and "@" in a.email
        }
        if len(domains) < 2:
            return False

    return True


async def match_to_procedure(
    meeting: ExtractedMeeting, meeting_id: str, *, driver: Any = None
) -> list[str]:
    """Link this meeting to every procedure pattern it matches."""
    driver = driver or _driver()
    now = datetime.now(UTC).isoformat()
    matched: list[str] = []

    for name, pattern in KNOWN_PROCEDURE_PATTERNS.items():
        if not matches_pattern(meeting, pattern):
            continue
        try:
            async with driver.session() as session:
                await session.run(
                    """
                    MATCH (m:Meeting {id: $meeting_id})
                    MERGE (p:Procedure {id: $proc_id})
                    ON CREATE SET p.name = $name,
                                  p.occurrence_count = 1,
                                  p.created_at = $now
                    ON MATCH SET  p.occurrence_count = p.occurrence_count + 1,
                                  p.updated_at = $now
                    MERGE (m)-[f:FOLLOWS_PROCEDURE]->(p)
                    ON CREATE SET f.confidence = $confidence, f.created_at = $now
                    """,
                    meeting_id=meeting_id,
                    proc_id=uuid5_id("procedure", name),
                    name=name,
                    confidence=MATCH_CONFIDENCE,
                    now=now,
                )
            matched.append(name)
        except Exception as exc:  # noqa: BLE001 - one bad match must not sink the rest
            log.warning("procedural.match_write_failed", procedure=name, error=str(exc))

    if matched:
        log.info("procedural.matched", meeting_id=meeting_id, procedures=matched)
    return matched


async def discover_procedures(
    *, driver: Any = None, min_occurrences: int = 3, similarity_threshold: float = 0.5
) -> dict[str, Any]:
    """Nightly: promote frequently co-occurring meeting shapes to Procedures.

    Uses `graph_algorithms.get_jaccard_similarity` rather than a MAGE CALL
    directly, keeping every CALL in that module.
    """
    from meeting_notes import graph_algorithms

    driver = driver or _driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Procedure)<-[:FOLLOWS_PROCEDURE]-(m:Meeting)
            WITH p, collect(m.id) AS meeting_ids, count(m) AS n
            WHERE n >= $min_occurrences
            RETURN p.id AS id, p.name AS name, meeting_ids, n
            """,
            min_occurrences=min_occurrences,
        )
        established = [dict(r) async for r in result]

    scored = 0
    for procedure in established:
        ids = procedure["meeting_ids"][:2]
        if len(ids) < 2:
            continue
        similarity = await graph_algorithms.get_jaccard_similarity(
            ids[0], ids[1], driver=driver
        )
        if similarity >= similarity_threshold:
            scored += 1

    log.info(
        "procedural.discovery_done",
        established=len(established), coherent=scored,
    )
    return {"established": len(established), "coherent": scored}
