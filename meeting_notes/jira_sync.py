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
