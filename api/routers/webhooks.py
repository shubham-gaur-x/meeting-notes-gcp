"""Webhooks — the one public surface, so nothing here trusts its own request body.

GitHub signs its deliveries, so `/github` is HMAC-verified and the payload is
usable. Jira Cloud does not sign anything, so `/jira` treats the body as a hint
and re-reads the issue over the authenticated REST API before touching the
graph. `/jira/sync` is the exception that takes a shared token, because it is
the one route whose cost a caller can choose.
"""

from __future__ import annotations

import hmac
import json
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from api.deps import settings_dep
from meeting_notes import github_webhook
from meeting_notes.config import Settings, get_settings
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


async def _refresh_issue_from_jira(key: str) -> None:
    """Re-read one issue from Jira and write THAT status into the graph.

    The webhook body is never the source of truth. Jira Cloud webhooks carry no
    HMAC, so a POST to this route proves nothing about who sent it; trusting the
    payload would let anyone who can reach the service close any ActionItem by
    posting a status of "Done".

    Taking the key as a hint and then fetching the issue over the authenticated
    REST API keeps the real-time behaviour and removes the trust. A spoofed
    payload now achieves nothing beyond causing us to ask Jira about a ticket,
    and Jira answers with the truth.
    """
    from meeting_notes import jira_client, jira_sync
    from meeting_notes.graph_client import update_action_jira_status

    try:
        issue = await jira_client.get_issue(key)
        fields = issue.get("fields", {}) or {}
        status_name = (fields.get("status") or {}).get("name", "")
        if not status_name:
            log.warning("webhook.jira.no_status_from_api", key=key)
            return
        done = jira_sync.is_done(status_name, fields)
        await update_action_jira_status(key, status_name, done)
        log.info("webhook.jira.status_updated", key=key, status=status_name, done=done)
    except Exception as exc:  # noqa: BLE001 - a webhook must not 500 on Jira being down
        log.warning("webhook.jira.refresh_failed", key=key, error=str(exc))


@router.post("/jira")
async def webhook_jira(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Jira issue events — a trigger for an authenticated re-read, not a write.

    Acknowledge-only in the sense that matters: nothing from the body reaches
    the graph. See `_refresh_issue_from_jira` for why.
    """
    from meeting_notes.jira_sync import JIRA_KEY_RE

    try:
        payload = json.loads(await request.body() or b"{}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad json") from exc

    jira_event = payload.get("webhookEvent", "")
    key = (payload.get("issue") or {}).get("key")

    if key and JIRA_KEY_RE.match(str(key)):
        background_tasks.add_task(_refresh_issue_from_jira, str(key))
    elif key:
        # Not a 400: a webhook that argues with its sender just gets retried.
        log.warning("webhook.jira.malformed_key", key=str(key)[:64])
        key = None

    log.info("webhook.jira.received", jira_event=jira_event, key=key)
    return {"status": "accepted", "event": jira_event, "key": key}


@router.post("/jira/sync")
async def webhook_jira_sync(
    request: Request, settings: Settings = Depends(settings_dep)
) -> dict[str, Any]:
    """On-demand batch reconciliation against Jira.

    Guarded, unlike the event route above: this one costs a full sweep of the
    Jira REST API per call, so leaving it open is a way to run up someone's
    rate limit. Deployed without a token configured it refuses outright, which
    is the failure a person notices; the alternative is a quiet open endpoint.

    Settings arrive through `deps.settings_dep` rather than a direct
    `get_settings()` call. `config` stays the only reader of the environment
    either way, but this makes it the only *seam* as well: a caller — including
    a test — overrides one dependency instead of rebinding an attribute on this
    module, which is inert the moment the name is imported rather than looked up.
    """
    from meeting_notes import jira_sync

    token = settings.jira_sync_trigger_token.strip()
    if token:
        if not hmac.compare_digest(request.headers.get("X-Sync-Token", ""), token):
            raise HTTPException(status_code=401, detail="bad sync token")
    elif settings.gcp_project_id.strip():
        log.error("webhook.jira_sync.no_token_configured")
        raise HTTPException(
            status_code=503, detail="JIRA_SYNC_TRIGGER_TOKEN not configured"
        )
    else:
        log.warning("webhook.jira_sync.unauthenticated_local")

    result = await jira_sync.sync_open_jira_tickets()
    return {"status": "ok", **result}
