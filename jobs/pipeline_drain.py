#!/usr/bin/env python3
"""Cloud Run Job entrypoint — drain one batch of staged records.

Thin by design (CLAUDE.md): all logic lives in meeting_notes/pipeline_drain.py.
"""

import asyncio

from meeting_notes import db
from meeting_notes.config import get_settings
from meeting_notes.pipeline_drain import drain_batch


def main() -> int:
    async def run() -> int:
        settings = get_settings()
        try:
            records = await db.claim_batch(settings.pipeline_batch_size)
            if not records:
                print("  pipeline_drain: nothing to claim")
                return 0
            result = await drain_batch(records)
            print(f"  pipeline_drain: processed {result.processed}, errors {result.errors}")
            return 1 if result.errors else 0
        finally:
            await db.close_pool()

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
