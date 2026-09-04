"""Pydantic models — extraction shapes and the single staging shape.

Ported from v5 (`transform_service/models.py`) with three deliberate changes:

1. `StagedRecord` is new (ADR-018). One staging table with a JSONB payload
   replaces v5's four near-identical raw tables.
2. The four `Raw*` models lose their `source_table` field. They are no longer
   tables — they are the per-source adapters' parse targets, and
   `StagedRecord.source_type` is the discriminator now.
3. `AirbyteWebhookPayload` is deleted outright (MIGRATION_FROM_V5.md §4).

Typing is modernised to 3.11+; validation behaviour is otherwise unchanged.
"""

from __future__ import annotations

from datetime import date, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

SourceType = Literal["email", "calendar", "meet", "jira"]


class Attendee(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    email: str | None = None
    role: str = "attendee"


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    owner: str
    task: str
    due: date | None = None
    done: bool = False
    priority: Literal["high", "medium", "low"] = "medium"
    jira_key: str | None = None
    linear_id: str | None = None
    linear_identifier: str | None = None
    is_engineering_task: bool = False
    # Per-item extraction confidence. Defaults to 1.0 so items the model does not
    # score are not gated; the extractor prompt asks for a real 0.0-1.0 value.
    confidence: float = 1.0


class Decision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    # Per-item extraction confidence, same pattern as ActionItem.confidence.
    # Defaults to 1.0 so decisions the model does not score are not gated.
    confidence: float = 1.0


class Blocker(BaseModel):
    """Something stopping progress, raised in a meeting.

    Stored as `Blocker` + `Meeting-[:RAISES_BLOCKER]->Blocker` and surfaced in
    the review queue. `status` lives on the node (default `open`), not here —
    the extraction only reports that a blocker was raised, never that it was
    resolved.
    """

    model_config = ConfigDict(extra="ignore")

    text: str
    raised_by: str | None = None


class ExtractedMeeting(BaseModel):
    """What the LLM returns for one meeting.

    Note that `kind` is the LLM's own description of the meeting and is NOT
    the same vocabulary as `meeting_type_router.TYPES`, which picks an
    extraction prompt. The two overlap but are not interchangeable — see the
    test that pins them apart.
    """

    model_config = ConfigDict(extra="ignore")

    title: str
    kind: Literal["meeting", "email_thread", "call", "standup", "review", "other"]
    platform: str
    date: date
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = None
    location: str | None = None
    attendees: list[Attendee] = []
    summary: str
    topics: list[str] = []
    decisions: list[Decision] = []
    blockers: list[Blocker] = []
    action_items: list[ActionItem] = []
    key_quotes: list[str] = []
    links: list[str] = []
    sentiment: Literal["positive", "neutral", "negative", "mixed"] = "neutral"
    follow_up_needed: bool = False
    confidence: float = 0.0

    @field_validator("decisions", mode="before")
    @classmethod
    def _coerce_decisions(cls, v: Any) -> Any:
        """Backward-compat: decisions are sometimes a list of plain strings in
        LLM output that omits confidence. Coerce a bare string entry to
        {"text": ..., "confidence": 1.0} so both shapes validate.

        Load-bearing — real extractions hit this path."""
        if not isinstance(v, list):
            return v
        return [{"text": item, "confidence": 1.0} if isinstance(item, str) else item for item in v]

    @field_validator("blockers", mode="before")
    @classmethod
    def _coerce_blockers(cls, v: Any) -> Any:
        """Same leniency `decisions` needs: a bare string becomes {"text": ...}."""
        if not isinstance(v, list):
            return v
        return [{"text": item} if isinstance(item, str) else item for item in v]


class StagedRecord(BaseModel):
    """One staged row from any source.

    `payload` is deliberately an opaque dict, and there is deliberately no
    typed model per source. v5's `RawEmail`/`RawCalendarEvent`/… described the
    columns of the per-source *tables* ADR-018 removed (`id`, `source_id`,
    `processed`); they never matched a payload and could not validate one.
    The per-source adapters in `pipeline.py` read the payload directly and
    tolerate a missing field rather than rejecting the record — the same
    degrade-don't-fail rule the enrichment layers follow.

    Staging keeps a single table, a single SKIP LOCKED claiming query
    (ADR-006), and a single drain path (ADR-010).
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    source_type: SourceType
    payload: dict[str, Any]
    fetched_at: str
    processed: bool = False
