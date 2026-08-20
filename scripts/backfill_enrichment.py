#!/usr/bin/env python3
"""Backfill graph enrichment over meetings already in the graph.

Enrichment (facts, relationships, temporal chains, causality, procedures,
embeddings) landed in Phase 7, after Phase 6 had already ingested. Meetings
written before that have no memory layer at all — this replays enrichment for
them without re-extracting, which would cost another full LLM pass over the
corpus and change nothing about the meetings themselves.

Reconstructs each `ExtractedMeeting` from its graph node rather than the
original payload: attendees, topics and action items are all already stored,
and enrichment only reads those.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

import structlog

from meeting_notes import graph_client, pipeline
from meeting_notes.models import ExtractedMeeting
from meeting_notes.utils import configure_logging

log = structlog.get_logger()

_FETCH = """
MATCH (m:Meeting)
OPTIONAL MATCH (p:Person)-[:ATTENDED]->(m)
OPTIONAL MATCH (m)-[:DISCUSSED]->(t:Topic)
OPTIONAL MATCH (m)-[:FOLLOWS_UP]->(a:ActionItem)
OPTIONAL MATCH (m)-[:PRODUCED]->(d:Decision)
RETURN m.id AS id, m.title AS title, m.date AS date, m.kind AS kind,
       m.platform AS platform, coalesce(m.summary, '') AS summary,
       coalesce(m.follow_up_needed, false) AS follow_up_needed,
       collect(DISTINCT {name: p.name, email: p.email}) AS attendees,
       collect(DISTINCT t.name) AS topics,
       collect(DISTINCT {owner: a.owner, task: a.task}) AS action_items,
       collect(DISTINCT d.text) AS decisions
ORDER BY date
"""


def _rebuild(row: dict[str, Any]) -> ExtractedMeeting:
    attendees = [a for a in row["attendees"] if a.get("email") or a.get("name")]
    actions = [a for a in row["action_items"] if a.get("task")]
    return ExtractedMeeting.model_validate(
        {
            "title": row["title"] or "Untitled",
            "kind": row["kind"] or "meeting",
            "platform": row["platform"] or "unknown",
            "date": row["date"],
            "summary": row["summary"] or row["title"] or "",
            "follow_up_needed": row["follow_up_needed"],
            "attendees": attendees,
            "topics": [t for t in row["topics"] if t],
            "decisions": [d for d in row["decisions"] if d],
            "action_items": actions,
        }
    )


async def run(limit: int | None = None) -> dict[str, int]:
    driver = graph_client.get_driver()
    async with driver.session() as session:
        result = await session.run(_FETCH)
        rows = [dict(r) async for r in result]

    if limit:
        rows = rows[:limit]

    ok = failed = 0
    for i, row in enumerate(rows, 1):
        try:
            await pipeline.enrich(_rebuild(row), row["id"])
            ok += 1
        except Exception as exc:  # noqa: BLE001 - one bad meeting must not stop the backfill
            failed += 1
            log.warning("backfill.meeting_failed", meeting_id=row["id"], error=str(exc))
        if i % 10 == 0:
            print(f"  {i}/{len(rows)}")

    await graph_client.close_driver()
    print(f"  backfill: {ok} enriched, {failed} failed, of {len(rows)}")
    return {"total": len(rows), "enriched": ok, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backfill_enrichment", description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="only the first N meetings")
    args = parser.parse_args(argv)
    configure_logging()
    result = asyncio.run(run(args.limit))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
