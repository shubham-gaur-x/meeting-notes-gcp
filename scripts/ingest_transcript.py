#!/usr/bin/env python3
"""Ingest any meeting transcript directly into meeting-notes-gcp.

Stages the transcript into PostgreSQL raw_records and immediately drains
the record through the pipeline to extract entities, decisions, and action items
and merge them into Memgraph.

Usage examples:
  uv run python scripts/ingest_transcript.py --title "Architecture Review" --file /path/to/transcript.txt
  uv run python scripts/ingest_transcript.py --title "Client Sprint Planning" --date "2026-09-18" --file notes.md
  uv run python scripts/ingest_transcript.py --title "Quick 1:1 Sync" --text "Michael: Let's ship the PR.\nAlex: Agreed."
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from meeting_notes import db
from meeting_notes.models import StagedRecord
from meeting_notes.pipeline_drain import drain_batch


async def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a meeting transcript into the memory graph.")
    parser.add_argument("--title", required=True, help="Title of the meeting")
    parser.add_argument("--file", type=Path, help="Path to transcript file (.txt, .md, .vtt)")
    parser.add_argument("--text", type=str, help="Raw transcript text content")
    parser.add_argument("--date", type=str, help="ISO date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--source-id", type=str, help="Optional unique source identifier")

    args = parser.parse_args()

    if not args.file and not args.text:
        print("Error: either --file or --text must be specified.", file=sys.stderr)
        return 1

    content = ""
    if args.file:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            return 1
        content = args.file.read_text(encoding="utf-8").strip()
    elif args.text:
        content = args.text.strip()

    if not content:
        print("Error: transcript content is empty.", file=sys.stderr)
        return 1

    meeting_date = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    source_id = args.source_id or f"manual-{meeting_date}-{uuid.uuid4().hex[:8]}"

    payload = {
        "title": args.title,
        "original_title": args.title,
        "text": content,
        "start_time": f"{meeting_date}T12:00:00Z",
    }

    try:
        record_id = await db.stage_record(source_id, "meet", payload)
        if not record_id:
            print(f"Notice: A record with source_id '{source_id}' was already staged.")
            return 0

        print(f"✓ Staged record '{record_id}' (source_id: {source_id})")

        staged_record = StagedRecord(
            id=record_id,
            source_id=source_id,
            source_type="meet",
            payload=payload,
            fetched_at=datetime.now(UTC).isoformat(),
            processed=False,
        )

        print(f"Processing transcript through entity & action item extraction...")
        drain_result = await drain_batch([staged_record])
        await db.mark_processed(record_id)

        if drain_result.errors:
            print(f"⚠ Finished with {drain_result.errors} processing error(s):")
            for err in drain_result.error_details:
                print(f"  - {err}")
            return 1

        print(f"✓ Successfully processed and merged meeting: '{args.title}' into Memgraph")
        return 0
    finally:
        await db.close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
