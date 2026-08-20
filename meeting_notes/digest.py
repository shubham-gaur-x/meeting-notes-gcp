"""Weekly digest — a rollup over the last seven days.

Pure shaping over one graph read, so it is testable without a database and
the endpoint stays a one-liner.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

DEFAULT_PERIOD_DAYS = 7


def shape(activity: dict[str, Any], days: int = DEFAULT_PERIOD_DAYS) -> dict[str, Any]:
    """Turn raw period activity into the digest. Pure — no I/O."""
    meetings = activity.get("meetings") or []
    decisions = activity.get("decisions") or []
    action_items = activity.get("action_items") or []

    open_actions = [a for a in action_items if not a.get("done")]
    closed_actions = [a for a in action_items if a.get("done")]
    high_priority = [a for a in open_actions if a.get("priority") == "high"]

    return {
        "period": f"last_{days}_days",
        "summary": {
            "total_meetings": len(meetings),
            "total_decisions": len(decisions),
            "total_action_items": len(action_items),
            "open_action_items": len(open_actions),
            "closed_action_items": len(closed_actions),
            "high_priority_open": len(high_priority),
        },
        "meetings": meetings,
        "decisions": decisions,
        "action_items": {
            "open": open_actions,
            "closed": closed_actions,
            "high_priority": high_priority,
        },
    }


async def weekly_digest(days: int = DEFAULT_PERIOD_DAYS, *, fetch: Any = None) -> dict[str, Any]:
    if fetch is None:
        from meeting_notes import graph_client

        fetch = graph_client.get_period_activity
    return shape(await fetch(days=days), days)
