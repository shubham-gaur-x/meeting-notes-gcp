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

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from meeting_notes import graph_algorithms
from meeting_notes.config import Settings, get_settings

log = structlog.get_logger()

MEETING_INDEX = "meeting_embedding_idx"
FACT_INDEX = "fact_embedding_idx"
CHUNK_INDEX = "chunk_embedding_idx"


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


def _format_entity_sections(
    attendees: list[str] | None,
    topics: list[str] | None,
    decisions: list[str] | None,
    actions: list[str] | None,
) -> list[str]:
    parts: list[str] = []
    if attendees:
        clean_names = [n.strip() for n in attendees if n and n.strip()]
        if clean_names:
            parts.append(f"Attendees: {', '.join(clean_names)}")
    if topics:
        clean_topics = [t.strip() for t in topics if t and t.strip()]
        if clean_topics:
            parts.append(f"Topics: {', '.join(clean_topics)}")
    if decisions:
        clean_decisions = [d.strip() for d in decisions if d and d.strip()]
        if clean_decisions:
            parts.append(f"Decisions: {'; '.join(clean_decisions)}")
    if actions:
        clean_actions = [a.strip() for a in actions if a and a.strip()]
        if clean_actions:
            parts.append(f"Action Items: {'; '.join(clean_actions)}")
    return parts


def format_meeting_chunk(
    *,
    title: str = "",
    original_title: str | None = None,
    attendees: list[str] | None = None,
    topics: list[str] | None = None,
    decisions: list[str] | None = None,
    actions: list[str] | None = None,
    summary: str = "",
    date: str | None = None,
    platform: str | None = None,
) -> str:
    """Format a comprehensive, structured text chunk for a meeting.

    Guarantees that all critical entity context — attendee names, extracted
    meeting title, original source title, topics, decisions, actions, and
    summary — is embedded together in the vector representation.
    """
    parts: list[str] = []
    if title:
        parts.append(f"Meeting Title: {title}")
    if original_title and original_title != title:
        parts.append(f"Original Title: {original_title}")
    meta = []
    if date:
        meta.append(f"Date: {date}")
    if platform:
        meta.append(f"Platform: {platform}")
    if meta:
        parts.append(" | ".join(meta))

    parts.extend(_format_entity_sections(attendees, topics, decisions, actions))

    if summary:
        parts.append(f"Summary: {summary.strip()}")

    return "\n".join(parts)


def _slice_body_text(
    body_text: str, step: int, overlap_chars: int, context_header: str
) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(body_text):
        end = min(start + step, len(body_text))
        if end < len(body_text):
            break_pt = body_text.rfind("\n", start, end)
            if break_pt > start + 100:
                end = break_pt
            else:
                space_pt = body_text.rfind(" ", start, end)
                if space_pt > start + 100:
                    end = space_pt
        segment = body_text[start:end].strip()
        if segment:
            prefix = f"[{context_header}]\n\n" if context_header else ""
            chunks.append(f"{prefix}{segment}")
        if end >= len(body_text):
            break
        start = end - overlap_chars
        if start < 0 or start >= end:
            start = end
    return chunks


def _build_chunk_header(
    title: str,
    original_title: str | None,
    date: str | None,
    attendees: list[str] | None,
    topics: list[str] | None,
) -> str:
    header_parts: list[str] = []
    if title:
        header_parts.append(f"Meeting: {title}")
    if original_title and original_title != title:
        header_parts.append(f"Original: {original_title}")
    if date:
        header_parts.append(f"Date: {date}")
    if attendees:
        clean_names = [n.strip() for n in attendees if n and n.strip()]
        if clean_names:
            header_parts.append(f"Attendees: {', '.join(clean_names)}")
    if topics:
        clean_topics = [t.strip() for t in topics if t and t.strip()]
        if clean_topics:
            header_parts.append(f"Topics: {', '.join(clean_topics)}")
    return " | ".join(header_parts)


