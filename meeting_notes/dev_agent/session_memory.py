"""Resumable session memory: a record of each dev-agent run, kept across attempts.

Modeled on Matteo's `AgentMemory` ontology (Quick Reference + confidence
keywords, Work Completed, Files Changed, Blockers, Next Actions, Resume
Context, Raw Notes). Persisted via `meeting_notes.db.set_dev_agent_session_memory`
(`dev_agent_runs.state_payload`) rather than a second database module — this
package owns no SQL of its own (CLAUDE.md).

Kept in Postgres rather than the graph's `AgentRun` node because the resume
read happens *before* a run, on a failed attempt where no PR — and so no
`AgentRun` node — exists yet.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()


def files_from_diff(diff: str) -> list[str]:
    """Changed file paths from a unified diff (the `b/` side of each `diff --git`)."""
    files: list[str] = []
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            if len(parts) == 2 and parts[1].strip():
                files.append(parts[1].strip())
    return files


def build_memory(
    ticket: dict[str, Any],
    *,
    outcome: str,
    pr: dict[str, Any] | None = None,
    files_changed: list[str] | None = None,
    error: str | None = None,
    verdict: Any = None,
    raw_notes: str = "",
) -> dict[str, Any]:
    """Assemble the memory record. `outcome` is 'pr_opened' or 'failed'."""
    key = ticket.get("key", "")
    summary = ticket.get("summary", "")
    files_changed = files_changed or []
    blockers: list[str] = []
    next_actions: list[str] = []

    if outcome == "pr_opened":
        work = [f"Opened PR {pr['html_url']}"] if pr else ["Opened a pull request"]
        if verdict is not None and getattr(verdict, "checked", False) and not verdict.passed:
            next_actions.append(
                "Automated check did not confirm the diff addresses the ticket — human review needed."
            )
        resume = (
            f"A PR is already open for {key}"
            + (f": {pr['html_url']}" if pr else "")
            + f". Files touched: {', '.join(files_changed) or 'unknown'}. "
            "If this ticket is reopened, refine that PR rather than starting from scratch."
        )
    else:  # failed
        work = []
        if error:
            blockers.append(error[:500])
        next_actions.append("Investigate the blocker below, then retry.")
        resume = (
            f"Previous attempt on {key} failed: {(error or 'unknown error')[:300]}. "
            f"Files touched so far: {', '.join(files_changed) or 'none recorded'}. "
            "Continue from there; do not redo work that already succeeded."
        )

    keywords = sorted({w.lower().strip(".,:;()") for w in summary.split() if len(w) > 3})[:8]
    return {
        "quick_reference": f"{key}: {outcome} — {summary}",
        "confidence_keywords": keywords,
        "decisions": [],
        "work_completed": work,
        "files_changed": files_changed,
        "blockers": blockers,
        "next_actions": next_actions,
        "resume_context": resume,
        "raw_notes": raw_notes or "",
        "outcome": outcome,
    }


async def record(
    ticket: dict[str, Any],
    *,
    outcome: str,
    pr: dict[str, Any] | None = None,
    files_changed: list[str] | None = None,
    error: str | None = None,
    verdict: Any = None,
    raw_notes: str = "",
    save: Any = None,
) -> dict[str, Any]:
    """Build and persist the session memory (best-effort). Returns the memory dict."""
    memory = build_memory(
        ticket, outcome=outcome, pr=pr, files_changed=files_changed,
        error=error, verdict=verdict, raw_notes=raw_notes,
    )
    if save is None:
        from meeting_notes.db import set_dev_agent_session_memory as save
    try:
        await save(ticket.get("key", ""), memory)
    except Exception:
        log.warning("session_memory.save_failed", exc_info=True)
    return memory


async def load_resume_context(ticket_key: str, load: Any = None) -> str | None:
    """The prior attempt's resume_context for injection into a retry, or None."""
    if load is None:
        from meeting_notes.db import get_dev_agent_session_memory as load
    try:
        memory = await load(ticket_key)
    except Exception:
        return None
    if not memory:
        return None
    context: str | None = memory.get("resume_context")
    return context or None
