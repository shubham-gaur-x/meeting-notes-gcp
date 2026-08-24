"""Review queues — the output of confidence gating and person resolution."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from api.deps import principal
from meeting_notes import graph_client
from meeting_notes.access_control import Principal

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/actions")
async def actions(
    limit: int = Query(50, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Items held back from Jira for being below the confidence threshold."""
    items = await graph_client.get_actions_needing_review(limit=limit)
    return {"actions": items, "count": len(items)}


@router.get("/people")
async def people(
    limit: int = Query(50, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Attendees that could not be resolved. Held, never silently dropped."""
    items = await graph_client.get_person_reviews(limit=limit)
    return {"people": items, "count": len(items)}


@router.get("/blockers")
async def blockers(
    limit: int = Query(50, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Open blockers raised in meetings, with who raised each."""
    items = await graph_client.get_open_blockers(limit=limit)
    return {"blockers": items, "count": len(items)}
