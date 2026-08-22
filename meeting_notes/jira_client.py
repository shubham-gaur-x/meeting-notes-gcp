"""Jira REST — the ONLY module in this package that talks to Jira (CLAUDE.md).

Ported from v5. Two changes: credentials come from settings rather than
`os.environ`, and the transport is injectable so the suite runs with no Jira
account.

`adf_to_text` is the piece worth reading. Jira returns descriptions and
comments as Atlassian Document Format — a nested JSON tree, not text — so
without flattening, every description reaching the extractor would be a
stringified dict. Carried over from v5 unchanged.

Scope: the read path the Phase 5 connector needs, plus the small write
helpers `jira_pusher` and `jira_sync` will need in Phase 6. v5's
`list_eligible_tickets` / `build_sprint_jql` / `list_active_sprint_tickets`
are `dev_agent` concerns and `dev_agent` is v2 (ADR-008), so they are not
ported.
"""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.utils import with_retry

log = structlog.get_logger()

# (method, url, headers, params, json_body) -> (status, parsed_json)
Transport = Callable[
    [str, str, dict[str, str], dict[str, Any] | None, dict[str, Any] | None],
    Awaitable[tuple[int, Any]],
]


def jira_headers(settings: Settings) -> dict[str, str]:
    creds = base64.b64encode(
        f"{settings.jira_email}:{settings.jira_api_token}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def jira_base_url(settings: Settings) -> str:
    return f"https://{settings.jira_domain}/rest/api/3"


def adf_to_text(node: Any) -> str:
    """Flatten an Atlassian Document Format node to plain text.

    Carried from v5 unchanged. Without this, a Jira description arrives at the
    extractor as a stringified dict and the LLM is asked to read JSON noise.
    """
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type", "")
    if node_type == "text":
        text: str = node.get("text", "")
        return text
    if node_type == "hardBreak":
        return "\n"
    if node_type == "codeBlock":
        inner = "".join(adf_to_text(c) for c in node.get("content", []))
        return f"\n{inner}\n"

    children = node.get("content") or []
    flattened = "".join(adf_to_text(c) for c in children)

    if node_type in ("paragraph", "heading", "listItem"):
        return flattened + "\n"
    if node_type in ("bulletList", "orderedList"):
        return flattened
    return flattened


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
async def search_issues(
    jql: str,
    *,
    fields: list[str] | None = None,
    max_results: int = 50,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    transport = transport or _default_transport

    params: dict[str, Any] = {"jql": jql, "maxResults": max_results}
    if fields:
        params["fields"] = ",".join(fields)

    _, body = await transport(
        "GET", f"{jira_base_url(settings)}/search/jql", jira_headers(settings), params, None
    )
    issues: list[dict[str, Any]] = (body or {}).get("issues", [])
    return issues


@with_retry(max_attempts=3, base_delay=2.0)
async def get_issue(
    key: str, *, settings: Settings | None = None, transport: Transport | None = None
) -> dict[str, Any]:
    settings = settings or get_settings()
    transport = transport or _default_transport
    _, body = await transport(
        "GET", f"{jira_base_url(settings)}/issue/{key}", jira_headers(settings), None, None
    )
    return body or {}


@with_retry(max_attempts=3, base_delay=2.0)
async def add_comment(
    key: str, text: str, *, settings: Settings | None = None, transport: Transport | None = None
) -> None:
    """Comment on an issue. Phase 6's dedup path links to an existing ticket
    rather than opening a duplicate, and says so in a comment."""
    settings = settings or get_settings()
    transport = transport or _default_transport
    await transport(
        "POST",
        f"{jira_base_url(settings)}/issue/{key}/comment",
        jira_headers(settings),
        None,
        {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": text}]}
                ],
            }
        },
    )
    log.info("jira.comment_added", issue_key=key)


# ─── issue creation and sprint handling ────────────────────────────────────────
# Ported from v5's jira_pusher.py, where these lived inline. All Jira REST
# belongs in this file (CLAUDE.md), so the move is a boundary fix, not a
# rewrite.

MEETING_ACTION_ITEM_LABEL = "meeting-action-item"
# The label `dev_agent.find_sprint_candidates` selects on.
DEV_AGENT_LABEL = "dev-agent"

_PRIORITY_MAP = {"high": "High", "medium": "Medium", "low": "Low"}


async def active_sprint_id(
    *, settings: Settings | None = None, transport: Transport | None = None
) -> int | None:
    """The current active sprint on the configured board, or None.

    Not retried: a Kanban board returns 400 "the board does not support
    sprints" for this endpoint, which is a permanent property of the board,
    not a transient failure. Confirmed live against a real Kanban board --
    retrying it three times (2s/4s/8s backoff) wasted ~14s on every push for
    no benefit, since jira_pusher already treats any failure here as
    "proceed without a sprint". A genuine transient error (timeout, 5xx)
    still surfaces to that same fallback, just without the wasted retries.
    """
    settings = settings or get_settings()
    transport = transport or _default_transport
    url = f"https://{settings.jira_domain}/rest/agile/1.0/board/{settings.jira_board_id}/sprint"
    try:
        _, body = await transport("GET", url, jira_headers(settings), {"state": "active"}, None)
    except Exception as exc:
        import httpx

        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 400:
            return None
        raise
    sprints = (body or {}).get("values", [])
    return int(sprints[0]["id"]) if sprints else None


