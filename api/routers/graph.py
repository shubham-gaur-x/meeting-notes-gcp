"""Graph read endpoints. Thin wrappers over `graph_client` (CLAUDE.md)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import principal
from meeting_notes import digest, graph_client
from meeting_notes.access_control import Principal

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/meetings/recent")
async def meetings_recent(
    limit: int = Query(10, ge=1, le=100), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Meetings by date, newest first."""
    meetings = await graph_client.get_recent_meetings(limit=limit)
    return {"meetings": meetings, "count": len(meetings)}


@router.get("/meetings/quality")
async def meetings_quality(
    limit: int = Query(20, ge=1, le=100), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Meetings ranked by the nightly quality score."""
    meetings = await graph_client.get_meetings_quality_ranked(limit=limit)
    return {"meetings": meetings, "count": len(meetings)}


@router.get("/timeline")
async def timeline(
    limit: int = Query(30, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Meetings in date order with the gap between them, for the timeline view."""
    events = await graph_client.get_timeline(limit=limit)
    return {"timeline": events, "count": len(events)}


@router.get("/person/{email}")
async def person(email: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """One person's meetings, topics and commitments, addressed by email."""
    return await graph_client.get_person_graph(email)


@router.get("/topic/{name}")
async def topic(name: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """One topic and the meetings that discussed it."""
    return await graph_client.get_topic_graph(name)


@router.get("/actions/open")
async def actions_open(
    limit: int = Query(50, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Undone action items, soonest deadline first, with Jira keys where filed."""
    actions = await graph_client.get_open_actions(limit=limit)
    return {"actions": actions, "count": len(actions)}


@router.get("/provenance/{meeting_id}")
async def meeting_provenance(meeting_id: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Empty until v2 — ADR-008 ships the schema in v1, the writers in v2."""
    return await graph_client.get_meeting_provenance(meeting_id)


@router.get("/provenance/by-ticket/{ticket_key}")
async def ticket_provenance(ticket_key: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """What a Jira ticket traces back to — the meeting, and the run that
    implemented it if the dev agent did."""
    return await graph_client.get_ticket_provenance(ticket_key)


_DATE = r"^\d{4}-\d{2}-\d{2}$"


@router.get("/digest/weekly")
async def digest_weekly(
    days: int = Query(7, ge=1, le=3660),
    start: str | None = Query(None, pattern=_DATE, description="inclusive, YYYY-MM-DD"),
    end: str | None = Query(None, pattern=_DATE, description="inclusive, YYYY-MM-DD"),
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    """Rollup over a window: meetings, decisions, and action items by state.

    `start`/`end` win over `days`. The `days` ceiling is ten years rather than
    90 so "past year" and "all time" are askable — the old cap silently made
    them impossible.
    """
    if start and end and end < start:
        # Returning nothing would read as a quiet period rather than a typo.
        raise HTTPException(status_code=422, detail="end must not be before start")
    return await digest.weekly_digest(days=days, start=start, end=end)


@router.get("/visualize")
async def visualize(
    limit: int = Query(150, ge=10, le=400),
    labels: str | None = Query(None, description="comma-separated node labels to include"),
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    """A drawable slice of the graph — the most connected nodes and the edges
    between them."""
    wanted = [x.strip() for x in labels.split(",") if x.strip()] if labels else None
    snapshot = await graph_client.get_graph_snapshot(limit=limit, labels=wanted)
    return {**snapshot, "count": len(snapshot["nodes"])}


@router.get("/meeting/{meeting_id}")
async def meeting_detail(meeting_id: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Everything one meeting produced — attendees, topics, decisions, actions."""
    return await graph_client.get_meeting_detail(meeting_id)


@router.get("/decisions")
async def decisions(
    limit: int = Query(25, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Decisions, newest first, each traceable to the meeting that made it."""
    found = await graph_client.get_recent_decisions(limit=limit)
    return {"decisions": found, "count": len(found)}
