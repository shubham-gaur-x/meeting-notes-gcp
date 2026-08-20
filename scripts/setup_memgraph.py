#!/usr/bin/env python3
"""Apply Memgraph's schema: constraints, indexes, and both vector indexes.

Idempotent. Memgraph raises on a constraint that already exists rather than
treating it as a no-op, so those errors are swallowed by name; anything else
is surfaced as a warning rather than silently dropped.

Two things here are load-bearing and easy to get wrong:

* **The provenance labels ship in v1 even though nothing writes them until
  v2** (ADR-008). Provenance cannot be backfilled — a merge that happens
  before the schema exists is lost forever — so `Ticket`, `PullRequest`,
  `AgentRun`, `Commit`, `FileChange` and `Blocker` are constrained now.
* **Both vector indexes are built for `embedding_dimension`**, 768 by
  default, matching what Vertex `text-embedding-005` and LM Studio's
  nomic-embed both return. Changing the dimension means migrating both
  indexes; it is not a knob to turn casually (CLAUDE.md).
"""

from __future__ import annotations

import asyncio
from typing import Any

from meeting_notes.config import get_settings
from meeting_notes.graph_client import close_driver, get_driver

# Node labels whose `id` must be unique. MERGE relies on these: without the
# constraint two writers can create parallel nodes that MERGE cannot collapse.
_ID_CONSTRAINED = (
    # core
    "Meeting",
    "Decision",
    "ActionItem",
    # memory layers
    "Fact",
    "Preference",
    "Procedure",
    "ProcedureStep",
    "MemorySession",
    # review / governance
    "PersonReview",
    "Blocker",
    # provenance — schema in v1, writers in v2 (ADR-008)
    "Ticket",
    "PullRequest",
    "AgentRun",
    "Commit",
    "FileChange",
)

# These MERGE on a natural key rather than a derived id.
_NATURAL_KEY_CONSTRAINED = (
    ("Person", "email"),
    ("Topic", "name"),
    ("Organization", "domain"),
)

_INDEXED = (
    ("Meeting", "date"),
    ("Meeting", "created_at"),
    ("ActionItem", "created_at"),
    ("ActionItem", "jira_key"),
    ("Decision", "created_at"),
    ("Person", "tracked"),
)


def statements(embedding_dimension: int) -> list[str]:
    """Every schema statement, in application order.

    Returned rather than executed so the schema is inspectable and testable
    without a database. Each entry is a single statement — Memgraph takes one
    per `run()`, so no semicolons.
    """
    out: list[str] = []

    for label in _ID_CONSTRAINED:
        out.append(f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.id IS UNIQUE")

    for label, key in _NATURAL_KEY_CONSTRAINED:
        out.append(f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{key} IS UNIQUE")

    for label, prop in _INDEXED:
        out.append(f"CREATE INDEX ON :{label}({prop})")

    # Vector indexes for semantic search. CREATE VECTOR INDEX is naturally
    # idempotent in Memgraph, unlike constraints.
    for name, label in (("meeting_embedding_idx", "Meeting"), ("fact_embedding_idx", "Fact")):
        out.append(
            f"CREATE VECTOR INDEX {name} ON :{label}(embedding) "
            f'WITH CONFIG {{"dimension": {embedding_dimension}, '
            '"capacity": 2048, "metric": "cos"}'
        )

    return out


async def apply(driver: Any | None = None, embedding_dimension: int | None = None) -> list[str]:
    """Apply the schema. Returns the statements that reported a real problem."""
    settings = get_settings()
    dimension = embedding_dimension or settings.embedding_dimension
    driver = driver or get_driver(settings)

    problems: list[str] = []
    async with driver.session() as session:
        for cypher in statements(dimension):
            try:
                await session.run(cypher)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                # Memgraph raises when a constraint already exists. That is what
                # idempotent looks like here, not a failure.
                if "already exists" not in str(exc).lower():
                    problems.append(f"{cypher}  ->  {exc}")
    return problems


def _main() -> int:
    async def run() -> int:
        settings = get_settings()
        print(f"  applying Memgraph schema at {settings.memgraph_host}:{settings.memgraph_port}")
        print(f"  vector index dimension: {settings.embedding_dimension}")
        try:
            problems = await apply()
        finally:
            await close_driver()

        total = len(statements(settings.embedding_dimension))
        if problems:
            print(f"  {total - len(problems)}/{total} statements applied; {len(problems)} problem(s):")
            for p in problems:
                print(f"    {p}")
            return 1
        print(f"  {total}/{total} statements applied")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(_main())
