"""Jira write operations an operator or the dashboard triggers by hand.

Deliberately **not** under `/webhook`. Everything in `webhooks.py` is a
public, unauthenticated surface that either verifies an HMAC or treats its
body as a hint and re-reads the truth over the authenticated REST API. These
routes are the opposite: the body *is* the instruction, and acting on it
spends this deployment's Jira credentials on an issue the caller names.

So they resolve a `Principal` like every other non-webhook route. Hanging
them off `/webhook` would have handed anyone who can reach the service the
ability to close any ticket, or open issues in any project, by POSTing a JSON
body — the same mistake `webhooks.py` documents having removed from `/jira`.

Thin wrappers over `jira_client` and `graph_client` (CLAUDE.md): no Jira REST
and no Cypher lives here.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.deps import principal
from meeting_notes import graph_client, jira_client
from meeting_notes.access_control import Principal

log = structlog.get_logger()

router = APIRouter(prefix="/jira", tags=["jira"])

# Jira treats these as terminal. `jira_sync.is_done` is the richer check — it
# also reads the issue's resolution field — but it needs a fetched issue, and
# here the transition we just asked for is the only fact available.
_DONE_STATUSES = frozenset({"done", "closed", "resolved"})


def _is_done(status_name: str) -> bool:
    return status_name.strip().lower() in _DONE_STATUSES


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1)
    status: str = Field(min_length=1)


class SubtaskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parent_key: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    description: str = ""
    priority: str = "medium"
    labels: list[str] = Field(default_factory=list)
    # When supplied, the new sub-task is also attached to this ActionItem in
    # the graph. Without it the Jira hierarchy exists and the graph one does
    # not, which is how `PARENT_OF` ends up unwritten and the hierarchy view
    # permanently flat.
    child_action_id: str | None = None


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inward_key: str = Field(min_length=1)
    outward_key: str = Field(min_length=1)
    link_type: str = "Relates"
    comment: str | None = None


class CommentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1)
    comment: str = Field(min_length=1)


@router.post("/transition")
async def transition(
    body: TransitionRequest, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Move an issue to a named status, then write that status into the graph.

    The graph is only updated when Jira accepted the transition. Writing it
    optimistically would leave the dashboard showing a done item that is still
    open in Jira, and the next sync would silently undo it.
    """
    moved = await jira_client.transition_issue(body.key, body.status)
    if moved:
        await graph_client.update_action_jira_status(
            body.key, body.status, _is_done(body.status)
        )
    log.info("jira_ops.transition", issue_key=body.key, status=body.status, moved=moved)
    return {"key": body.key, "status": body.status, "transitioned": moved}


@router.post("/subtask")
async def subtask(body: SubtaskRequest, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Create a Jira sub-task under a parent, and mirror the edge in the graph."""
    subtask_key = await jira_client.create_subtask(
        body.parent_key,
        body.summary,
        body.description,
        priority=body.priority,
        labels=body.labels or None,
    )

    linked = False
    if body.child_action_id:
        await graph_client.update_action_jira_key(body.child_action_id, subtask_key)
        linked = await graph_client.link_action_parent(body.parent_key, body.child_action_id)
        if not linked:
            # Not an error: a Jira parent filed outside this pipeline has no
            # ActionItem to hang the edge from.
            log.info(
                "jira_ops.parent_not_in_graph",
                parent_key=body.parent_key,
                child_action_id=body.child_action_id,
            )

    log.info("jira_ops.subtask_created", parent_key=body.parent_key, issue_key=subtask_key)
    return {
        "parent_key": body.parent_key,
        "subtask_key": subtask_key,
        "graph_linked": linked,
    }


@router.post("/link")
async def link(body: LinkRequest, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Relate two issues, possibly in different projects."""
    linked = await jira_client.link_issues(
        body.inward_key,
        body.outward_key,
        link_type=body.link_type,
        comment=body.comment,
    )
    return {
        "inward_key": body.inward_key,
        "outward_key": body.outward_key,
        "link_type": body.link_type,
        "linked": linked,
    }


@router.post("/comment")
async def comment(body: CommentRequest, _: Principal = Depends(principal)) -> dict[str, Any]:
    """Comment on an existing issue."""
    created = await jira_client.add_comment(body.key, body.comment)
    return {"key": body.key, "comment_id": created.get("id"), "status": "added"}