def chunk_meeting_content(
    *,
    title: str = "",
    original_title: str | None = None,
    attendees: list[str] | None = None,
    topics: list[str] | None = None,
    decisions: list[str] | None = None,
    actions: list[str] | None = None,
    summary: str = "",
    date: str | None = None,
    platform: str | None = None,
    max_chunk_chars: int = 1500,
    overlap_chars: int = 200,
) -> list[str]:
    """Break meeting content into structured chunks.

    Every chunk is guaranteed to retain the entity context header:
    meeting title, original source title, attendee names, and topics.
    """
    context_header = _build_chunk_header(title, original_title, date, attendees, topics)

    full_chunk = format_meeting_chunk(
        title=title,
        original_title=original_title,
        attendees=attendees,
        topics=topics,
        decisions=decisions,
        actions=actions,
        summary=summary,
        date=date,
        platform=platform,
    )

    if not full_chunk.strip():
        return []

    if len(full_chunk) <= max_chunk_chars:
        return [full_chunk]

    body_parts = []
    if decisions:
        body_parts.append("Decisions:\n" + "\n".join(f"- {d}" for d in decisions if d))
    if actions:
        body_parts.append("Action Items:\n" + "\n".join(f"- {a}" for a in actions if a))
    if summary:
        body_parts.append(f"Summary:\n{summary}")

    body_text = "\n\n".join(body_parts)
    step = max(200, max_chunk_chars - len(context_header) - 50)

    sliced = _slice_body_text(body_text, step, overlap_chars, context_header)
    return sliced if sliced else [full_chunk]


def format_action_item_chunk(
    task: str,
    *,
    owner: str | None = None,
    meeting_title: str | None = None,
    original_title: str | None = None,
) -> str:
    """Format an action item into an entity-rich chunk."""
    parts = [f"Action Item: {task}"]
    if owner:
        parts.append(f"Assignee: {owner}")
    if meeting_title:
        parts.append(f"Meeting: {meeting_title}")
    if original_title and original_title != meeting_title:
        parts.append(f"Source: {original_title}")
    return " | ".join(parts)


def format_fact_chunk(
    text: str,
    *,
    meeting_title: str | None = None,
    original_title: str | None = None,
) -> str:
    """Format a fact into an entity-rich chunk."""
    parts = [f"Fact: {text}"]
    if meeting_title:
        parts.append(f"Meeting: {meeting_title}")
    if original_title and original_title != meeting_title:
        parts.append(f"Source: {original_title}")
    return " | ".join(parts)


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


def _extract_meeting_fields(
    meeting: Any,
    title: str | None,
    original_title: str | None,
    attendees: list[str] | None,
    topics: list[str] | None,
    decisions: list[str] | None,
    actions: list[str] | None,
    summary: str | None,
) -> tuple[
    str | None,
    str | None,
    list[str] | None,
    list[str] | None,
    list[str] | None,
    list[str] | None,
    str,
]:
    t = title or getattr(meeting, "title", None)
    ot = original_title or getattr(meeting, "original_title", None)
    if attendees is None:
        att_list = getattr(meeting, "attendees", []) or []
        attendees = [a.name for a in att_list if getattr(a, "name", None)]
    if topics is None:
        topics = getattr(meeting, "topics", None)
    if decisions is None:
        dec_list = getattr(meeting, "decisions", []) or []
        decisions = [d.text for d in dec_list if getattr(d, "text", None)]
    if actions is None:
        act_list = getattr(meeting, "action_items", []) or []
        actions = [
            f"{a.owner}: {a.task}" if getattr(a, "owner", None) else a.task
            for a in act_list
            if getattr(a, "task", None)
        ]
    s = summary or getattr(meeting, "summary", "") or ""
    return t, ot, attendees, topics, decisions, actions, s


async def _hydrate_from_graph(
    driver: Any, meeting_id: str
) -> dict[str, Any]:
    try:
        async with driver.session() as session:
            res = await session.run(
                """
                MATCH (m:Meeting {id: $meeting_id})
                OPTIONAL MATCH (p:Person)-[:ATTENDED]->(m)
                OPTIONAL MATCH (m)-[:DISCUSSED]->(t:Topic)
                OPTIONAL MATCH (m)-[:PRODUCED]->(d:Decision)
                OPTIONAL MATCH (m)-[:FOLLOWS_UP]->(a:ActionItem)
                RETURN m.title AS title, m.original_title AS original_title,
                       m.summary AS summary, m.date AS date, m.platform AS platform,
                       collect(DISTINCT p.name) AS attendees,
                       collect(DISTINCT t.name) AS topics,
                       collect(DISTINCT d.text) AS decisions,
                       collect(
                           DISTINCT CASE WHEN a.owner IS NOT NULL
                           THEN a.owner + ': ' + a.task ELSE a.task END
                       ) AS actions
                """,
                meeting_id=meeting_id,
            )
            row = await res.single()
            return dict(row) if row else {}
    except Exception as exc:  # noqa: BLE001
        log.debug("vector.hydrate_meeting_failed", error=str(exc))
        return {}


