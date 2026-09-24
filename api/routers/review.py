"""Review queues — the output of confidence gating and person resolution."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from api.deps import principal
from meeting_notes import graph_client
from meeting_notes.access_control import Principal

router = APIRouter(prefix="/review", tags=["review"])


class ResolvePersonRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1)
    email: str | None = None


class AddAttendeeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)


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


@router.post("/people/{review_id}/resolve")
async def resolve_person(
    review_id: str,
    req: ResolvePersonRequest,
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    """Resolve an unverified attendee with their verified name and optional email."""
    res = await graph_client.resolve_person_review(review_id, req.name, req.email)
    return {"status": "ok", "person": res}


@router.delete("/people/{review_id}")
async def delete_person(
    review_id: str,
    delete_actions: bool = Query(True),
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    """Permanently delete an invalid person review node and unconfirmed actions."""
    deleted = await graph_client.delete_person_review(review_id, delete_actions=delete_actions)
    return {"status": "ok", "deleted": deleted}


@router.post("/meeting/{meeting_id}/attendee")
async def add_attendee(
    meeting_id: str,
    req: AddAttendeeRequest,
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    """Add a confirmed attendee directly to a meeting."""
    res = await graph_client.add_meeting_attendee(meeting_id, req.name, req.email)
    return {"status": "ok", "attendee": res}


@router.get("/blockers")
async def blockers(
    limit: int = Query(50, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Open blockers raised in meetings, with who raised each."""
    items = await graph_client.get_open_blockers(limit=limit)
    return {"blockers": items, "count": len(items)}
