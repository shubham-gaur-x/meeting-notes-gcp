"""Memory endpoints — the natural-language surface Phase 7 built the functions for."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.deps import principal
from meeting_notes import graph_client
from meeting_notes.access_control import Principal
from meeting_notes.memory import retrieval, vector

router = APIRouter(prefix="/graph", tags=["memory"])


class MemoryQuery(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/memory/query")
async def memory_query(body: MemoryQuery, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Answer a natural-language question from the graph.

    Semantic search is passed in as the fallback so a question sharing no
    keywords with any meeting still finds it by meaning.
    """
    return await retrieval.full_memory_query(
        body.question, search_meetings=vector.search_similar_meetings
    )


@router.get("/memory/person/{email}")
async def memory_person(email: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Everything remembered about one person.

    Returns `{}` for an untracked person — per-person analytics are opt-in.
    """
    return await retrieval.person_memory_profile(email)


@router.get("/memory/sessions")
async def memory_sessions(
    limit: int = Query(20, ge=1, le=100), _: Principal = Depends(principal)
) -> dict[str, Any]:
    driver = graph_client.get_driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (ms:MemorySession)
            RETURN ms.id AS id, ms.query_text AS query_text,
                   ms.answer_text AS answer_text, ms.nodes_accessed AS nodes_accessed,
                   ms.created_at AS created_at
            ORDER BY ms.created_at DESC
            LIMIT $limit
            """,
            limit=limit,
        )
        sessions = [dict(r) async for r in result]
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/search/meetings")
async def search_meetings(
    q: str = Query(min_length=1),
    limit: int = Query(5, ge=1, le=50),
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    hits = await vector.search_similar_meetings(q, limit=limit)
    return {"query": q, "results": hits, "count": len(hits)}


@router.get("/search/facts")
async def search_facts(
    q: str = Query(min_length=1),
    limit: int = Query(5, ge=1, le=50),
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    hits = await vector.search_similar_facts(q, limit=limit)
    return {"query": q, "results": hits, "count": len(hits)}
