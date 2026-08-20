"""The `Source` protocol and the one staging loop every connector shares.

v5 had a `TranscriptSource` protocol, but it is a different concept despite
the similar name: it read rows *already staged* in Postgres, because Airbyte
did the fetching. Here a Source fetches from upstream and stages, since v6
owns every connector.

Incremental behaviour lives here rather than in each connector, so the
watermark ordering rule is implemented once instead of four times with three
subtle variations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

log = structlog.get_logger()


@dataclass(frozen=True)
class FetchedRecord:
    """One raw record, ready to stage.

    `watermark` is the source's own ordering value for this record — a Gmail
    internalDate, a Calendar `updated` timestamp, a Jira `updated`. Comparable
    as a string within a single source, which is all `stage_all` needs.
    """

    source_id: str
    source_type: str
    payload: dict[str, Any]
    watermark: str | None = None


@dataclass
class StageResult:
    staged: int = 0
    skipped: int = 0
    watermark: str | None = None
    errors: list[str] = field(default_factory=list)


class Source(Protocol):
    """Fetch what changed since `since`. Capture only — never interpret."""

    source_type: str

    async def fetch(self, since: str | None) -> list[FetchedRecord]: ...


StageFn = Callable[[FetchedRecord], Awaitable[str | None]]
WatermarkFn = Callable[[str, str], Awaitable[None]]


async def stage_all(
    source: Source,
    stage: StageFn,
    set_watermark: WatermarkFn,
    *,
    since: str | None,
) -> StageResult:
    """Fetch, stage everything, then advance the watermark.

    **The ordering is a correctness property.** Advancing the watermark before
    staging succeeds means a mid-batch failure skips those records
    permanently, and nothing surfaces the loss — someone notices a week later
    that meetings are missing. So: stage first, and only move the watermark if
    every record made it.
    """
    records = await source.fetch(since)
    result = StageResult()

    for record in records:
        staged_id = await stage(record)
        if staged_id is None:
            result.skipped += 1
        else:
            result.staged += 1

    # Max rather than last: sources do not always return records in order, and
    # taking the last one would rewind the watermark and re-fetch forever.
    watermarks = [r.watermark for r in records if r.watermark]
    if watermarks:
        result.watermark = max(watermarks)
        await set_watermark(source.source_type, result.watermark)

    log.info(
        "source.staged",
        source=source.source_type,
        staged=result.staged,
        skipped=result.skipped,
        watermark=result.watermark,
    )
    return result
