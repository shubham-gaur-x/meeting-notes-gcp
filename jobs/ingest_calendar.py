#!/usr/bin/env python3
"""Cloud Run Job entrypoint — ingest calendar.

Thin by design (CLAUDE.md): all logic lives in meeting_notes/sources/.
"""

from meeting_notes.sources.runner import run_job

if __name__ == "__main__":
    raise SystemExit(run_job("calendar"))
