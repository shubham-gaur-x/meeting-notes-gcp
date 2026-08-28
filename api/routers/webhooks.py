"""Webhooks — the one public surface. HMAC-verified, never token-authed."""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from meeting_notes import github_webhook
from meeting_notes.config import get_settings
from meeting_notes.graph_client import close_agent_run_on_merge

log = structlog.get_logger()

router = APIRouter(prefix="/webhook", tags=["webhooks"])


async def _close_agent_run_on_merge(pr_url: str) -> None:
    try:
        result = await close_agent_run_on_merge(pr_url)
    except Exception:
        log.error("webhook.github.close_agent_run_failed", pr_url=pr_url, exc_info=True)
        return
    if result is not None:
        log.info("webhook.github.agent_run_closed", ticket_key=result.get("ticket_key"), pr_url=pr_url)


@router.post("/github")
async def webhook_github(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """GitHub merge/push events.

    Verified before anything else touches the payload. The graph write is
    backgrounded so GitHub gets a fast 200 — it retries on slow responses.

    `pull_request.merged` is the ONE place `dev_agent`'s CLOSED state is
    written (ADR-020) — it's a no-op for the many merged PRs that aren't the
    agent's, since `close_agent_run_on_merge` only matches an existing
    AgentRun. Every other event is acknowledge-only: ADR-008 puts the rest of
    the provenance writers in v2.
    """
    settings = get_settings()
    raw = await request.body()

    if not github_webhook.verify_signature(
        raw,
        request.headers.get(github_webhook.SIGNATURE_HEADER),
        settings.github_webhook_secret,
        settings=settings,
    ):
        log.warning("webhook.github.bad_signature")
        raise HTTPException(status_code=401, detail="bad signature")

    try:
        payload = json.loads(raw or b"{}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad json") from exc

    # NOTE: `github_event=`, never `event=`. structlog reserves `event` for the
    # message text and raises TypeError at call time -- a real production 500
    # in v5, missed because its tests called handlers directly rather than
    # driving the route (MIGRATION_FROM_V5.md #3).
    gh_event = request.headers.get("X-GitHub-Event", "")
    log.info("webhook.github.received", github_event=gh_event, keys=sorted(payload)[:5])

    if gh_event == "pull_request" and payload.get("action") == "closed":
        pr = payload.get("pull_request") or {}
        if pr.get("merged"):
            pr_url = pr.get("html_url", "")
            if pr_url:
                background_tasks.add_task(_close_agent_run_on_merge, pr_url)

    return {"status": "accepted", "event": gh_event}


async def _update_jira_status_background(key: str, status_name: str, done: bool) -> None:
    from meeting_notes.graph_client import update_action_jira_status
    try:
        await update_action_jira_status(key, status_name, done)
        log.info("webhook.jira.status_updated", key=key, status=status_name, done=done)
    except Exception as exc:
        log.warning("webhook.jira.update_failed", key=key, error=str(exc))


@router.post("/jira")
async def webhook_jira(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Jira issue events — status syncing back into the graph in real-time."""
    try:
        payload = json.loads(await request.body() or b"{}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad json") from exc

    jira_event = payload.get("webhookEvent", "")
    issue = payload.get("issue", {})
    key = issue.get("key")

    if key:
        status_name = issue.get("fields", {}).get("status", {}).get("name", "")
        done = status_name.lower() in ("done", "closed", "resolved") or bool(issue.get("fields", {}).get("resolution"))
        background_tasks.add_task(_update_jira_status_background, key, status_name, done)

    log.info("webhook.jira.received", jira_event=jira_event, key=key)
    return {"status": "accepted", "event": jira_event, "key": key}


@router.post("/jira/sync")
async def webhook_jira_sync() -> dict[str, Any]:
    """On-demand batch sync of all open Jira tickets into the graph."""
    from meeting_notes import jira_sync
    result = await jira_sync.sync_open_jira_tickets()
    return {"status": "ok", **result}
