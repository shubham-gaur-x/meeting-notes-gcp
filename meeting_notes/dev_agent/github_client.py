"""GitHub API client — read-only PR verification.

The dev agent never opens a PR through this module — that happens inside the
headless coding-agent run itself (`gh pr create`, prompted for in
`orchestrator.build_prompt`). This module only *finds* the PR the agent
opened, by branch name, and fetches its diff for the guardrail gates and
self-verify to score.
"""

from __future__ import annotations

from typing import Any

import structlog

from meeting_notes.utils import with_retry

log = structlog.get_logger()


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@with_retry(max_attempts=3, base_delay=2.0)
async def find_open_pr(
    owner: str, repo: str, branch: str, token: str, transport: Any = None
) -> dict[str, Any] | None:
    """Return {number, html_url} for the first open PR on this branch, or None."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            params={"head": f"{owner}:{branch}", "state": "open"},
            headers=_github_headers(token),
        )
        resp.raise_for_status()
        pulls = resp.json()

    if not pulls:
        return None
    pr = pulls[0]
    return {"number": pr["number"], "html_url": pr["html_url"]}


@with_retry(max_attempts=3, base_delay=2.0)
async def get_pr_diff(
    owner: str, repo: str, pr_number: int, token: str, max_bytes: int = 200_000
) -> str:
    """The unified diff for a PR (truncated to `max_bytes`), or "" if unavailable.

    Used by self-verify to score the change against the ticket intent.
    """
    import httpx

    headers = _github_headers(token)
    headers["Accept"] = "application/vnd.github.v3.diff"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}", headers=headers
        )
        resp.raise_for_status()
        return resp.text[:max_bytes]
