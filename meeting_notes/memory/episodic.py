"""Episodic memory — what happened, in what order, and what caused what.

Owns `MemorySession`, `PRECEDED_BY`, `CAUSED_BY` and `ACCESSED`, and issues
Cypher only for those (CLAUDE.md).

**`MemorySession` nodes are written here and nowhere else** — an explicit
CLAUDE.md rule, so `retrieval.py` calls `log_session()` rather than writing
the node itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.models import ExtractedMeeting
from meeting_notes.utils import uuid5_id

log = structlog.get_logger()

CAUSALITY_SYSTEM = (
    "You are analyzing whether a meeting was caused by a prior decision or meeting. "
    'Respond ONLY with JSON: {"references_prior": true|false, '
    '"reference_description": "string or null"}. '
    "Only say true if the summary explicitly references an earlier decision or discussion."
)

# A meeting links to at most one predecessor: the chain is a spine, not a mesh.
_MAX_CAUSAL_LINKS = 1


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


async def link_temporal_chain(
    meeting_id: str,
    meeting_date: str,
    attendee_emails: list[str],
    *,
    driver: Any = None,
) -> bool:
    """Link this meeting to the most recent prior one sharing an attendee.

    `gap_days` on the edge is what makes the chain useful — "these two
    happened three days apart" is the signal, not merely that they are
    ordered.
    """
    if not attendee_emails:
        return False

    driver = driver or _driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (current:Meeting {id: $meeting_id})
            MATCH (prev:Person)-[:ATTENDED]->(prior:Meeting)
            WHERE prev.email IN $emails
              AND prior.date < $meeting_date
              AND prior.id <> $meeting_id
            WITH current, prior ORDER BY prior.date DESC LIMIT 1
            MERGE (current)-[p:PRECEDED_BY]->(prior)
            ON CREATE SET p.gap_days = (date($meeting_date) - date(prior.date)).day,
                          p.created_at = $now
            RETURN prior.id AS prior_id
            """,
            meeting_id=meeting_id,
            emails=attendee_emails,
            meeting_date=meeting_date,
            now=datetime.now(UTC).isoformat(),
        )
        record = await result.single()

    if record is None:
        return False
    log.info("episodic.temporal_chain_linked", meeting_id=meeting_id, prior_id=record["prior_id"])
    return True


async def detect_causality(
    meeting: ExtractedMeeting,
    meeting_id: str,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    chat: Any = None,
) -> int:
    """Link this meeting to the prior Decision it follows up on.

    Only runs when `follow_up_needed` is set — the cheap gate before an LLM
    call, mirroring the classifier's role earlier in the pipeline.
    """
    if not meeting.follow_up_needed:
        return 0

    settings = settings or get_settings()
    if chat is None:
        from meeting_notes import llm_client

        chat = llm_client.chat_json

    try:
        parsed = await chat(CAUSALITY_SYSTEM, meeting.summary, temperature=0.0, settings=settings)
    except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
        log.warning("episodic.causality_failed", meeting_id=meeting_id, error=str(exc))
        return 0

    if not isinstance(parsed, dict) or not parsed.get("references_prior"):
        return 0
    description = parsed.get("reference_description")
    if not description:
        return 0

    driver = driver or _driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (d:Decision) RETURN d.id AS id, d.text AS text LIMIT 50"
        )
        candidates = [dict(r) async for r in result]

    best = _best_overlap(str(description), candidates)
    if best is None:
        return 0

    async with driver.session() as session:
        await session.run(
            """
            MATCH (m:Meeting {id: $meeting_id})
            MATCH (d:Decision {id: $decision_id})
            MERGE (m)-[c:CAUSED_BY]->(d)
            ON CREATE SET c.confidence = $confidence, c.created_at = $now
            """,
            meeting_id=meeting_id,
            decision_id=best["id"],
            confidence=round(best["score"], 3),
            now=datetime.now(UTC).isoformat(),
        )

    log.info(
        "episodic.causality_linked",
        meeting_id=meeting_id, decision_id=best["id"], confidence=round(best["score"], 3),
    )
    return _MAX_CAUSAL_LINKS


