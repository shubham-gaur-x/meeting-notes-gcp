"""Memory retrieval — natural-language questions answered from the graph.

**Query-time only.** `pipeline.py` must never import this (CLAUDE.md): the
pipeline writes memory, retrieval reads it, and mixing the two would put an
LLM synthesis call on the ingestion path.

Reads only. The one side effect is logging a `MemorySession`, which is
delegated to `episodic.log_session` because that module owns the node type.

Two governance rules are enforced here rather than assumed:

* **`Person.tracked` gates per-person analytics.** Aggregates are the default;
  naming individuals is opt-in (CLAUDE.md).
* **`FACT_MIN_CONFIDENCE` applies at read time.** Facts seed at 0.3 and gain
  0.1 per corroboration, so an unfiltered read surfaces one-off noise at the
  same weight as a fact repeated across many meetings. This is a
  retrieval-quality floor, not a side-effect gate — unlike an ActionItem,
  a Fact has no ticket to block.
"""

from __future__ import annotations

from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.memory import episodic

log = structlog.get_logger()

ENTITY_SYSTEM = (
    "Extract entities from this question. Respond ONLY with JSON: "
    '{"people": ["name"], "topics": ["keyword"], "date_hint": "string or null"} '
    "Be conservative — only extract clearly named entities."
)

SYNTHESIS_SYSTEM_PREFIX = (
    "You are a meeting memory assistant with access to a structured knowledge graph. "
    "Answer the question using ONLY the context below. "
    "Be specific and cite names and dates when available. "
    "If the context does not contain enough information, say so — do not guess.\n"
    # The shape is pinned because the Vertex and Gemini backends set
    # responseMimeType=application/json, so the model MUST return JSON. Without
    # naming the key it invents its own nested structure and the caller ends up
    # stringifying a dict into the answer field -- observed live against real
    # graph data before this line existed.
    'Respond ONLY with JSON of exactly this shape: {"answer": "your prose answer here"}. '
    "The answer value must be plain readable prose, not nested objects or lists.\n"
    "Context: "
)

NO_CONTEXT_ANSWER = (
    "I don't have anything in memory that answers that. "
    "Nothing in the graph matched the question."
)


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


async def _chat(system: str, user: str, settings: Settings | None, chat: Any) -> Any:
    if chat is None:
        from meeting_notes import llm_client

        chat = llm_client.chat_json
    return await chat(system, user, temperature=0.0, settings=settings)


async def extract_entities(
    question: str, *, settings: Settings | None = None, chat: Any = None
) -> dict[str, Any]:
    """Pull people/topics/date hints out of a question."""
    try:
        parsed = await _chat(ENTITY_SYSTEM, question, settings, chat)
    except Exception as exc:  # noqa: BLE001 - a failed parse degrades to no entities
        log.warning("retrieval.entity_extraction_failed", error=str(exc))
        return {"people": [], "topics": [], "date_hint": None}

    if not isinstance(parsed, dict):
        return {"people": [], "topics": [], "date_hint": None}
    return {
        "people": parsed.get("people") or [],
        "topics": parsed.get("topics") or [],
        "date_hint": parsed.get("date_hint"),
    }


async def assemble_context(
    entities: dict[str, Any],
    question: str,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    search_meetings: Any = None,
) -> tuple[list[str], list[str]]:
    """Gather graph context for a question. Returns (context_lines, node_ids)."""
    settings = settings or get_settings()
    driver = driver or _driver()
    lines: list[str] = []
    node_ids: list[str] = []

    people = [p for p in entities.get("people", []) if isinstance(p, str)]
    topics = [t.lower().strip() for t in entities.get("topics", []) if isinstance(t, str)]

    async with driver.session() as session:
        if people:
            result = await session.run(
                """
                UNWIND $names AS name
                MATCH (p:Person)
                WHERE toLower(p.name) CONTAINS toLower(name)
                   OR toLower(p.email) CONTAINS toLower(name)
                RETURN DISTINCT p.id AS id, p.name AS name, p.email AS email
                LIMIT 10
                """,
                names=people,
            )
            async for record in result:
                node_ids.append(record["id"])
                lines.append(f"Person: {record['name']} <{record['email']}>")

        if topics:
            result = await session.run(
                """
                UNWIND $topics AS topic
                MATCH (t:Topic)<-[:DISCUSSED]-(m:Meeting)
                WHERE t.name CONTAINS topic
                RETURN DISTINCT m.id AS id, m.title AS title, m.date AS date,
                                m.summary AS summary
                ORDER BY m.date DESC
                LIMIT 10
                """,
                topics=topics,
            )
            async for record in result:
                node_ids.append(record["id"])
                lines.append(
                    f"Meeting ({record['date']}): {record['title']} — {record['summary']}"
                )

        result = await session.run(
            """
            MATCH (f:Fact)
            WHERE f.confidence >= $min_confidence
            RETURN f.id AS id, f.text AS text, f.confidence AS confidence
            ORDER BY f.confidence DESC
            LIMIT 10
            """,
            min_confidence=settings.fact_min_confidence,
        )
        async for record in result:
            node_ids.append(record["id"])
            lines.append(f"Fact (confidence {record['confidence']}): {record['text']}")

    # Semantic search as a fallback: a question sharing no keywords with any
    # meeting still finds the right one by meaning. This is the mechanism
    # behind the "zero keyword overlap" exit criterion.
    if not lines and search_meetings is not None:
        for hit in await search_meetings(question, limit=5, driver=driver, settings=settings):
            node_ids.append(hit["id"])
            lines.append(f"Meeting ({hit.get('date')}): {hit.get('title')} — {hit.get('summary')}")

    return lines, node_ids


