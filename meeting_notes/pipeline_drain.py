"""Drain one claimed batch: route each record to the pipeline or jira_sync.

Exists so `jobs/pipeline_drain.py` stays thin (CLAUDE.md). `staged_records`
holds every source in one table (ADR-018); `jira` rows are status
sync-back, everything else goes through `pipeline.process`.

Errors are per-record, not per-batch — carried from v5's
`asyncio.gather(..., return_exceptions=True)` pattern in `process_new_emails`
et al. One exploding record must not silently drop every other record queued
behind it in the same claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

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


async def drain_batch(
    records: list[StagedRecord],
    *,
    process: Any = None,
    sync_jira: Any = None,
) -> DrainResult:
    """Route and process every record in a claimed batch."""
    process = process or _default_process
    sync_jira = sync_jira or _default_sync_jira

    result = DrainResult()
    for record in records:
        try:
            if record.source_type == "jira":
                await sync_jira(record.payload, record_id=record.id)
            else:
                await process(record, adapter_for(record.source_type))
            result.processed += 1
        except Exception as exc:  # noqa: BLE001 - one bad record must not sink the batch
            result.errors += 1
            result.error_details.append(f"{record.id}: {exc}")
            log.error(
                "pipeline_drain.record_error",
                record_id=record.id, source=record.source_type, error=str(exc), exc_info=True,
            )

    log.info(
        "pipeline_drain.batch_done",
        total=len(records), processed=result.processed, errors=result.errors,
    )
    return result
