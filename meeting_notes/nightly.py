"""Nightly graph maintenance — the orchestration, not the entrypoint.

Sits alongside `pipeline.py`: that one orchestrates a single record, this one
orchestrates the scheduled whole-graph passes. `jobs/nightly.py` stays a thin
`main()` over this, per CLAUDE.md's rule that business logic lives in the
package.

Steps are independent and failures are per-step: the full algorithm pass
hitting a transient Memgraph conflict must not cost us the night's decay and
consolidation.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

STEPS: tuple[str, ...] = ("reresolve", "algorithms", "consolidate", "decay", "procedures")


async def run_step(name: str) -> Any:
    """Run one named step. Imports are local so a single step does not drag in
    every memory module."""
    from meeting_notes import graph_algorithms, person_resolver
    from meeting_notes.config import get_settings
    from meeting_notes.memory import episodic, procedural, semantic

    if name == "reresolve":
        # Runs FIRST: resolution is order-dependent, so clearing the stale part
        # of the review queue before the algorithms means PageRank and community
        # detection see the fuller attendance graph rather than a snapshot of
        # what happened to be knowable at ingest time.
        return await person_resolver.reresolve_reviews(
            roster_path=get_settings().person_roster_path or None
        )
    if name == "algorithms":
        return await graph_algorithms.run_full()
    if name == "consolidate":
        return await semantic.consolidate()
    if name == "decay":
        return await episodic.decay_relevance()
    if name == "procedures":
        return await procedural.discover_procedures()
    raise ValueError(f"unknown step {name!r}")


async def run(steps: tuple[str, ...] = STEPS, *, step_fn: Any = None) -> dict[str, Any]:
    """Run each step, catching failures individually.

    Returns a per-step outcome map so the caller can report partial success
    rather than a single pass/fail.
    """
    step_fn = step_fn or run_step
    results: dict[str, Any] = {}
    failures = 0

    for name in steps:
        try:
            results[name] = await step_fn(name)
            log.info("nightly.step_done", nightly_step=name, result=results[name])
        except Exception as exc:  # noqa: BLE001 - one bad step must not sink the night
            failures += 1
            results[name] = None
            log.error("nightly.step_failed", nightly_step=name, error=str(exc))

    log.info("nightly.done", steps=len(steps), failures=failures)
    return {"results": results, "failures": failures, "steps": len(steps)}