async def _persist_meeting_chunks(
    driver: Any,
    meeting_id: str,
    chunks: list[str],
    vector: list[float],
    settings: Settings | None,
    embed: Any,
    now: str,
) -> None:
    for idx, chunk_text in enumerate(chunks):
        chunk_id = f"{meeting_id}_chunk_{idx}"
        c_vector: list[float] | None = (
            vector if idx == 0 else await embed_text(chunk_text, settings=settings, embed=embed)
        )
        if c_vector is not None:
            try:
                async with driver.session() as session:
                    await session.run(
                        """
                        MERGE (c:Chunk {id: $chunk_id})
                        SET c.meeting_id = $meeting_id,
                            c.chunk_index = $idx,
                            c.text = $text,
                            c.embedding = $embedding,
                            c.updated_at = $now
                        WITH c
                        MATCH (m:Meeting {id: $meeting_id})
                        MERGE (m)-[:HAS_CHUNK]->(c)
                        """,
                        chunk_id=chunk_id,
                        meeting_id=meeting_id,
                        idx=idx,
                        text=chunk_text,
                        embedding=c_vector,
                        now=now,
                    )
            except Exception as exc:  # noqa: BLE001
                log.debug("vector.chunk_write_failed", error=str(exc))


async def embed_meeting(
    meeting_id: str,
    summary: str | Any = None,
    *,
    meeting: Any = None,
    title: str | None = None,
    original_title: str | None = None,
    attendees: list[str] | None = None,
    topics: list[str] | None = None,
    decisions: list[str] | None = None,
    actions: list[str] | None = None,
    date: str | None = None,
    platform: str | None = None,
    driver: Any = None,
    settings: Settings | None = None,
    embed: Any = None,
) -> bool:
    """Embed a meeting and its structured chunks onto Meeting and Chunk nodes."""
    # 1. Resolve meeting object if passed as first argument
    if summary is not None and not isinstance(summary, str) and meeting is None:
        meeting = summary
        summary = None

    # 2. Extract fields from meeting object if present
    if meeting is not None:
        title, original_title, attendees, topics, decisions, actions, summary = _extract_meeting_fields(
            meeting, title, original_title, attendees, topics, decisions, actions, summary
        )

    # 3. If caller gave no metadata and no meeting object, hydrate from Memgraph.
    driver_to_use = driver or _driver()
    if title is None and meeting is None and (summary is None or summary == ""):
        row = await _hydrate_from_graph(driver_to_use, meeting_id)
        if row.get("title"):
            title = title or row.get("title")
            original_title = original_title or row.get("original_title")
            attendees = attendees or [n for n in row.get("attendees", []) if n]
            topics = topics or [t for t in row.get("topics", []) if t]
            decisions = decisions or [d for d in row.get("decisions", []) if d]
            actions = actions or [a for a in row.get("actions", []) if a]
            summary = summary or row.get("summary")

    # 4. Generate structured chunk(s)
    if any([title, original_title, attendees, topics, decisions, actions]):
        chunks = chunk_meeting_content(
            title=title or "",
            original_title=original_title,
            attendees=attendees,
            topics=topics,
            decisions=decisions,
            actions=actions,
            summary=summary or "",
            date=date,
            platform=platform,
        )
    else:
        chunks = [summary] if summary and str(summary).strip() else []

    if not chunks:
        return False

    primary_chunk = chunks[0]
    vector = await embed_text(primary_chunk, settings=settings, embed=embed)
    if vector is None:
        return False

    now = datetime.now(UTC).isoformat()
    async with driver_to_use.session() as session:
        await session.run(
            """
            MATCH (m:Meeting {id: $meeting_id})
            SET m.embedding = $embedding,
                m.embedding_chunk = $primary_chunk,
                m.chunk_count = $chunk_count,
                m.embedding_updated_at = $now
            """,
            meeting_id=meeting_id,
            embedding=vector,
            primary_chunk=primary_chunk,
            chunk_count=len(chunks),
            now=now,
        )

    # 5. Embed and persist individual Chunk nodes
    await _persist_meeting_chunks(driver_to_use, meeting_id, chunks, vector, settings, embed, now)

    log.info("vector.meeting_embedded", meeting_id=meeting_id, chunks=len(chunks))
    return True