_STEM_LENGTH = 5


def _stems(text: str) -> set[str]:
    """Crude prefix stemming: significant words truncated to a common prefix.

    Exact word matching misses the morphological variants this comparison
    exists to catch -- a summary saying "the database migration" against a
    decision recorded as "migrate the database" shares only one exact word out
    of three (0.33) and would score below any sane threshold. Truncating to
    five characters makes migration/migrate and similar pairs agree, without
    pulling in a stemming dependency for one comparison.

    Words of three characters or fewer are dropped: they are almost all
    articles and prepositions, and they inflate the score without carrying
    meaning.
    """
    return {w[:_STEM_LENGTH] for w in text.lower().split() if len(w) > 3}


def _best_overlap(
    description: str, candidates: list[dict[str, Any]], threshold: float = 0.5
) -> dict[str, Any] | None:
    """Highest-overlap candidate above `threshold`, or None.

    Deliberately not an embedding comparison: this runs inside enrichment over
    at most 50 candidates, and a cheap lexical score keeps it off the LLM path.

    The threshold stays conservative on purpose. A missed link merely means no
    CAUSED_BY edge; a false one asserts a causal claim the graph will later
    present as fact, which is the more expensive error.
    """
    words = _stems(description)
    if not words:
        return None

    best, best_score = None, 0.0
    for candidate in candidates:
        candidate_words = _stems(candidate.get("text") or "")
        if not candidate_words:
            continue
        score = len(words & candidate_words) / len(words)
        if score > best_score:
            best, best_score = candidate, score

    return {**best, "score": best_score} if best and best_score >= threshold else None


async def decay_relevance(driver: Any = None) -> dict[str, int]:
    """Nightly: decay every meeting's relevance by 5%, floored at 0.1.

    The floor matters — decaying to zero would make old meetings invisible to
    ranking rather than merely less prominent, which is not what "stale"
    should mean.
    """
    driver = driver or _driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (m:Meeting)
            SET m.relevance_weight = CASE
                WHEN m.relevance_weight IS NULL THEN 1.0
                WHEN m.relevance_weight <= 0.1 THEN 0.1
                ELSE m.relevance_weight * 0.95
            END
            RETURN count(m) AS updated
            """
        )
        record = await result.single()
        updated = record["updated"] if record else 0

    log.info("episodic.decay_done", meetings_decayed=updated)
    return {"meetings_decayed": int(updated)}


async def log_session(
    query_text: str, answer_text: str, node_ids: list[str], *, driver: Any = None
) -> str:
    """Record one retrieval as a MemorySession with ACCESSED edges.

    The ONLY place MemorySession nodes are written (CLAUDE.md).
    """
    now = datetime.now(UTC).isoformat()
    session_id = uuid5_id("session", f"{now}{query_text}")

    driver = driver or _driver()
    async with driver.session() as session:
        await session.run(
            """
            MERGE (ms:MemorySession {id: $session_id})
            SET ms.query_text = $query_text,
                ms.answer_text = $answer_text,
                ms.nodes_accessed = $node_count,
                ms.created_at = $now
            """,
            session_id=session_id,
            query_text=query_text,
            answer_text=answer_text,
            node_count=len(node_ids),
            now=now,
        )
        if node_ids:
            await session.run(
                """
                MATCH (ms:MemorySession {id: $session_id})
                UNWIND $node_ids AS nid
                MATCH (n {id: nid})
                MERGE (ms)-[:ACCESSED]->(n)
                """,
                session_id=session_id,
                node_ids=node_ids,
            )

    log.info("episodic.session_logged", session_id=session_id, nodes=len(node_ids))
    return session_id
