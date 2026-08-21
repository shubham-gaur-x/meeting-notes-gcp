"""One ingestion run, wired end to end.

This exists so `jobs/*` stay thin. CLAUDE.md: a job file past ~50 lines means
logic has leaked out of the package, and the natural place for that leak is
exactly this wiring — get a token, read the watermark, fetch, stage, advance.
Doing it once here keeps all four jobs to a `main()`.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import structlog

from meeting_notes import db, google_auth
from meeting_notes.config import Settings, get_settings
from meeting_notes.models import SourceType
from meeting_notes.sources.base import FetchedRecord, Source, StageResult, stage_all

log = structlog.get_logger()


async def _stage(record: FetchedRecord) -> str | None:
    # cast: Source.source_type is the canonical SourceType literal by
    # construction; a test asserts every source uses one of its values.
    source_type = cast(SourceType, record.source_type)
    return await db.stage_record(record.source_id, source_type, record.payload)


async def run_source(source: Source, settings: Settings | None = None) -> StageResult:
    """Fetch from one source and stage what it returns."""
    settings = settings or get_settings()
    since = await db.get_watermark(source.source_type)
    log.info("ingest.start", source=source.source_type, since=since)

    result = await stage_all(source, _stage, db.set_watermark, since=since)

    log.info(
        "ingest.done",
        source=source.source_type,
        staged=result.staged,
        skipped=result.skipped,
    )
    return result


async def build_google_source(name: str, settings: Settings | None = None) -> Any:
    """Construct a Google-backed source with a fresh access token.

    Token refresh raises TokenExpiredError rather than returning None, so a dead
    token surfaces as a failed job rather than a successful run that staged
    nothing.
    """
    settings = settings or get_settings()
    token = await google_auth.get_access_token(settings)

    if name == "gmail":
        from meeting_notes.sources.gmail import GmailSource

        return GmailSource(access_token=token)
    if name == "calendar":
        from meeting_notes.sources.calendar import CalendarSource

        return CalendarSource(access_token=token)
    if name == "meet":
        from meeting_notes.sources.meet import MeetSource

        return MeetSource(
            access_token=token, subscription=settings.meet_pubsub_subscription
        )
    raise ValueError(f"unknown Google source {name!r}")


def run_job(name: str) -> int:
    """Entrypoint body shared by every ingest job."""

    async def main() -> int:
        settings = get_settings()
        try:
            if name == "jira":
                from meeting_notes.sources.jira import JiraSource

                source: Any = JiraSource(settings=settings)
                result = await run_source(source, settings)
            else:
                source = await build_google_source(name, settings)
                result = await run_source(source, settings)
                # Meet acks only after staging succeeded — see sources/meet.py.
                if hasattr(source, "acknowledge"):
                    await source.acknowledge()
        finally:
            await db.close_pool()

        print(f"  {name}: staged {result.staged}, skipped {result.skipped}")
        return 0

    return asyncio.run(main())
