"""Drain one claimed batch: route each record to the pipeline or jira_sync with bounded concurrency.

Exists so `jobs/pipeline_drain.py` stays thin (CLAUDE.md). `staged_records`
holds every source in one table (ADR-018); `jira` rows are status
sync-back, everything else goes through `pipeline.process`.

Errors are per-record, not per-batch: one exploding record must not silently
drop every other record queued behind it in the same claim. Bounded concurrency
via `graph_write_concurrency` ensures high throughput without exceeding database
or API limits. Poison-pill failures are recorded to dead-letter storage to prevent
infinite retry loops.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.models import StagedRecord
from meeting_notes.pipeline import adapter_for

log = structlog.get_logger()


@dataclass
class DrainResult:
    processed: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


async def _default_process(record: StagedRecord, adapter: Any) -> Any:
    from meeting_notes.pipeline import process

    return await process(record, adapter)


async def _default_sync_jira(payload: dict[str, Any], *, record_id: str) -> bool:
    from meeting_notes.jira_sync import sync_one

    return await sync_one(payload, record_id=record_id)


async def _default_record_failure(record_id: str, error: str) -> tuple[int, bool, str]:
    from meeting_notes import db

    return await db.record_drain_failure(record_id, error)


async def drain_batch(
    records: list[StagedRecord],
    *,
    process: Any = None,
    sync_jira: Any = None,
    record_failure: Any = None,
    concurrency_limit: int | None = None,
    settings: Settings | None = None,
) -> DrainResult:
    """Route and process every record in a claimed batch with bounded concurrency."""
    process = process or _default_process
    sync_jira = sync_jira or _default_sync_jira
    record_failure = record_failure or _default_record_failure
    settings = settings or get_settings()

    limit = concurrency_limit or max(1, getattr(settings, "graph_write_concurrency", 3))
    sem = asyncio.Semaphore(limit)
    result = DrainResult()
    lock = asyncio.Lock()

    async def _handle_record(record: StagedRecord) -> None:
        async with sem:
            try:
                if record.source_type == "jira":
                    await sync_jira(record.payload, record_id=record.id)
                else:
                    await process(record, adapter_for(record.source_type))
                async with lock:
                    result.processed += 1
            except Exception as exc:  # noqa: BLE001 - one bad record must not sink the batch
                async with lock:
                    result.errors += 1
                    result.error_details.append(f"{record.id}: {exc}")
                log.error(
                    "pipeline_drain.record_error",
                    record_id=record.id, source=record.source_type, error=str(exc), exc_info=True,
                )
                try:
                    await record_failure(record.id, str(exc))
                except Exception as rec_exc:  # noqa: BLE001
                    log.warning(
                        "pipeline_drain.record_failure_failed",
                        record_id=record.id,
                        error=str(rec_exc),
                    )

    await asyncio.gather(*[_handle_record(r) for r in records])

    log.info(
        "pipeline_drain.batch_done",
        total=len(records), processed=result.processed, errors=result.errors,
    )
    return result
