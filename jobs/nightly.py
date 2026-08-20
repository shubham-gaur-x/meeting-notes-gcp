#!/usr/bin/env python3
"""Nightly graph maintenance — Cloud Run Job, triggered by Cloud Scheduler.

Thin entrypoint. The orchestration lives in `meeting_notes.nightly`.
`--step` is repeatable so Scheduler can stagger the expensive passes and a
single failed stage can be re-run on its own.
"""

from __future__ import annotations

import argparse
import asyncio

from meeting_notes import nightly
from meeting_notes.graph_client import close_driver
from meeting_notes.utils import configure_logging


async def _run(steps: tuple[str, ...]) -> int:
    try:
        outcome = await nightly.run(steps)
    finally:
        await close_driver()
    ok = outcome["steps"] - outcome["failures"]
    print(f"  nightly: {ok}/{outcome['steps']} steps ok")
    return 1 if outcome["failures"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightly", description=__doc__)
    parser.add_argument("--step", action="append", choices=nightly.STEPS)
    args = parser.parse_args(argv)
    configure_logging()
    return asyncio.run(_run(tuple(args.step) if args.step else nightly.STEPS))


if __name__ == "__main__":
    raise SystemExit(main())
