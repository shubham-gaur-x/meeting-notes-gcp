"""Graph read endpoints. Thin wrappers over `graph_client` (CLAUDE.md)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from api.deps import principal
from meeting_notes import digest, graph_client
from meeting_notes.access_control import Principal

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/meetings/recent")
async def meetings_recent(
    limit: int = Query(10, ge=1, le=100), _: Principal = Depends(principal)
) -> dict[str, Any]:
    meetings = await graph_client.get_recent_meetings(limit=limit)
    return {"meetings": meetings, "count": len(meetings)}


@router.get("/timeline")
async def timeline(
    limit: int = Query(30, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    events = await graph_client.get_timeline(limit=limit)
    return {"timeline": events, "count": len(events)}


@router.get("/person/{email}")
async def person(email: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    return await graph_client.get_person_graph(email)


@router.get("/topic/{name}")
async def topic(name: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    return await graph_client.get_topic_graph(name)


@router.get("/actions/open")
async def actions_open(
    limit: int = Query(50, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    actions = await graph_client.get_open_actions(limit=limit)
    return {"actions": actions, "count": len(actions)}


@router.get("/provenance/{meeting_id}")
async def meeting_provenance(meeting_id: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Empty until v2 — ADR-008 ships the schema in v1, the writers in v2."""
    return await graph_client.get_meeting_provenance(meeting_id)


@router.get("/provenance/by-ticket/{ticket_key}")
async def ticket_provenance(ticket_key: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    return await graph_client.get_ticket_provenance(ticket_key)


@router.get("/digest/weekly")
async def digest_weekly(
    days: int = Query(7, ge=1, le=90), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Rollup of the last week: meetings, decisions, and action items by state."""
    return await digest.weekly_digest(days=days)
