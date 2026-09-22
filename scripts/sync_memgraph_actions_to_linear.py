"""Sync existing Memgraph ActionItem nodes to Linear team ONI."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from meeting_notes.config import get_settings
from meeting_notes.graph_client import get_all_actions, update_action_linear_info
from meeting_notes.linear_client import create_issue

log = structlog.get_logger()


async def sync_actions() -> None:
    settings = get_settings()
    if not settings.linear_api_key or not settings.linear_team_id:
        print("ERROR: LINEAR_API_KEY and LINEAR_TEAM_ID must be set in .env")
        return

    actions: list[dict[str, Any]] = await get_all_actions()
    unlinked = [a for a in actions if not a.get("linear_id") and not a.get("linear_identifier")]
    print(f"Found {len(actions)} total actions, {len(unlinked)} unlinked to Linear.")

    created_count = 0
    for a in unlinked:
        task = a.get("task", "")
        if not task:
            continue

        desc = (
            f"Action Item from Meeting Memory System\n\n"
            f"- **Owner:** {a.get('owner') or 'Unassigned'}\n"
            f"- **Due Date:** {a.get('due') or 'None'}\n"
            f"- **Created:** {a.get('created_at') or 'Unknown'}\n"
            f"- **Memgraph ID:** `{a.get('id')}`"
        )
        priority = a.get("priority") or "medium"
        due_date = a.get("due")

        try:
            print(f"Creating Linear issue for: {task[:60]}...")
            issue = await create_issue(
                title=task,
                description=desc,
                priority=priority,
                due_date=due_date,
                settings=settings,
            )
            ident = issue.get("identifier")
            lid = issue.get("id")
            url = issue.get("url")

            await update_action_linear_info(
                action_id=a["id"],
                linear_id=str(lid or ""),
                linear_identifier=str(ident or ""),
                linear_url=str(url or ""),
                linear_state="Todo",
            )
            created_count += 1
            print(f" -> Created {ident}: {url}")
            # Small delay to respect rate limits
            await asyncio.sleep(0.3)
        except Exception as exc:
            print(f" -> Failed to create issue for {task[:40]}: {exc}")

    print(f"\nFinished syncing {created_count} action items to Linear team {settings.linear_team_id}!")


if __name__ == "__main__":
    asyncio.run(sync_actions())
