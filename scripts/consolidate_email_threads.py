#!/usr/bin/env python3
"""Collapse per-message email rows into one staged record per thread.

The Gmail connector used to stage one record per message, so a conversation
became several Meeting nodes with overlapping decisions and the same
commitment filed as several Jira tickets. The connector now groups by thread;
this brings already-staged rows to the same shape without re-fetching from
Gmail, which would need a fresh OAuth consent.

Idempotent: a thread that is already one record is left alone, so re-running
is a no-op. Ordering comes from the RFC 2822 `Date` header, since the staged
payloads predate the connector's `internal_date`.

    python -m scripts.consolidate_email_threads --dry-run
    python -m scripts.consolidate_email_threads
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from email.utils import parsedate_to_datetime
from typing import Any

from meeting_notes import db
from meeting_notes.sources.gmail import _thread_record
from meeting_notes.utils import configure_logging


def _sort_key(payload: dict[str, Any]) -> str:
    """A lexically sortable timestamp from the message's Date header.

    Falls back to the empty string rather than raising: an unparseable date
    should cost that message its position in the thread, not the whole
    consolidation.
    """
    raw = payload.get("date") or ""
    try:
        return f"{int(parsedate_to_datetime(raw).timestamp() * 1000):013d}"
    except (TypeError, ValueError):
        return ""


def group_by_thread(records: list[Any]) -> dict[str, list[Any]]:
    """Staged rows keyed by thread. A row with no thread_id is its own thread."""
    threads: dict[str, list[Any]] = defaultdict(list)
    for record in records:
        thread_id = (record.payload or {}).get("thread_id") or record.source_id
        threads[thread_id].append(record)
    return dict(threads)


async def consolidate(dry_run: bool = False) -> dict[str, int]:
    records = await db.list_staged_by_type("email")
    threads = group_by_thread(records)
    multi = {tid: rows for tid, rows in threads.items() if len(rows) > 1}

    print(f"  {len(records)} email records in {len(threads)} threads")
    print(f"  {len(multi)} thread(s) span more than one message")
    for tid, rows in list(multi.items())[:5]:
        subject = (rows[0].payload or {}).get("subject", "")[:52]
        print(f"    {tid}: {len(rows)} messages — {subject}")

    if not multi:
        print("  nothing to consolidate")
        return {"threads": 0, "rows_removed": 0}

    replacements: list[tuple[str, dict[str, Any]]] = []
    for thread_id, rows in multi.items():
        messages = [
            {
                "id": r.source_id,
                "subject": (r.payload or {}).get("subject", ""),
                "from": (r.payload or {}).get("from", ""),
                "to": (r.payload or {}).get("to", ""),
                "cc": (r.payload or {}).get("cc", ""),
                "date": (r.payload or {}).get("date", ""),
                "body": (r.payload or {}).get("body", ""),
                # The connector orders on this; synthesised here from the header.
                "internal_date": _sort_key(r.payload or {}),
            }
            for r in rows
        ]
        # Built by the connector's own helper so the consolidated payload and a
        # freshly fetched one cannot drift apart.
        replacements.append((thread_id, _thread_record(thread_id, messages, "email").payload))

    old_ids = [r.source_id for rows in multi.values() for r in rows]
    if dry_run:
        print(f"  DRY RUN: would replace {len(old_ids)} rows with {len(replacements)}")
        return {"threads": len(replacements), "rows_removed": len(old_ids) - len(replacements)}

    written = await db.replace_staged_records("email", old_ids, replacements)
    print(f"  replaced {len(old_ids)} rows with {written} thread records")
    return {"threads": written, "rows_removed": len(old_ids) - written}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="consolidate_email_threads", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)
    configure_logging()

    async def run() -> int:
        try:
            await consolidate(dry_run=args.dry_run)
        finally:
            await db.close_pool()
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
