"""Linear GraphQL client — the ONLY module in this package that talks to Linear.

Linear uses a unified GraphQL endpoint (https://api.linear.app/graphql) with API key
authentication. The transport is injectable so the test suite runs with no live Linear account.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import httpx


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


# Module-level client for connection pooling — avoids TCP/TLS setup per request.
_shared_client: httpx.AsyncClient | None = None


def _get_shared_client() -> httpx.AsyncClient:
    """Lazily create a shared httpx client with optimized connection pooling and timeouts."""
    global _shared_client  # noqa: PLW0603
    if _shared_client is None or _shared_client.is_closed:
        import httpx

        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30.0,
        )
        timeout = httpx.Timeout(
            timeout=30.0,
            connect=10.0,
            read=30.0,
            write=30.0,
            pool=10.0,
        )
        _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _shared_client


async def close_shared_client() -> None:
    """Explicitly close the shared httpx client session."""
    global _shared_client  # noqa: PLW0603
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


async def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
) -> tuple[int, Any]:
    import httpx

    client = _get_shared_client()
    try:
        response = await client.request(
            method, url, headers=headers, params=params, json=json_body
        )
    except httpx.TimeoutException as exc:
        log.warning("linear.timeout", error=str(exc), method=method, url=url)
        raise
    except httpx.NetworkError as exc:
        log.warning("linear.network_error", error=str(exc), method=method, url=url)
        raise

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        log.warning("linear.rate_limited", retry_after=retry_after, status=429)
        response.raise_for_status()

    # For 4xx responses, extract GraphQL error payloads if present in JSON body
    if response.status_code >= 400:
        try:
            body = response.json()
            if isinstance(body, dict) and "errors" in body:
                return response.status_code, body
        except Exception:
            pass
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


# O(1) lookup table — easier to extend than a chain of if/elif.
_PRIORITY_MAP: dict[str, int] = {
    "urgent": 1, "critical": 1, "p0": 1, "p1": 1,
    "high": 2, "p2": 2,
    "medium": 3, "med": 3, "p3": 3,
    "low": 4, "p4": 4,
}


def linear_priority_from_name(priority: str) -> int:
    """Map string priority to Linear's integer priority scale (0=None, 1=Urgent, 2=High, 3=Medium, 4=Low)."""
    return _PRIORITY_MAP.get(priority.strip().lower(), 0)


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


