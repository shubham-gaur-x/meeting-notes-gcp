"""Webhooks — the one public surface. HMAC-verified, never token-authed."""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from meeting_notes import github_webhook
from meeting_notes.config import get_settings

log = structlog.get_logger()

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/github")
async def webhook_github(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """GitHub merge/push events.

    Verified before anything else touches the payload. The graph write is
    backgrounded so GitHub gets a fast 200 — it retries on slow responses.

    v1 only acknowledges: ADR-008 puts the provenance *writers* in v2, so
    there is deliberately nothing to write yet.
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
    return {"status": "accepted", "event": gh_event}


@router.post("/jira")
async def webhook_jira(request: Request) -> dict[str, Any]:
    """Jira issue events — status syncing back into the graph.

    Jira Cloud webhooks carry no HMAC, so this is intentionally
    acknowledge-only in v1: `jira_sync` polls instead, which is authenticated
    and cannot be spoofed. Accepting writes from an unauthenticated POST would
    be a worse trade.
    """
    try:
        payload = json.loads(await request.body() or b"{}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad json") from exc

    jira_event = payload.get("webhookEvent", "")
    log.info("webhook.jira.received", jira_event=jira_event)
    return {"status": "accepted", "event": jira_event}
