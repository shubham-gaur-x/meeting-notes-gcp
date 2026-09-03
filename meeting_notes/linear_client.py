"""Linear GraphQL client — the ONLY module in this package that talks to Linear.

Linear uses a unified GraphQL endpoint (https://api.linear.app/graphql) with API key
authentication. The transport is injectable so the test suite runs with no live Linear account.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.utils import with_retry

log = structlog.get_logger()

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"

# (method, url, headers, params, json_body) -> (status, parsed_json)
Transport = Callable[
    [str, str, dict[str, str], dict[str, Any] | None, dict[str, Any] | None],
    Awaitable[tuple[int, Any]],
]


def linear_headers(settings: Settings) -> dict[str, str]:
    """Build Authorization and Content-Type headers for Linear GraphQL requests."""
    return {
        "Authorization": settings.linear_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
) -> tuple[int, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method, url, headers=headers, params=params, json=json_body
        )
        response.raise_for_status()
        return response.status_code, (response.json() if response.content else None)


@with_retry(max_attempts=3, base_delay=2.0)
async def execute_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Execute a GraphQL query or mutation against Linear's API."""
    settings = settings or get_settings()
    transport = transport or _default_transport

    payload: dict[str, Any] = {"query": query, "variables": variables or {}}
    status, body = await transport("POST", LINEAR_GRAPHQL_URL, linear_headers(settings), None, payload)

    if not isinstance(body, dict):
        raise ValueError(f"Linear GraphQL returned non-dict response (status {status})")

    if "errors" in body and body["errors"]:
        error_msg = body["errors"][0].get("message", "Unknown GraphQL error")
        log.warning("linear.graphql_error", error=error_msg, errors=body["errors"])
        raise RuntimeError(f"Linear GraphQL error: {error_msg}")

    data: dict[str, Any] = body.get("data", {})
    return data


def linear_priority_from_name(priority: str) -> int:
    """Map string priority to Linear's integer priority scale (0=None, 1=Urgent, 2=High, 3=Medium, 4=Low)."""
    p = priority.strip().lower()
    if p in ("urgent", "critical", "p0", "p1"):
        return 1
    if p in ("high", "p2"):
        return 2
    if p in ("medium", "med", "p3"):
        return 3
    if p in ("low", "p4"):
        return 4
    return 0


async def create_issue(
    title: str,
    *,
    description: str = "",
    team_id: str | None = None,
    project_id: str | None = None,
    parent_id: str | None = None,
    priority: str | int = 0,
    due_date: str | None = None,
    assignee_id: str | None = None,
    label_ids: list[str] | None = None,
    state_id: str | None = None,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Create an issue in Linear, optionally attached to a project or parent issue."""
    settings = settings or get_settings()
    team_id = team_id or settings.linear_team_id
    if not team_id:
        raise ValueError("linear_team_id is required to create a Linear issue")

    int_priority = linear_priority_from_name(priority) if isinstance(priority, str) else priority

    mutation = """
    mutation IssueCreate($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue {
          id
          identifier
          title
          url
          priority
          state {
            id
            name
            type
          }
          project {
            id
            name
          }
          parent {
            id
            identifier
          }
        }
      }
    }
    """
    input_data: dict[str, Any] = {
        "title": title,
        "teamId": team_id,
        "description": description,
        "priority": int_priority,
    }
    if project_id:
        input_data["projectId"] = project_id
    elif settings.linear_default_project_id:
        input_data["projectId"] = settings.linear_default_project_id

    if parent_id:
        input_data["parentId"] = parent_id
    if due_date:
        input_data["dueDate"] = due_date
    if assignee_id:
        input_data["assigneeId"] = assignee_id
    if label_ids:
        input_data["labelIds"] = label_ids
    if state_id:
        input_data["stateId"] = state_id

    data = await execute_graphql(mutation, {"input": input_data}, settings=settings, transport=transport)
    result = data.get("issueCreate", {})
    if not result.get("success"):
        raise RuntimeError("Linear issueCreate mutation returned success=false")

    issue: dict[str, Any] = result.get("issue", {})
    log.info("linear.issue_created", identifier=issue.get("identifier"), id=issue.get("id"))
    return issue


async def create_project(
    name: str,
    *,
    team_ids: list[str] | None = None,
    description: str = "",
    color: str = "#5E6AD2",
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Create a project in Linear for grouping deliverables and initiatives."""
    settings = settings or get_settings()
    team_ids = team_ids or ([settings.linear_team_id] if settings.linear_team_id else [])
    if not team_ids:
        raise ValueError("At least one team_id is required to create a Linear project")

    mutation = """
    mutation ProjectCreate($input: ProjectCreateInput!) {
      projectCreate(input: $input) {
        success
        project {
          id
          name
          url
          state
        }
      }
    }
    """
    input_data: dict[str, Any] = {
        "name": name,
        "teamIds": team_ids,
        "description": description,
        "color": color,
    }

    data = await execute_graphql(mutation, {"input": input_data}, settings=settings, transport=transport)
    result = data.get("projectCreate", {})
    if not result.get("success"):
        raise RuntimeError("Linear projectCreate mutation returned success=false")

    project: dict[str, Any] = result.get("project", {})
    log.info("linear.project_created", name=project.get("name"), id=project.get("id"))
    return project