async def update_issue(
    issue_id: str,
    *,
    state_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    priority: str | int | None = None,
    assignee_id: str | None = None,
    project_id: str | None = None,
    parent_id: str | None = None,
    due_date: str | None = None,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Update fields on an existing Linear issue."""
    settings = settings or get_settings()
    mutation = """
    mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
        issue {
          id
          identifier
          title
          description
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
    input_data: dict[str, Any] = {}
    if state_id is not None:
        input_data["stateId"] = state_id
    if title is not None:
        input_data["title"] = title
    if description is not None:
        input_data["description"] = description
    if priority is not None:
        input_data["priority"] = (
            linear_priority_from_name(priority) if isinstance(priority, str) else priority
        )
    if assignee_id is not None:
        input_data["assigneeId"] = assignee_id
    if project_id is not None:
        input_data["projectId"] = project_id
    if parent_id is not None:
        input_data["parentId"] = parent_id
    if due_date is not None:
        input_data["dueDate"] = due_date

    data = await execute_graphql(
        mutation, {"id": issue_id, "input": input_data}, settings=settings, transport=transport
    )
    result = data.get("issueUpdate", {})
    if not result.get("success"):
        raise RuntimeError("Linear issueUpdate mutation returned success=false")

    issue: dict[str, Any] = result.get("issue", {})
    log.info("linear.issue_updated", id=issue.get("id"), identifier=issue.get("identifier"))
    return issue


async def transition_issue(
    issue_id: str,
    state_id: str,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Update the workflow state of a Linear issue."""
    return await update_issue(
        issue_id, state_id=state_id, settings=settings, transport=transport
    )


async def get_issue(
    issue_id: str,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any] | None:
    """Retrieve an issue from Linear by ID or identifier (e.g. 'ENG-42')."""
    settings = settings or get_settings()
    query = """
    query Issue($id: String!) {
      issue(id: $id) {
        id
        identifier
        title
        description
        url
        priority
        state {
          id
          name
          type
          color
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
    """
    data = await execute_graphql(query, {"id": issue_id}, settings=settings, transport=transport)
    issue: dict[str, Any] | None = data.get("issue")
    return issue


# In-memory TTL cache for workflow states per team: {team_id: (timestamp, states)}
_workflow_states_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SECONDS = 300.0


async def list_workflow_states(
    team_id: str | None = None,
    *,
    use_cache: bool = True,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[dict[str, Any]]:
    """List workflow states available for a team in Linear, with caching."""
    import time

    settings = settings or get_settings()
    team_id = team_id or settings.linear_team_id
    if not team_id:
        return []

    now = time.time()
    if use_cache and team_id in _workflow_states_cache:
        cached_time, cached_states = _workflow_states_cache[team_id]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_states

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
    if states:
        _workflow_states_cache[team_id] = (now, states)
    return states


async def resolve_workflow_state(
    state_name_or_id: str,
    team_id: str | None = None,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any] | None:
    """Resolve a workflow state by ID, name, or type (case-insensitive)."""
    if not state_name_or_id:
        return None
    target = state_name_or_id.strip()
    target_lower = target.lower()

    states = await list_workflow_states(team_id, settings=settings, transport=transport)
    for st in states:
        if st.get("id") == target:
            return st
    for st in states:
        if (st.get("name") or "").strip().lower() == target_lower:
            return st
    for st in states:
        if (st.get("type") or "").strip().lower() == target_lower:
            return st

    return {"id": target, "name": target, "type": "unknown"}


async def create_issue_relation(
    issue_id: str,
    related_issue_id: str,
    relation_type: str = "related",
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Relate two issues in Linear (e.g. 'related', 'blocks', 'duplicate')."""
    settings = settings or get_settings()
    mutation = """
    mutation IssueRelationCreate($input: IssueRelationCreateInput!) {
      issueRelationCreate(input: $input) {
        success
        issueRelation {
          id
          type
          issue {
            id
            identifier
          }
          relatedIssue {
            id
            identifier
          }
        }
      }
    }
    """
    input_data = {
        "issueId": issue_id,
        "relatedIssueId": related_issue_id,
        "type": relation_type,
    }
    data = await execute_graphql(mutation, {"input": input_data}, settings=settings, transport=transport)
    result = data.get("issueRelationCreate", {})
    if not result.get("success"):
        raise RuntimeError("Linear issueRelationCreate mutation returned success=false")
    relation: dict[str, Any] = result.get("issueRelation", {})
    log.info(
        "linear.relation_created",
        issue_id=issue_id,
        related_id=related_issue_id,
        type=relation_type,
    )
    return relation


async def create_attachment(
    issue_id: str,
    url: str,
    title: str = "Meeting Thread",
    *,
    subtitle: str | None = None,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Attach an external link (e.g. Gmail thread URL) to a Linear issue."""
    settings = settings or get_settings()
    mutation = """
    mutation AttachmentCreate($input: AttachmentCreateInput!) {
      attachmentCreate(input: $input) {
        success
        attachment {
          id
          url
          title
        }
      }
    }
    """
    input_data: dict[str, Any] = {
        "issueId": issue_id,
        "url": url,
        "title": title,
    }
    if subtitle:
        input_data["subtitle"] = subtitle

    data = await execute_graphql(mutation, {"input": input_data}, settings=settings, transport=transport)
    result = data.get("attachmentCreate", {})
    attachment: dict[str, Any] = result.get("attachment", {})
    log.info("linear.attachment_created", issue_id=issue_id, url=url)
    return attachment


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
