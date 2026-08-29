#!/usr/bin/env python3
"""Score two revisions of `meeting_notes/classifier.py` against real staged data.

The classifier is the cheap gate in front of extraction: below
`classifier_score_threshold` a record is marked processed and no LLM is ever
called. That makes a change to it easy to reason about wrongly — a new noise
pattern can look obviously correct in a unit test and still change nothing on
real traffic, or change the wrong thing.

This answers one question: **for records already staged, which gate decisions
does a change actually flip?** It is a pure function over rows already in
Postgres — no Gmail call, no LLM, no graph write, no Jira. Running it costs
nothing and mutates nothing.

    python -m scripts.ab_classifier                     # working tree vs master
    python -m scripts.ab_classifier --base HEAD~1
    python -m scripts.ab_classifier --source calendar
    python -m scripts.ab_classifier --unprocessed-only  # only rows not yet drained

Subjects are withheld unless `--show-subjects` is passed, the same way
`scripts/doctor.py` reports secrets as set/unset and never prints a value:
staged payloads are real mail, and the default output is meant to be safe to
paste into a pull request.

Note the asymmetry in what is compared. `--base` is read out of git via
`git show`, while the head side is whatever `meeting_notes.classifier` imports
right now — so an uncommitted edit is included without needing a commit first.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from meeting_notes import classifier as head_classifier
from meeting_notes import db
from meeting_notes.config import get_settings
from meeting_notes.models import StagedRecord
from meeting_notes.pipeline import adapter_for

CLASSIFIER_PATH = "meeting_notes/classifier.py"
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_classifier_at_revision(revision: str) -> ModuleType:
    """Import `classifier.py` as it existed at `revision`, without checking it out.

    Loaded under a private module name so it cannot collide with the already
    imported `meeting_notes.classifier`. The module is dependency-free by
    design (`re` and `typing` only), which is what makes this safe.
    """
    try:
        source = subprocess.run(
            ["git", "show", f"{revision}:{CLASSIFIER_PATH}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"cannot read {CLASSIFIER_PATH} at {revision!r}: {exc.stderr.strip()}"
        ) from exc

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        temp_path = fh.name

    spec = importlib.util.spec_from_file_location("_classifier_base", temp_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {CLASSIFIER_PATH} at {revision!r}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Scored:
    """One staged record scored by both revisions."""

    source_id: str
    title: str
    base_score: float
    head_score: float
    base_passes: bool
    head_passes: bool

    @property
    def flipped(self) -> bool:
        return self.base_passes != self.head_passes

    @property
    def moved(self) -> bool:
        return abs(self.base_score - self.head_score) > 1e-9


def score_records(
    records: list[StagedRecord],
    source_type: str,
    base: ModuleType,
    head: ModuleType,
    threshold: float,
) -> list[Scored]:
    """Score every record with both revisions, through the real adapter."""
    adapter = adapter_for(source_type)
    scored: list[Scored] = []
    for record in records:
        text = adapter.text(record.payload)
        metadata = adapter.classify_metadata(record.payload)
        base_score = base.classify(text, metadata)
        head_score = head.classify(text, metadata)
        scored.append(
            Scored(
                source_id=record.source_id,
                title=adapter.router_title(record.payload),
                base_score=base_score,
                head_score=head_score,
                base_passes=base_score >= threshold,
                head_passes=head_score >= threshold,
            )
        )
    return scored


def select_records(records: list[StagedRecord], unprocessed_only: bool) -> list[StagedRecord]:
    """Narrow the corpus. Split out from `main` so it is testable without a database."""
    if not unprocessed_only:
        return records
    return [r for r in records if not r.processed]


def label(item: Scored, show_subjects: bool) -> str:
    """Identify a record without leaking mail contents by default."""
    return item.title[:58] if show_subjects else item.source_id


def render(scored: list[Scored], *, base: str, threshold: float, show_subjects: bool) -> None:
    flipped = [s for s in scored if s.flipped]
    moved = [s for s in scored if s.moved and not s.flipped]
    kept = sum(1 for s in scored if s.head_passes and not s.flipped)
    dropped = sum(1 for s in scored if not s.head_passes and not s.flipped)

    # These three are disjoint and sum to the corpus. `moved` deliberately is
    # not a fourth bucket -- it is a subset of the two unchanged rows above,
    # and printing it alongside them as a peer made the numbers stop adding up.
    print(f"records: {len(scored)}   base: {base}   threshold: {threshold}\n")
    print(f"  extracted by both:      {kept}")
    print(f"  dropped by both:        {dropped}")
    print(f"  GATE DECISION CHANGED:  {len(flipped)}")
    print(f"  {'':22}  {'-' * len(str(len(scored)))}")
    print(f"  {'':22}  {len(scored)}\n")
    print(f"  of the unchanged, {len(moved)} scored differently without crossing the gate\n")

    for item in sorted(flipped, key=lambda s: -s.base_score):
        direction = (
            "EXTRACTED -> DROPPED"
            if item.base_passes
            else "DROPPED -> EXTRACTED   <-- new work for the LLM"
        )
        print(f"  {direction}")
        print(f"    {label(item, show_subjects)}")
        print(f"    score: {item.base_score:.2f} -> {item.head_score:.2f}\n")

    if moved:
        print("  scores that moved without changing the decision:")
        for item in sorted(moved, key=lambda s: -s.base_score):
            print(
                f"    {item.base_score:.2f} -> {item.head_score:.2f}  "
                f"{label(item, show_subjects)}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ab_classifier",
        description="A/B two classifier revisions over real staged records.",
    )
    parser.add_argument(
        "--base",
        default="master",
        help="git revision to compare against (default: master)",
    )
    parser.add_argument(
        "--source",
        default="email",
        choices=("email", "calendar", "meet"),
        help="which staged source to score (default: email)",
    )
    parser.add_argument(
        "--unprocessed-only",
        action="store_true",
        help="score only rows the pipeline has not drained yet",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="override classifier_score_threshold from settings",
    )
    parser.add_argument(
        "--show-subjects",
        action="store_true",
        help="print subjects instead of source ids (reveals mail contents)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    threshold = args.threshold if args.threshold is not None else settings.classifier_score_threshold

    async def run() -> int:
        try:
            records = await db.list_staged_by_type(args.source)
        finally:
            await db.close_pool()

        records = select_records(records, args.unprocessed_only)
        if not records:
            print(f"no staged {args.source} records to score")
            return 1

        base = load_classifier_at_revision(args.base)
        scored = score_records(records, args.source, base, head_classifier, threshold)
        render(scored, base=args.base, threshold=threshold, show_subjects=args.show_subjects)
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