async def add_comment(
    issue_id: str,
    body: str,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Add a comment to an existing Linear issue."""
    settings = settings or get_settings()
    mutation = """
    mutation CommentCreate($input: CommentCreateInput!) {
      commentCreate(input: $input) {
        success
        comment {
          id
          body
        }
      }
    }
    """
    data = await execute_graphql(
        mutation, {"input": {"issueId": issue_id, "body": body}}, settings=settings, transport=transport
    )
    result = data.get("commentCreate", {})
    comment: dict[str, Any] = result.get("comment", {})
    log.info("linear.comment_added", issue_id=issue_id, comment_id=comment.get("id"))
    return comment


async def transition_issue(
    issue_id: str,
    state_id: str,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Update the workflow state of a Linear issue."""
    settings = settings or get_settings()
    mutation = """
    mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
        issue {
          id
          identifier
          state {
            id
            name
            type
          }
        }
      }
    }
    """
    data = await execute_graphql(
        mutation, {"id": issue_id, "input": {"stateId": state_id}}, settings=settings, transport=transport
    )
    result = data.get("issueUpdate", {})
    if not result.get("success"):
        raise RuntimeError("Linear issueUpdate mutation returned success=false")

    issue: dict[str, Any] = result.get("issue", {})
    log.info("linear.issue_transitioned", id=issue.get("id"), state=issue.get("state"))
    return issue


async def list_workflow_states(
    team_id: str | None = None,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[dict[str, Any]]:
    """List workflow states available for a team in Linear."""
    settings = settings or get_settings()
    team_id = team_id or settings.linear_team_id
    query = """
    query WorkflowStates($teamId: String) {
      workflowStates(filter: { team: { id: { eq: $teamId } } }) {
        nodes {
          id
          name
          type
          color
        }
      }
    }
    """
    data = await execute_graphql(query, {"teamId": team_id}, settings=settings, transport=transport)
    states: list[dict[str, Any]] = data.get("workflowStates", {}).get("nodes", [])
    return states


async def list_projects(
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[dict[str, Any]]:
    """List active Linear projects."""
    settings = settings or get_settings()
    query = """
    query Projects {
      projects {
        nodes {
          id
          name
          url
          state
        }
      }
    }
    """
    data = await execute_graphql(query, {}, settings=settings, transport=transport)
    projects: list[dict[str, Any]] = data.get("projects", {}).get("nodes", [])
    return projects


async def search_issues(
    term: str,
    *,
    team_id: str | None = None,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[dict[str, Any]]:
    """Search issues by query string in Linear."""
    settings = settings or get_settings()
    team_id = team_id or settings.linear_team_id
    query = """
    query IssueSearch($term: String!, $teamId: String) {
      issueSearch(query: $term, filter: { team: { id: { eq: $teamId } } }, first: 25) {
        nodes {
          id
          identifier
          title
          description
          url
          state {
            id
            name
            type
          }
        }
      }
    }
    """
    data = await execute_graphql(
        query, {"term": term, "teamId": team_id}, settings=settings, transport=transport
    )
    issues: list[dict[str, Any]] = data.get("issueSearch", {}).get("nodes", [])
    return issues