async def _embed_pending(
    fetch_cypher: str,
    write_cypher: str,
    meeting_id: str,
    text_field: str | Any,
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

    if not pending:
        return 0

    now = datetime.now(UTC).isoformat()
    limit = (settings or get_settings()).embedding_concurrency
    semaphore = asyncio.Semaphore(max(1, limit))

    async def embed_one(row: dict[str, Any]) -> int:
        if callable(text_field):
            text_val = text_field(row)
        else:
            text_val = row.get(text_field, "")

        if not text_val or not str(text_val).strip():
            return 0

        async with semaphore:
            vector = await embed_text(str(text_val), settings=settings, embed=embed)
        if vector is None:
            return 0
        async with driver.session() as session:
            await session.run(
                write_cypher,
                id=row["id"],
                embedding=vector,
                chunk_text=text_val,
                now=now,
            )
        return 1

    written = await asyncio.gather(*(embed_one(row) for row in pending))
    return sum(written)


async def embed_action_items_for_meeting(
    meeting_id: str, *, driver: Any = None, settings: Settings | None = None, embed: Any = None
) -> int:
    """Embed this meeting's un-embedded ActionItems with rich chunk context."""
    driver = driver or _driver()
    count = await _embed_pending(
        """
        MATCH (m:Meeting {id: $meeting_id})-[:FOLLOWS_UP]->(a:ActionItem)
        WHERE a.embedding IS NULL AND a.task IS NOT NULL
        OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
        RETURN a.id AS id, a.task AS task, coalesce(p.name, a.owner) AS owner,
               m.title AS meeting_title, m.original_title AS original_title
        """,
        """
        MATCH (a:ActionItem {id: $id})
        SET a.embedding = $embedding, a.embedding_chunk = $chunk_text, a.embedding_updated_at = $now
        """,
        meeting_id,
        lambda row: format_action_item_chunk(
            row.get("task", ""),
            owner=row.get("owner"),
            meeting_title=row.get("meeting_title"),
            original_title=row.get("original_title"),
        ),
        driver=driver, settings=settings, embed=embed,
    )
    if count:
        log.info("vector.actions_embedded", meeting_id=meeting_id, count=count)
    return count


async def embed_facts_for_meeting(
    meeting_id: str, *, driver: Any = None, settings: Settings | None = None, embed: Any = None
) -> int:
    """Embed Facts attached to this meeting with rich chunk context."""
    driver = driver or _driver()
    count = await _embed_pending(
        """
        MATCH (m:Meeting {id: $meeting_id})-[:HAS_FACT]->(f:Fact)
        WHERE f.embedding IS NULL AND f.text IS NOT NULL
        RETURN f.id AS id, f.text AS text,
               m.title AS meeting_title, m.original_title AS original_title
        """,
        """
        MATCH (f:Fact {id: $id})
        SET f.embedding = $embedding, f.embedding_chunk = $chunk_text, f.embedding_updated_at = $now
        """,
        meeting_id,
        lambda row: format_fact_chunk(
            row.get("text", ""),
            meeting_title=row.get("meeting_title"),
            original_title=row.get("original_title"),
        ),
        driver=driver, settings=settings, embed=embed,
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
    """Semantic search over Meeting summaries and structured chunks."""
    settings = settings or get_settings()
    return await _search(
        MEETING_INDEX,
        """
        UNWIND $ids AS mid
        MATCH (m:Meeting {id: mid})
        OPTIONAL MATCH (p:Person)-[:ATTENDED]->(m)
        RETURN m.id AS id, m.title AS title, m.original_title AS original_title,
               m.date AS date, m.summary AS summary, m.kind AS kind,
               m.embedding_chunk AS chunk,
               collect(DISTINCT p.name) AS attendees
        """,
        query_text, limit,
        driver=driver or _driver(), settings=settings, embed=embed, search=search,
    )


async def search_similar_chunks(
    query_text: str,
    limit: int = 5,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    embed: Any = None,
    search: Any = None,
) -> list[dict[str, Any]]:
    """Semantic search over Chunk embeddings."""
    settings = settings or get_settings()
    return await _search(
        CHUNK_INDEX,
        """
        UNWIND $ids AS cid
        MATCH (c:Chunk {id: cid})
        OPTIONAL MATCH (m:Meeting)-[:HAS_CHUNK]->(c)
        RETURN c.id AS id, c.text AS text, c.chunk_index AS chunk_index,
               m.id AS meeting_id, m.title AS meeting_title, m.original_title AS original_title
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
