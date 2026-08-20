"""Vector memory — 768-dim semantic search over Meeting, Fact and ActionItem.

Owns the `embedding` property on those node types, the same way
`graph_algorithms` writes `pagerank_score` onto nodes it does not otherwise
own.

**Never issues a MAGE CALL.** Search goes through
`graph_algorithms.vector_search()`, keeping every CALL in that one module
(CLAUDE.md).

Embeddings come from `llm_client.embed`, which is the only module allowed to
construct an LLM client. v5 reached into the extractor's OpenAI singleton
directly; Phase 4's seam replaces that, so `fake` works offline here too.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from meeting_notes import graph_algorithms
from meeting_notes.config import Settings, get_settings

log = structlog.get_logger()

MEETING_INDEX = "meeting_embedding_idx"
FACT_INDEX = "fact_embedding_idx"


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


async def embed_text(
    text: str, *, settings: Settings | None = None, embed: Any = None
) -> list[float] | None:
    """Embed one string. Returns None rather than raising.

    Embedding is an enrichment step: a failure here must never block or roll
    back a meeting that has already been written to the graph.
    """
    if not text or not text.strip():
        return None

    if embed is None:
        from meeting_notes import llm_client

        embed = llm_client.embed

    try:
        vector: list[float] | None = await embed(text, settings=settings)
        return vector
    except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
        log.warning("vector.embed_failed", error=str(exc))
        return None


async def embed_meeting(
    meeting_id: str,
    summary: str,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    embed: Any = None,
) -> bool:
    """Embed a meeting's summary onto Meeting.embedding."""
    vector = await embed_text(summary, settings=settings, embed=embed)
    if vector is None:
        return False

    driver = driver or _driver()
    async with driver.session() as session:
        await session.run(
            """
            MATCH (m:Meeting {id: $meeting_id})
            SET m.embedding = $embedding, m.embedding_updated_at = $now
            """,
            meeting_id=meeting_id,
            embedding=vector,
            now=datetime.now(UTC).isoformat(),
        )
    log.info("vector.meeting_embedded", meeting_id=meeting_id)
    return True


async def _embed_pending(
    fetch_cypher: str,
    write_cypher: str,
    meeting_id: str,
    text_field: str,
    *,
    driver: Any,
    settings: Settings | None,
    embed: Any,
) -> int:
    """Embed rows that have no embedding yet. Idempotent by construction —
    the fetch filters on `embedding IS NULL`, so a MERGE-matched node from an
    earlier meeting is embedded once and not re-embedded on every ingestion.
    """
    async with driver.session() as session:
        result = await session.run(fetch_cypher, meeting_id=meeting_id)
        pending = [dict(r) async for r in result]

    now = datetime.now(UTC).isoformat()
    count = 0
    for row in pending:
        vector = await embed_text(row[text_field], settings=settings, embed=embed)
        if vector is None:
            continue
        async with driver.session() as session:
            await session.run(write_cypher, id=row["id"], embedding=vector, now=now)
        count += 1
    return count


async def embed_action_items_for_meeting(
    meeting_id: str, *, driver: Any = None, settings: Settings | None = None, embed: Any = None
) -> int:
    """Embed this meeting's un-embedded ActionItems — the dedup similarity input."""
    driver = driver or _driver()
    count = await _embed_pending(
        """
        MATCH (m:Meeting {id: $meeting_id})-[:FOLLOWS_UP]->(a:ActionItem)
        WHERE a.embedding IS NULL AND a.task IS NOT NULL
        RETURN a.id AS id, a.task AS task
        """,
        """
        MATCH (a:ActionItem {id: $id})
        SET a.embedding = $embedding, a.embedding_updated_at = $now
        """,
        meeting_id, "task", driver=driver, settings=settings, embed=embed,
    )
    if count:
        log.info("vector.actions_embedded", meeting_id=meeting_id, count=count)
    return count


async def embed_facts_for_meeting(
    meeting_id: str, *, driver: Any = None, settings: Settings | None = None, embed: Any = None
) -> int:
    """Embed Facts attached to this meeting that have no embedding yet."""
    driver = driver or _driver()
    count = await _embed_pending(
        """
        MATCH (m:Meeting {id: $meeting_id})-[:HAS_FACT]->(f:Fact)
        WHERE f.embedding IS NULL
        RETURN f.id AS id, f.text AS text
        """,
        """
        MATCH (f:Fact {id: $id})
        SET f.embedding = $embedding, f.embedding_updated_at = $now
        """,
        meeting_id, "text", driver=driver, settings=settings, embed=embed,
    )
    if count:
        log.info("vector.facts_embedded", meeting_id=meeting_id, count=count)
    return count


async def _search(
    index_name: str,
    hydrate_cypher: str,
    query_text: str,
    limit: int,
    *,
    driver: Any,
    settings: Settings | None,
    embed: Any,
    search: Any,
) -> list[dict[str, Any]]:
    vector = await embed_text(query_text, settings=settings, embed=embed)
    if vector is None:
        return []

    search = search or graph_algorithms.vector_search
    hits = await search(index_name, vector, limit, driver=driver)
    if not hits:
        return []

    async with driver.session() as session:
        result = await session.run(hydrate_cypher, ids=[h["node_id"] for h in hits])
        by_id = {r["id"]: dict(r) async for r in result}

    # Preserve the search's similarity ordering; drop hits whose node has since
    # been deleted rather than emitting a half-empty row.
    return [
        {**by_id[h["node_id"]], "similarity": h["similarity"]}
        for h in hits
        if h["node_id"] in by_id
    ]


async def search_similar_meetings(
    query_text: str,
    limit: int = 5,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    embed: Any = None,
    search: Any = None,
) -> list[dict[str, Any]]:
    """Semantic search over Meeting summaries."""
    settings = settings or get_settings()
    return await _search(
        MEETING_INDEX,
        """
        UNWIND $ids AS mid
        MATCH (m:Meeting {id: mid})
        RETURN m.id AS id, m.title AS title, m.date AS date,
               m.summary AS summary, m.kind AS kind
        """,
        query_text, limit,
        driver=driver or _driver(), settings=settings, embed=embed, search=search,
    )


async def search_similar_facts(
    query_text: str,
    limit: int = 5,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    embed: Any = None,
    search: Any = None,
) -> list[dict[str, Any]]:
    """Semantic search over Fact text."""
    settings = settings or get_settings()
    return await _search(
        FACT_INDEX,
        """
        UNWIND $ids AS fid
        MATCH (f:Fact {id: fid})
        RETURN f.id AS id, f.text AS text, f.confidence AS confidence
        """,
        query_text, limit,
        driver=driver or _driver(), settings=settings, embed=embed, search=search,
    )
