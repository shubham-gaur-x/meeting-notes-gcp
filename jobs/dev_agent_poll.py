#!/usr/bin/env python3
"""Autonomous dev agent — Cloud Run Job, triggered by Cloud Scheduler.

Thin entrypoint (CLAUDE.md): one poll cycle per invocation, no in-process
scheduler. All orchestration lives in `meeting_notes.dev_agent.orchestrator`.
"""

from __future__ import annotations

import asyncio

from meeting_notes import db
from meeting_notes.dev_agent.orchestrator import poll_and_process
from meeting_notes.graph_client import close_driver
from meeting_notes.utils import configure_logging


async def _run() -> int:
    try:
        result = await poll_and_process()
    finally:
        await db.close_pool()
        await close_driver()
    reason = result.get("reason")
    if reason:
        print(f"  dev_agent_poll: attempted 0 ({reason})")
        return 1
    print(f"  dev_agent_poll: attempted {result['attempted']}")
    return 0


def main() -> int:
    configure_logging()
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
