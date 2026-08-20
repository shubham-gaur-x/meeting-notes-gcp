#!/usr/bin/env python3
"""Record `fake`-backend fixtures against a real LLM (ADR-014).

ADR-014 promises that a deliberate prompt change is "one command rather than
hand-authored JSON". This is that command.

    make record-fixtures LLM=gemini

It reads every meeting in `sample_data/meetings/`, runs each through the real
backend at temperature 0.0, and writes one fixture per prompt keyed exactly
as `llm_client.fixture_key` computes it. Tier 0 then replays them offline.

Deliberately refuses to run against `fake` — recording from the replayer would
either fail on a miss or copy fixtures onto themselves.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from meeting_notes import extractor, llm_client
from meeting_notes.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "sample_data" / "meetings"


def load_corpus(directory: Path) -> list[dict[str, Any]]:
    """Every meeting in the corpus, sorted for a stable recording order."""
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def prompts_for(record: dict[str, Any]) -> tuple[str, str]:
    """The exact (system, user) pair `extract_meeting` will later send.

    Derived from the same helpers the extractor uses, so the recorded key
    cannot drift from the key looked up at replay time. This is the whole
    reason recording is a script and not a manual step.
    """
    system = extractor.build_system_prompt(record.get("type_hint"))
    user = (
        f"Extract meeting information from this {record['source_type']}:"
        f"\n\n{record['text']}"
    )
    return system, user


def write_fixture(out_dir: Path, key: str, response: dict[str, Any]) -> None:
    """Persist one fixture. Sync by design — kept out of the async path so the
    event loop is never blocked on disk I/O."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{key}.json").write_text(
        json.dumps(response, indent=2, sort_keys=True), encoding="utf-8"
    )


async def fetch_one(record: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Call the real model for one corpus entry."""
    system, user = prompts_for(record)
    response = await llm_client.chat_json(system, user, temperature=0.0, settings=settings)
    if response is None:
        raise RuntimeError(
            f"{record.get('name', '?')}: the model returned unparseable output. "
            "Recording a null fixture would bake that failure in permanently."
        )
    return response


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="record_fixtures",
        description="Record fake-backend fixtures against a real LLM.",
    )
    parser.add_argument(
        "--force", action="store_true", help="re-record fixtures that already exist"
    )
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    if settings.llm_backend == "fake":
        print(
            "  LLM_BACKEND is 'fake' — there is nothing to record from.\n"
            "  Set a real backend first, e.g.:\n"
            "    LLM_BACKEND=gemini GEMINI_API_KEY=... make record-fixtures\n"
            "  A free key: https://aistudio.google.com/apikey"
        )
        return 1

    if not args.corpus.exists():
        print(f"  No corpus at {args.corpus}")
        return 1

    corpus = load_corpus(args.corpus)
    if not corpus:
        print(f"  No meetings in {args.corpus}")
        return 1

    out_dir = llm_client.DEFAULT_FIXTURE_DIR

    async def run() -> int:
        print(f"  recording {len(corpus)} meeting(s) via '{settings.llm_backend}' -> {out_dir}")
        written = skipped = 0
        for record in corpus:
            system, user = prompts_for(record)
            key = llm_client.fixture_key(system, user, 0.0)
            name = record.get("name", "?")

            if args.force:
                (out_dir / f"{key}.json").unlink(missing_ok=True)

            if (out_dir / f"{key}.json").exists():
                print(f"    exists    {name:32s} {key}")
                skipped += 1
                continue

            write_fixture(out_dir, key, await fetch_one(record, settings))
            print(f"    recorded  {name:32s} {key}")
            written += 1
        print(f"  {written} recorded, {skipped} already present")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
