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

STEPS: tuple[str, ...] = (
    "reresolve", "algorithms", "consolidate", "preferences", "decay", "procedures",
    "quality",
)


async def _score_quality(get_inputs: Any = None, set_quality: Any = None) -> dict[str, int]:
    """Score every meeting and write the result back.

    Runs last: `action_completion` reads `ActionItem.done`, which the Jira sync
    updates, so scoring before the rest of the night would grade yesterday's
    state.

    The population rates are computed across the whole corpus first because the
    yield components are percentile ranks — a meeting's decision rate only means
    something relative to the others.
    """
    from meeting_notes import graph_client, meeting_quality

    get_inputs = get_inputs or graph_client.get_meetings_quality_inputs
    set_quality = set_quality or graph_client.set_meeting_quality

    rows = await get_inputs()
    decision_rates = [
        r["decision_count"] / (r["duration_minutes"] / 60)
        for r in rows
        if r.get("duration_minutes")
    ]
    action_rates = [
        r["action_count"] / (r["duration_minutes"] / 60)
        for r in rows
        if r.get("duration_minutes")
    ]
    population = {"decision": decision_rates, "action": action_rates}

    scored = failed = 0
    for row in rows:
        try:
            result = meeting_quality.compute_quality(
                {
                    "attended": row.get("attendee_count"),
                    "invited": row.get("attendee_count"),
                    "n_decisions": row.get("decision_count", 0),
                    "n_actions": row.get("action_count", 0),
                    "n_actions_done": row.get("actions_done", 0),
                    "duration_minutes": row.get("duration_minutes"),
                    "agenda_text": row.get("summary", ""),
                    "recurrence_scores": [],
                },
                population,
            )
            await set_quality(row["id"], result["quality_score"], result["components"])
            scored += 1
        except Exception as exc:  # noqa: BLE001 - one bad meeting must not sink the pass
            failed += 1
            log.warning("nightly.quality_failed", meeting_id=row.get("id"), error=str(exc))

    return {"scored": scored, "failed": failed}


async def run_step(name: str, **kwargs: Any) -> Any:
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
    if name == "preferences":
        # Once per person over their history, not once per attendee per
        # meeting -- "how someone likes to work" is not a per-meeting trait.
        return await semantic.consolidate_preferences()
    if name == "decay":
        return await episodic.decay_relevance()
    if name == "procedures":
        return await procedural.discover_procedures()
    if name == "quality":
        return await _score_quality(**kwargs)
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