async def full_memory_query(
    question: str,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    chat: Any = None,
    search_meetings: Any = None,
    log_session: bool = True,
) -> dict[str, Any]:
    """Answer a natural-language question from the graph.

    Returns the answer plus the node ids that contributed, so the caller can
    show its working rather than presenting an unsourced assertion.
    """
    settings = settings or get_settings()
    driver = driver or _driver()

    entities = await extract_entities(question, settings=settings, chat=chat)
    lines, node_ids = await assemble_context(
        entities, question, driver=driver, settings=settings, search_meetings=search_meetings
    )

    if not lines:
        # Honest emptiness beats a confident guess: the whole point of a
        # memory system is that its answers are grounded.
        return {"question": question, "answer": NO_CONTEXT_ANSWER, "node_ids": [], "entities": entities}

    context = "\n".join(lines)
    try:
        parsed = await _chat(f"{SYNTHESIS_SYSTEM_PREFIX}{context}", question, settings, chat)
        answer = (
            parsed.get("answer")
            if isinstance(parsed, dict) and parsed.get("answer")
            else str(parsed)
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("retrieval.synthesis_failed", error=str(exc))
        answer = NO_CONTEXT_ANSWER

    if log_session:
        try:
            await episodic.log_session(question, str(answer), node_ids, driver=driver)
        except Exception as exc:  # noqa: BLE001 - logging must not fail the answer
            log.warning("retrieval.session_log_failed", error=str(exc))

    return {
        "question": question,
        "answer": answer,
        "node_ids": node_ids,
        "entities": entities,
    }


async def person_memory_profile(
    email: str, *, driver: Any = None, settings: Settings | None = None
) -> dict[str, Any]:
    """Everything the graph remembers about one person. No LLM call.

    Returns {} when the person is not found, and **{} when they are not
    tracked** — per-person analytics are opt-in (CLAUDE.md).
    """
    settings = settings or get_settings()
    driver = driver or _driver()

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Person {email: $email})
            RETURN p.id AS id, p.name AS name, p.email AS email,
                   coalesce(p.tracked, false) AS tracked,
                   p.pagerank_score AS pagerank_score,
                   p.community_id AS community_id,
                   p.betweenness_centrality AS betweenness_centrality,
                   p.degree_centrality AS degree_centrality
            """,
            email=email,
        )
        records = [dict(r) async for r in result]
        if not records:
            return {}

        profile = records[0]
        if not profile.get("tracked"):
            log.info("retrieval.profile_withheld_untracked", email=email)
            return {}

        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[:ATTENDED]->(m:Meeting)-[:HAS_FACT]->(f:Fact)
            WHERE f.confidence >= $min_confidence
            RETURN DISTINCT f.id AS id, f.text AS text,
                            f.confidence AS confidence, f.source_count AS source_count
            ORDER BY f.confidence DESC
            LIMIT 10
            """,
            email=email,
            min_confidence=settings.fact_min_confidence,
        )
        profile["facts"] = [dict(r) async for r in result]

        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[:PREFERS]->(pref:Preference)
            RETURN pref.id AS id, pref.category AS category, pref.value AS value
            """,
            email=email,
        )
        profile["preferences"] = [dict(r) async for r in result]

        # KNOWS is stored in one canonical direction (lexicographically ordered
        # emails), so this must match either direction or half the edges vanish.
        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[k:KNOWS]-(other:Person)
            RETURN other.name AS name, other.email AS email, k.weight AS weight
            ORDER BY k.weight DESC
            LIMIT 10
            """,
            email=email,
        )
        profile["knows"] = [dict(r) async for r in result]

        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[i:INTERESTED_IN]->(t:Topic)
            RETURN t.name AS name, i.weight AS weight
            ORDER BY i.weight DESC
            LIMIT 10
            """,
            email=email,
        )
        profile["interests"] = [dict(r) async for r in result]

    return profile
