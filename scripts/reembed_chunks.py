"""Re-embed all existing Meetings, ActionItems, and Facts in Memgraph using structured chunks.

Every chunk includes:
- Meeting title and original/source title
- All attendee names (e.g. Coley Woyak, Michael Baylard)
- Topics, key decisions, and action item deliverables
- Clear contextual headers on all chunk segments
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from meeting_notes.graph_client import close_driver, get_driver
from meeting_notes.llm_client import embed
from meeting_notes.memory import vector

log = structlog.get_logger()


async def reembed_all() -> dict[str, int]:
    driver = get_driver()
    now = datetime.now(UTC).isoformat()

    stats = {"meetings": 0, "chunks": 0, "actions": 0, "facts": 0}

    # 1. Re-embed Meetings
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (m:Meeting)
            OPTIONAL MATCH (p:Person)-[:ATTENDED]->(m)
            OPTIONAL MATCH (m)-[:DISCUSSED]->(t:Topic)
            OPTIONAL MATCH (m)-[:PRODUCED]->(d:Decision)
            OPTIONAL MATCH (m)-[:FOLLOWS_UP]->(a:ActionItem)
            RETURN m.id AS id, m.title AS title, m.original_title AS original_title,
                   m.summary AS summary, m.date AS date, m.platform AS platform,
                   collect(DISTINCT p.name) AS attendees,
                   collect(DISTINCT t.name) AS topics,
                   collect(DISTINCT d.text) AS decisions,
                   collect(
                       DISTINCT CASE WHEN a.owner IS NOT NULL THEN a.owner + ': ' + a.task ELSE a.task END
                   ) AS actions
            """
        )
        meetings = [dict(r) async for r in result]

    print(f"Found {len(meetings)} meetings to re-embed in structured chunks...")
    for m in meetings:
        ok = await vector.embed_meeting(
            m["id"],
            title=m.get("title") or "",
            original_title=m.get("original_title"),
            attendees=m.get("attendees") or [],
            topics=m.get("topics") or [],
            decisions=m.get("decisions") or [],
            actions=m.get("actions") or [],
            summary=m.get("summary") or "",
            date=str(m.get("date") or ""),
            platform=m.get("platform") or "",
            driver=driver,
            embed=embed,
        )
        if ok:
            stats["meetings"] += 1
            # Check chunks created
            async with driver.session() as session:
                c_res = await session.run(
                    "MATCH (:Meeting {id: $id})-[:HAS_CHUNK]->(c:Chunk) RETURN count(c) AS cnt",
                    id=m["id"],
                )
                r = await c_res.single()
                if r:
                    stats["chunks"] += r["cnt"]
            print(
                f"  ✓ Embedded meeting: {m.get('title')} (original: {m.get('original_title')})"
            )

    # 2. Re-embed Action Items with rich context
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (m:Meeting)-[:FOLLOWS_UP]->(a:ActionItem)
            WHERE a.task IS NOT NULL
            OPTIONAL MATCH (a)-[:ASSIGNED_TO]->(p:Person)
            RETURN a.id AS id, a.task AS task, coalesce(p.name, a.owner) AS owner,
                   m.title AS meeting_title, m.original_title AS original_title
            """
        )
        actions = [dict(r) async for r in result]

    print(f"\nRe-embedding {len(actions)} action items with assignee and meeting context...")
    for act in actions:
        chunk_text = vector.format_action_item_chunk(
            act["task"],
            owner=act.get("owner"),
            meeting_title=act.get("meeting_title"),
            original_title=act.get("original_title"),
        )
        vec = await embed(chunk_text)
        if vec:
            async with driver.session() as session:
                await session.run(
                    """
                    MATCH (a:ActionItem {id: $id})
                    SET a.embedding = $embedding,
                        a.embedding_chunk = $chunk_text,
                        a.embedding_updated_at = $now
                    """,
                    id=act["id"],
                    embedding=vec,
                    chunk_text=chunk_text,
                    now=now,
                )
            stats["actions"] += 1

    # 3. Re-embed Facts with rich context
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (m:Meeting)-[:HAS_FACT]->(f:Fact)
            WHERE f.text IS NOT NULL
            RETURN f.id AS id, f.text AS text,
                   m.title AS meeting_title, m.original_title AS original_title
            """
        )
        facts = [dict(r) async for r in result]

    print(f"\nRe-embedding {len(facts)} facts with meeting provenance...")
    for f in facts:
        chunk_text = vector.format_fact_chunk(
            f["text"],
            meeting_title=f.get("meeting_title"),
            original_title=f.get("original_title"),
        )
        vec = await embed(chunk_text)
        if vec:
            async with driver.session() as session:
                await session.run(
                    """
                    MATCH (f:Fact {id: $id})
                    SET f.embedding = $embedding,
                        f.embedding_chunk = $chunk_text,
                        f.embedding_updated_at = $now
                    """,
                    id=f["id"],
                    embedding=vec,
                    chunk_text=chunk_text,
                    now=now,
                )
            stats["facts"] += 1

    await close_driver()
    return stats


if __name__ == "__main__":
    out = asyncio.run(reembed_all())
    print("\nRe-embedding summary:", out)
