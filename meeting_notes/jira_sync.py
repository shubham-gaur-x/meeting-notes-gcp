"""Jira status -> graph. The reverse direction from jira_pusher.

Ported from v5's `jira_agent.py`. Consumes staged `source_type="jira"` rows
(the same staging table everything else uses, ADR-018) rather than a
dedicated raw table.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

_DONE_STATUSES = ("done", "closed", "resolved")


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


async def sync_open_jira_tickets(
    *, driver: Any | None = None, settings: Any | None = None, transport: Any | None = None
) -> dict[str, Any]:
    """Query Jira Cloud for the current status of all open action items and update Memgraph in batch.

    Runs a single bulk JQL query against Jira and updates matching ActionItem nodes.
    Zero LLM tokens are used ($0.00 cost).
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
            RETURN DISTINCT a.jira_key AS key, coalesce(a.done, false) AS done, a.jira_status AS current_status
            """
        )
        items = [dict(r) async for r in result]

    if not items:
        return {"total": 0, "synced": 0, "completed": 0}

    keys = [item["key"] for item in items if item.get("key")]
    jql = f"key in ({','.join(keys)})"

    try:
        issues = await jira_client.search_issues(
            jql, fields=["status", "resolution"], max_results=len(keys), settings=settings, transport=transport
        )
    except Exception as exc:
        log.warning("jira_sync.search_failed", error=str(exc))
        return {"total": len(items), "synced": 0, "completed": 0, "error": str(exc)}

    synced = 0
    completed = 0
    for issue in issues:
        key = issue.get("key")
        status_name = issue.get("fields", {}).get("status", {}).get("name", "")
        done = status_name.lower() in _DONE_STATUSES or bool(issue.get("fields", {}).get("resolution"))
        if key:
            matched = await update_action_jira_status(key, status_name, done, driver=driver)
            if matched:
                synced += 1
                if done:
                    completed += 1

    log.info("jira_sync.batch_synced", total=len(items), synced=synced, completed=completed)
    return {"total": len(items), "synced": synced, "completed": completed}
