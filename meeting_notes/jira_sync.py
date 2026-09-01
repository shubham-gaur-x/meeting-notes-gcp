"""Jira status -> graph. The reverse direction from jira_pusher.

Ported from v5's `jira_agent.py`. Consumes staged `source_type="jira"` rows
(the same staging table everything else uses, ADR-018) rather than a
dedicated raw table.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

log = structlog.get_logger()

DONE_STATUSES = ("done", "closed", "resolved")

# Jira project keys are uppercase alphanumerics, a hyphen, then digits. Every
# key reaching JQL or a REST path is checked against this, because keys arrive
# from webhook payloads and from `a.jira_key` in the graph -- neither of which
# is a trusted source.
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")

_DONE_STATUSES = DONE_STATUSES


def is_done(status: str | None, fields: dict[str, Any] | None = None) -> bool:
    """Whether a Jira status (plus optional fields) means the work is finished.

    One definition, imported by every caller. Two places spelling "done"
    independently is the drift that ADR-020 exists because of -- there, a
    second hardcoded copy of the terminal set fell out of sync with the first
    and the poller resumed shipped runs forever.
    """
    if (status or "").strip().lower() in DONE_STATUSES:
        return True
    return bool((fields or {}).get("resolution"))


async def _default_update_status(key: str, status: str, done: bool) -> bool:
    from meeting_notes.graph_client import update_action_jira_status

    result: bool = await update_action_jira_status(key, status, done)
    return result


async def _default_mark_processed(record_id: str) -> None:
    from meeting_notes import db

    await db.mark_processed(record_id)


async def sync_one(
    payload: dict[str, Any],
    *,
    record_id: str,
    update_status: Any = None,
    mark_processed: Any = None,
) -> bool:
    """Sync one staged Jira issue's status into the graph.

    Returns whether an ActionItem carried this jira_key. `matched=False` is
    real signal — a Jira ticket created outside this pipeline — not a bug, so
    `jobs/pipeline_drain`'s batch counters mean something rather than always
    reporting a match.

    The record is marked processed either way: an unmatched issue does not
    need retrying, it needs a human to notice the counter.
    """
    update_status = update_status or _default_update_status
    mark_processed = mark_processed or _default_mark_processed

    key = payload["key"]
    status = payload.get("status", "")
    done = status.lower() in _DONE_STATUSES

    bound = log.bind(source_event="sync_jira_issue", jira_key=key, status=status)
    matched = bool(await update_status(key, status, done))
    await mark_processed(record_id)

    bound.info("jira_sync.issue_synced", done=done, matched=matched)
    return matched


# Jira caps `maxResults` well below the number of tickets this will accumulate,
# and a JQL string has a length limit of its own. One query for every key is
# the shape that quietly stops returning rows once the backlog outgrows it, so
# keys go over in chunks and the caller sees every one of them.
_JQL_CHUNK = 50


async def sync_open_jira_tickets(
    *, driver: Any | None = None, settings: Any | None = None, transport: Any | None = None
) -> dict[str, Any]:
    """Reconcile every ActionItem carrying a jira_key against Jira's own view.

    Reads in chunks of `_JQL_CHUNK` and writes the authenticated answer into the
    graph. No LLM involved.

    `skipped` counts keys the graph holds that are not well-formed Jira keys.
    Those never reach JQL: `key in (...)` is a query language, and a key is only
    ever as trustworthy as whatever wrote it -- which here includes a webhook
    payload. A malformed key is reported rather than interpolated.
    """
    from meeting_notes import jira_client
    from meeting_notes.config import get_settings
    from meeting_notes.graph_client import get_driver, update_action_jira_status

    settings = settings or get_settings()
    driver = driver or get_driver()

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:ActionItem)
            WHERE a.jira_key IS NOT NULL
            RETURN DISTINCT a.jira_key AS key, coalesce(a.done, false) AS done,
                   a.jira_status AS current_status
            """
        )
        items = [dict(r) async for r in result]

    if not items:
        return {"total": 0, "synced": 0, "completed": 0, "skipped": 0}

    raw_keys = [str(item["key"]) for item in items if item.get("key")]
    keys = [k for k in raw_keys if JIRA_KEY_RE.match(k)]
    skipped = len(raw_keys) - len(keys)
    if skipped:
        log.warning("jira_sync.malformed_keys_skipped", count=skipped)

    synced = 0
    completed = 0
    for start in range(0, len(keys), _JQL_CHUNK):
        chunk = keys[start : start + _JQL_CHUNK]
        jql = f"key in ({','.join(chunk)})"
        try:
            issues = await jira_client.search_issues(
                jql,
                fields=["status", "resolution"],
                max_results=len(chunk),
                settings=settings,
                transport=transport,
            )
        except Exception as exc:  # noqa: BLE001 - one bad chunk must not lose the rest
            log.warning("jira_sync.search_failed", error=str(exc), chunk_start=start)
            continue

        for issue in issues:
            key = issue.get("key")
            if not key:
                continue
            fields = issue.get("fields", {}) or {}
            status_name = (fields.get("status") or {}).get("name", "")
            done = is_done(status_name, fields)
            if await update_action_jira_status(key, status_name, done, driver=driver):
                synced += 1
                if done:
                    completed += 1

    log.info(
        "jira_sync.batch_synced",
        total=len(items), synced=synced, completed=completed, skipped=skipped,
    )
    return {"total": len(items), "synced": synced, "completed": completed, "skipped": skipped}
