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
