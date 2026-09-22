#!/usr/bin/env python3
"""Google Meet historical conference record & transcript backfill.

Directly queries the Google Meet API v2 for past conference records and their
transcripts, stages them, and drains them into Memgraph.

Usage:
  PYTHONPATH=. uv run python jobs/ingest_meet_history.py
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from meeting_notes import db, google_auth
from meeting_notes.config import get_settings
from meeting_notes.models import StagedRecord
from meeting_notes.pipeline_drain import drain_batch
from meeting_notes.sources.meet import MEET_API, entries_to_text

log = structlog.get_logger()


async def fetch_meet_history(access_token: str, max_records: int = 50) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. List conference records
        res = await client.get(
            f"{MEET_API}/conferenceRecords", headers=headers, params={"pageSize": max_records}
        )
        if res.status_code != 200:
            log.error("meet_history.list_failed", status=res.status_code, body=res.text)
            return []

        data = res.json()
        conf_records = data.get("conferenceRecords") or []
        log.info("meet_history.found_conferences", count=len(conf_records))

        results = []
        for cr in conf_records:
            cr_name = cr.get("name", "")  # conferenceRecords/{id}
            if not cr_name:
                continue

            # 2. List transcripts for this conference record
            t_res = await client.get(f"{MEET_API}/{cr_name}/transcripts", headers=headers)
            if t_res.status_code != 200:
                continue

            transcripts = t_res.json().get("transcripts") or []
            for t in transcripts:
                t_name = t.get("name", "")
                if not t_name:
                    continue

                # 3. Fetch transcript entries
                entries_res = await client.get(
                    f"{MEET_API}/{t_name}/entries", headers=headers, params={"pageSize": 100}
                )
                if entries_res.status_code != 200:
                    continue

                entries = entries_res.json().get("transcriptEntries") or []
                text = entries_to_text(entries)
                if not text.strip():
                    continue

                results.append({
                    "source_id": cr_name.replace("/", "-"),
                    "title": cr.get("space", "Google Meet Sync"),
                    "start_time": cr.get("startTime", ""),
                    "text": text,
                })

        return results


async def main() -> int:
    settings = get_settings()
    try:
        token = await google_auth.get_access_token(settings)
    except Exception as e:
        print(f"Google Auth error: {e}")
        print("To refresh/re-consent your token, run: uv run python scripts/auth_spike.py --reconsent")
        return 1

    print("Fetching conference records from Google Meet API...")
    items = await fetch_meet_history(token)
    if not items:
        print("No recent Google Meet transcripts found in conference records.")
        return 0

    staged_records = []
    for item in items:
        payload = {
            "title": item["title"],
            "text": item["text"],
            "start_time": item["start_time"],
        }
        rec_id = await db.stage_record(item["source_id"], "meet", payload)
        if rec_id:
            staged_records.append(StagedRecord(
                id=rec_id,
                source_id=item["source_id"],
                source_type="meet",
                payload=payload,
                fetched_at=item["start_time"] or "",
                processed=False,
            ))

    print(f"Staged {len(staged_records)} new transcript(s). Draining into graph...")
    if staged_records:
        result = await drain_batch(staged_records)
        print(f"Drained: processed {result.processed}, errors {result.errors}")

    await db.close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
