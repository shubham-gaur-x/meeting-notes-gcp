"""Pipeline Operations & Dead-Letter Queue (DLQ) administrative endpoints."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import require_admin
from meeting_notes import db
from meeting_notes.access_control import Principal

log = structlog.get_logger()
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class ReplayRequest(BaseModel):
    """Payload to replay one or all quarantined dead-letter records."""

    record_id: str | None = Field(
        default=None,
        description=(
            "Optional UUID of a specific record to replay. "
            "If omitted, all dead-letter records are replayed."
        ),
    )


@router.get("/stats")
async def queue_stats(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """Retrieve staging queue depth and status breakdown (pending, retry, dead_letter, processed)."""
    stats = await db.get_queue_stats()
    log.info("pipeline_ops.queue_stats", actor=admin.name, role=admin.role)
    return {"stats": stats}


@router.get("/dlq")
async def list_dead_letters(
    limit: int = Query(50, ge=1, le=500),
    admin: Principal = Depends(require_admin),
) -> dict[str, Any]:
    """List quarantined records that failed processing after reaching maximum retry attempts."""
    records = await db.list_dead_letter_records(limit=limit)
    log.info(
        "pipeline_ops.list_dlq",
        actor=admin.name,
        role=admin.role,
        limit=limit,
        count=len(records),
    )
    return {
        "count": len(records),
        "records": [
            {
                "id": r.id,
                "source_id": r.source_id,
                "source_type": r.source_type,
                "attempts": r.attempts,
                "last_error": r.last_error,
                "status": r.status,
                "fetched_at": r.fetched_at,
            }
            for r in records
        ],
    }


@router.post("/dlq/replay")
async def replay_dead_letters(
    body: ReplayRequest | None = None,
    admin: Principal = Depends(require_admin),
) -> dict[str, Any]:
    """Replay quarantined dead-letter records by resetting attempts to 0 and status to 'pending'."""
    record_id = body.record_id if body else None

    if record_id:
        try:
            uuid.UUID(record_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid record_id {record_id!r}: must be a valid UUID",
            ) from None

        success = await db.replay_dead_letter_record(record_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Dead-letter record {record_id} not found or not in 'dead_letter' status",
            )
        log.info(
            "pipeline_ops.replay_dlq",
            actor=admin.name,
            role=admin.role,
            record_id=record_id,
            count=1,
        )
        return {"status": "replayed", "record_id": record_id, "count": 1}

    count = await db.replay_all_dead_letter_records()
    log.info(
        "pipeline_ops.replay_all_dlq",
        actor=admin.name,
        role=admin.role,
        count=count,
    )
    return {"status": "replayed", "count": count}
