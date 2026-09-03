"""Linear write operations an operator or dashboard triggers by hand.

Mirrors jira_ops.py with authenticated endpoints (Principal-gated) for Linear
state transitions, sub-issue creation, project assignments, and health checks.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.deps import principal
from meeting_notes import graph_client, linear_client
from meeting_notes.access_control import Principal

log = structlog.get_logger()

router = APIRouter(prefix="/linear", tags=["linear"])

_DONE_TYPES = frozenset({"completed", "canceled", "done", "closed"})


def _is_done_type(state_type: str) -> bool:
    return state_type.strip().lower() in _DONE_TYPES


def _state_name(issue: dict[str, Any], default: str = "Todo") -> str:
    """Extract the workflow state name from a Linear issue response."""
    return str((issue.get("state") or {}).get("name", default))


class LinearTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issue_id: str = Field(min_length=1)
    state_id: str = Field(min_length=1)
    action_id: str | None = None


class LinearSubtaskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parent_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    priority: str | int = "medium"
    child_action_id: str | None = None


class LinearCommentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issue_id: str = Field(min_length=1)
    comment: str = Field(min_length=1)


class LinearIssueRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1)
    description: str = ""
    project_id: str | None = None
    priority: str | int = "medium"
    due_date: str | None = None
    action_id: str | None = None


@router.post("/transition")
async def transition(
    body: LinearTransitionRequest, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Move a Linear issue to a new state and record state changes in the graph."""
    updated = await linear_client.transition_issue(body.issue_id, body.state_id)
    state_info = updated.get("state") or {}
    state_name = state_info.get("name", "")
    state_type = state_info.get("type", "")
    is_done = _is_done_type(state_type or state_name)

    if body.action_id:
        await graph_client.update_action_linear_state(
            body.action_id, linear_state=state_name, done=is_done
        )

    log.info("linear_ops.transition", issue_id=body.issue_id, state=state_name, is_done=is_done)
    return {"issue_id": body.issue_id, "state": state_name, "is_done": is_done, "updated": bool(updated)}


@router.post("/subtask")
async def subtask(
    body: LinearSubtaskRequest, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Create a sub-issue under a parent Linear issue and optionally link to graph ActionItem."""
    created = await linear_client.create_issue(
        title=body.title,
        description=body.description,
        parent_id=body.parent_id,
        priority=body.priority,
    )
    linear_id = created.get("id", "")
    linear_identifier = created.get("identifier", "")
    linear_url = created.get("url", "")
    linear_state = _state_name(created)

    if body.child_action_id and linear_id:
        await graph_client.update_action_linear_info(
            body.child_action_id,
            linear_id=linear_id,
            linear_identifier=linear_identifier,
            linear_url=linear_url,
            linear_state=linear_state,
        )

    log.info("linear_ops.subtask_created", parent_id=body.parent_id, identifier=linear_identifier)
    return {
        "parent_id": body.parent_id,
        "issue_id": linear_id,
        "identifier": linear_identifier,
        "url": linear_url,
    }


@router.post("/issue")
async def create_issue_endpoint(
    body: LinearIssueRequest, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Create a new Linear issue manually."""
    created = await linear_client.create_issue(
        title=body.title,
        description=body.description,
        project_id=body.project_id,
        priority=body.priority,
        due_date=body.due_date,
    )
    linear_id = created.get("id", "")
    linear_identifier = created.get("identifier", "")
    linear_url = created.get("url", "")
    linear_state = _state_name(created)

    if body.action_id and linear_id:
        await graph_client.update_action_linear_info(
            body.action_id,
            linear_id=linear_id,
            linear_identifier=linear_identifier,
            linear_url=linear_url,
            linear_state=linear_state,
        )

    return {
        "issue_id": linear_id,
        "identifier": linear_identifier,
        "url": linear_url,
        "state": linear_state,
    }


@router.post("/comment")
async def add_comment_endpoint(
    body: LinearCommentRequest, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Add a comment to a Linear issue."""
    comment = await linear_client.add_comment(body.issue_id, body.comment)
    return {"issue_id": body.issue_id, "comment_id": comment.get("id")}


@router.get("/projects")
async def list_projects_endpoint(_: Principal = Depends(principal)) -> dict[str, Any]:
    """List active Linear projects."""
    projects = await linear_client.list_projects()
    return {"projects": projects, "count": len(projects)}


@router.get("/states")
async def list_states_endpoint(
    team_id: str | None = None, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """List workflow states for a Linear team."""
    states = await linear_client.list_workflow_states(team_id=team_id)
    return {"states": states, "count": len(states)}


@router.get("/health")
async def health_endpoint(_: Principal = Depends(principal)) -> dict[str, Any]:
    """Check Linear API connectivity."""
    try:
        projects = await linear_client.list_projects()
        return {"status": "ok", "connected": True, "projects_count": len(projects)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "connected": False, "error": str(exc)}
