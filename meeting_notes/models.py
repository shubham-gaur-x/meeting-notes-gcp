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


# ─── adapter parse targets ────────────────────────────────────────────────────
# These are no longer tables (ADR-018). Each per-source adapter parses a
# StagedRecord.payload into the matching model below, so validation stays
# exactly as strict as v5's while staging keeps a single table.


class RawEmail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    subject: str
    from_email: str
    to_emails: list[str]
    body: str
    received_at: str
    processed: bool = False


class RawCalendarEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    title: str
    description: str | None = None
    start_time: str
    end_time: str
    attendees_json: str | None = None
    processed: bool = False


class RawMeetTranscript(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    title: str = ""
    transcript_text: str = ""
    conference_record: str | None = None
    start_time: str | None = None
    attendees_json: str | None = None
    calendar_description: str | None = None  # fallback context only
    processed: bool = False


class RawJiraIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    key: str
    summary: str
    status: str
    assignee: str | None = None
    priority: str | None = None
    jira_created_at: str | None = None
    jira_updated_at: str | None = None
    processed: bool = False


# ─── staging (ADR-018) ────────────────────────────────────────────────────────


class StagedRecord(BaseModel):
    """One staged row from any source.

    `payload` is opaque here on purpose: a per-source adapter parses it into
    the matching typed model above, so validation stays as strict as v5's
    while staging keeps a single table, a single SKIP LOCKED claiming query
    (ADR-006), and a single drain path (ADR-010).
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    source_type: SourceType
    payload: dict[str, Any]
    fetched_at: str
    processed: bool = False
