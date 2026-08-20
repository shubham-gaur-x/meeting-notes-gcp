#!/usr/bin/env python3
"""Nightly graph maintenance — Cloud Run Job, triggered by Cloud Scheduler.

Thin entrypoint: every step lives in the package (CLAUDE.md). Steps are
selectable with `--step` so Scheduler can stagger the expensive ones, and so a
single failing stage can be re-run without repeating the rest.

Each step is independent and failures are per-step: the full algorithm pass
taking a transient Memgraph conflict must not cost us the night's decay and
consolidation.
"""

from __future__ import annotations

import argparse
import asyncio

import structlog

from meeting_notes import graph_algorithms
from meeting_notes.config import get_settings
from meeting_notes.memory import episodic, procedural, semantic
from meeting_notes.utils import configure_logging

log = structlog.get_logger()

STEPS = ("algorithms", "consolidate", "decay", "procedures")


async def run_step(name: str) -> dict:
    if name == "algorithms":
        return await graph_algorithms.run_full()
    if name == "consolidate":
        return await semantic.consolidate()
    if name == "decay":
        return await episodic.decay_relevance()
    if name == "procedures":
        return await procedural.discover_procedures()
    raise ValueError(f"unknown step {name!r}")


async def run(steps: tuple[str, ...]) -> int:
    settings = get_settings()
    log.info("nightly.start", steps=list(steps), memgraph=settings.memgraph_host)

    failures = 0
    for name in steps:
        try:
            result = await run_step(name)
            log.info("nightly.step_done", nightly_step=name, result=result)
        except Exception as exc:  # noqa: BLE001 - one bad step must not sink the night
            failures += 1
            log.error("nightly.step_failed", nightly_step=name, error=str(exc))

    from meeting_notes.graph_client import close_driver

    await close_driver()

    log.info("nightly.done", steps=len(steps), failures=failures)
    print(f"  nightly: {len(steps) - failures}/{len(steps)} steps ok")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightly", description=__doc__)
    parser.add_argument(
        "--step", action="append", choices=STEPS,
        help="run only this step (repeatable). Default: all, in order.",
    )
    args = parser.parse_args(argv)
    configure_logging()
    return asyncio.run(run(tuple(args.step) if args.step else STEPS))


if __name__ == "__main__":
    raise SystemExit(main())