@with_retry(max_attempts=3, base_delay=2.0)
async def move_to_sprint(
    issue_key: str,
    sprint_id: int,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> None:
    settings = settings or get_settings()
    transport = transport or _default_transport
    url = f"https://{settings.jira_domain}/rest/agile/1.0/sprint/{sprint_id}/issue"
    status, _ = await transport("POST", url, jira_headers(settings), None, {"issues": [issue_key]})
    if status >= 400:
        raise RuntimeError(f"sprint move returned HTTP {status}")


async def create_issue(
    *,
    summary: str,
    description: str,
    priority: str,
    sprint_id: int | None,
    is_engineering_task: bool,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> str:
    """Create one Jira issue. Returns its key.

    Follow-ups the extractor raised get `meeting-action-item` so they are
    visibly distinct from work reported through normal channels. Engineering
    tasks get `dev-agent`, which is what `find_sprint_candidates` selects on —
    v5 left them unlabelled, which meant the agent could never see them.

    A high-priority item is moved to the active sprint. **A sprint-move
    failure does not fail issue creation** — the issue already exists at that
    point and is more valuable un-sprinted than lost.
    """
    settings = settings or get_settings()
    transport = transport or _default_transport

    fields: dict[str, Any] = {
        "project": {"key": settings.jira_project_key},
        "summary": summary,
        "description": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
        },
        "issuetype": {"name": settings.jira_issue_type},
        "priority": {"name": _PRIORITY_MAP.get(priority, "Medium")},
    }
    # The two halves have to agree on how a coding task is marked:
    # `find_sprint_candidates` selects on DEV_AGENT_LABEL, so an engineering
    # task created without it is invisible to the agent forever.
    fields["labels"] = (
        [DEV_AGENT_LABEL] if is_engineering_task else [MEETING_ACTION_ITEM_LABEL]
    )

    status, body = await transport(
        "POST", f"{jira_base_url(settings)}/issue", jira_headers(settings), None, {"fields": fields}
    )
    if status >= 400:
        raise RuntimeError(f"Jira issue creation returned HTTP {status}")
    issue_key: str = (body or {})["key"]

    if sprint_id and priority == "high":
        try:
            await move_to_sprint(issue_key, sprint_id, settings=settings, transport=transport)
        except Exception as exc:  # noqa: BLE001 - reported, issue creation still succeeds
            log.warning("jira.sprint_move_failed", issue_key=issue_key, error=str(exc))

    log.info("jira.issue_created", issue_key=issue_key, priority=priority)
    return issue_key


# ─── dev agent (Phase 11, ADR-020) ─────────────────────────────────────────────


@with_retry(max_attempts=3, base_delay=2.0)
async def list_active_sprint_tickets(
    project_key: str,
    statuses: list[str],
    require_labels: list[str],
    skip_labels: list[str],
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[dict[str, Any]]:
    """Tickets eligible for the dev agent: in the active sprint, in one of
    `statuses`, carrying every label in `require_labels`, carrying none of
    `skip_labels`.

    A ticket without any linked ActionItem (e.g. human-authored) is still
    eligible — the confidence gate that filters low-confidence ActionItem
    tickets lives in orchestrator.find_sprint_candidates, one layer up.
    """
    settings = settings or get_settings()
    status_clause = " OR ".join(f'status = "{s}"' for s in statuses)
    jql_parts = [f"project = {project_key}", "sprint in openSprints()", f"({status_clause})"]
    for label in require_labels:
        jql_parts.append(f'labels = "{label}"')
    for label in skip_labels:
        jql_parts.append(f'labels != "{label}"')
    jql = " AND ".join(jql_parts)

    issues = await search_issues(
        jql, fields=["summary", "description", "status", "labels", "priority"],
        settings=settings, transport=transport,
    )
    return [
        {
            "key": i["key"],
            "summary": i.get("fields", {}).get("summary", ""),
            "description": adf_to_text(i.get("fields", {}).get("description")),
            "status": (i.get("fields", {}).get("status") or {}).get("name", ""),
            "labels": i.get("fields", {}).get("labels", []),
        }
        for i in issues
    ]


async def get_issue_detail(
    key: str, *, settings: Settings | None = None, transport: Transport | None = None
) -> dict[str, Any]:
    """One ticket's key/summary/description, shaped for `orchestrator.build_prompt`."""
    issue = await get_issue(key, settings=settings, transport=transport)
    fields = issue.get("fields", {})
    return {
        "key": issue.get("key", key),
        "summary": fields.get("summary", ""),
        "description": adf_to_text(fields.get("description")),
    }


@with_retry(max_attempts=3, base_delay=2.0)
async def transition_issue(
    key: str,
    status_name: str,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> bool:
    """Move an issue to the named status. Returns False (not raises) if the
    transition is not available from the issue's current status — the caller
    logs and proceeds rather than failing the whole run over a workflow
    mismatch."""
    settings = settings or get_settings()
    transport = transport or _default_transport
    url = f"{jira_base_url(settings)}/issue/{key}/transitions"
    _, body = await transport("GET", url, jira_headers(settings), None, None)
    transitions = (body or {}).get("transitions", [])
    match = next((t for t in transitions if t.get("name") == status_name), None)
    if match is None:
        log.warning("jira.transition_unavailable", issue_key=key, status=status_name)
        return False
    status, _ = await transport(
        "POST", url, jira_headers(settings), None, {"transition": {"id": match["id"]}}
    )
    return status < 400
