"""Dev agent — manual trigger, preflight, and recent-run visibility.

Read routes report on `jobs/dev_agent_poll.py`'s own polling; the trigger
route exists for an ad hoc run from the dashboard between scheduled polls.
It kicks off one poll cycle in the background rather than awaiting it, since
a coding run can take much longer than an HTTP request should.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from api.deps import principal
from meeting_notes import db
from meeting_notes.access_control import Principal
from meeting_notes.config import get_settings
from meeting_notes.dev_agent import backend
from meeting_notes.dev_agent.orchestrator import poll_and_process

router = APIRouter(prefix="/dev-agent", tags=["dev-agent"])


@router.get("/preflight")
async def preflight(_: Principal = Depends(principal)) -> dict[str, Any]:
    """Whether the configured coding backend is ready to run, without starting one."""
    settings = get_settings()
    dev_backend = backend.select_backend(settings)
    try:
        detail = await backend.preflight(dev_backend, settings)
        return {"backend": dev_backend, "ok": True, "detail": detail}
    except backend.PreflightError as exc:
        return {"backend": dev_backend, "ok": False, "detail": str(exc)}


@router.get("/runs")
async def runs(
    limit: int = Query(50, ge=1, le=200), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Recent dev-agent runs, newest first, with the PR each produced."""
    items = await db.list_recent_dev_agent_runs(limit=limit)
    return {"runs": [r.model_dump(mode="json") for r in items], "count": len(items)}


@router.post("/trigger")
async def trigger(
    background_tasks: BackgroundTasks, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Run one poll cycle now instead of waiting for Cloud Scheduler.

    Returns what the cycle attempted; it does not wait for the coding run to
    finish, which can take many minutes."""
    background_tasks.add_task(poll_and_process)
    return {"status": "accepted"}
