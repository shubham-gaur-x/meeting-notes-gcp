"""The pipeline — one `process(record, adapter)`, not three copies (ADR-010).

v5's `graph_builder.py` has `process_email`, `process_calendar_event` and
`process_transcript` — three functions ~90% identical, with the entire
nine-call memory-enrichment block copy-pasted verbatim three times. Adding a
fifth source meant a fourth copy. Here, adding a source is one small
`Adapter`; the pipeline itself never branches on source type.

Each `Adapter` shapes a staged record's opaque payload into what the
classifier, router and extractor each need. The one behavioural difference
between sources is carried forward from v5 deliberately: a real Meet
transcript is strong signal on its own, so `MeetAdapter` skips the
classifier's score gate when transcript text is present — a text classifier
tuned for email subjects has no business vetoing an actual recorded meeting.

MIGRATION_FROM_V5 bug #1 (`ASSIGNED_TO` never forming) is already fixed in
`graph_client.upsert_meeting_graph` (Phase 3) — this module does not
re-resolve owners, it just calls that function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from meeting_notes import classifier, extractor, meeting_type_router
from meeting_notes.config import Settings, get_settings
from meeting_notes.models import ExtractedMeeting, StagedRecord

log = structlog.get_logger()


@dataclass(frozen=True)
class PipelineResult:
    status: str  # "processed" | "skipped_low_score" | "extract_failed"
    meeting_id: str | None = None
    score: float | None = None


class Adapter(Protocol):
    """What one source contributes to the pipeline. Everything else is shared."""

    source_type: str

    def text(self, payload: dict[str, Any]) -> str:
        """The text handed to the classifier and, prefixed, to the extractor."""
        ...

    def classify_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Signals classify() uses beyond the text itself."""
        ...

    def router_title(self, payload: dict[str, Any]) -> str: ...
    def router_hint(self, payload: dict[str, Any]) -> str:
        """meeting_type_router's prompt hint for this payload."""
        ...

    def extract_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Fallback values for null-like extractor fields (date, platform)."""
        ...

    def skip_score_gate(self, payload: dict[str, Any]) -> bool:
        """True when the classifier's score should not gate this record."""
        return False


def _route_hint(title: str, body: str, source_type: str) -> str:
    meeting_type = meeting_type_router.route(title, body, source_type=source_type)
    return meeting_type_router.prompt_hint(meeting_type)


class EmailAdapter:
    source_type = "email"

    def text(self, payload: dict[str, Any]) -> str:
        return f"{payload.get('subject', '')}\n\n{payload.get('body', '')}"

    def classify_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"from": payload.get("from", ""), "to": payload.get("to", "")}

    def router_title(self, payload: dict[str, Any]) -> str:
        subject: str = payload.get("subject", "")
        return subject

    def router_hint(self, payload: dict[str, Any]) -> str:
        return _route_hint(self.router_title(payload), payload.get("body", ""), "email")

    def extract_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        date = (payload.get("date") or "")[:10] or None
        return {"date": date, "platform": "email"}

    def skip_score_gate(self, payload: dict[str, Any]) -> bool:
        return False


class CalendarAdapter:
    source_type = "calendar"

    def text(self, payload: dict[str, Any]) -> str:
        return f"{payload.get('summary', '')}\n\n{payload.get('description', '') or ''}"

    def classify_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        attendees = payload.get("attendees") or []
        return {
            "start_time": payload.get("start", ""),
            "end_time": payload.get("end", ""),
            "attendees_count": len(attendees),
        }

    def router_title(self, payload: dict[str, Any]) -> str:
        summary: str = payload.get("summary", "")
        return summary

    def router_hint(self, payload: dict[str, Any]) -> str:
        return _route_hint(
            self.router_title(payload), payload.get("description", "") or "", "calendar"
        )

    def extract_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = payload.get("start") or ""
        date = start[:10] if len(start) >= 10 else None
        return {"date": date, "platform": "google_calendar"}

    def skip_score_gate(self, payload: dict[str, Any]) -> bool:
        return False


class MeetAdapter:
    source_type = "meet"

    def text(self, payload: dict[str, Any]) -> str:
        # Transcript is primary; fall back to title only when it is absent —
        # carried from v5's process_transcript.
        primary = (payload.get("text") or "").strip()
        body = primary or payload.get("title", "")
        return f"{payload.get('title', '')}\n\n{body}"

    def classify_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"start_time": payload.get("start_time", "")}

    def router_title(self, payload: dict[str, Any]) -> str:
        title: str = payload.get("title", "")
        return title

    def router_hint(self, payload: dict[str, Any]) -> str:
        return _route_hint(self.router_title(payload), self.text(payload), "meet")

    def extract_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = payload.get("start_time") or ""
        date = start[:10] if len(start) >= 10 else None
        return {"date": date, "platform": "google_meet"}

    def skip_score_gate(self, payload: dict[str, Any]) -> bool:
        """A real transcript is strong signal on its own. Only the title-only
        fallback (no transcript captured) goes through the normal score gate."""
        return bool((payload.get("text") or "").strip())


_ADAPTERS: dict[str, Adapter] = {
    "email": EmailAdapter(),
    "calendar": CalendarAdapter(),
    "meet": MeetAdapter(),
}


def adapter_for(source_type: str) -> Adapter:
    try:
        return _ADAPTERS[source_type]
    except KeyError:
        raise ValueError(f"no pipeline adapter for source_type {source_type!r}") from None


async def process(
    record: StagedRecord,
    adapter: Adapter,
    *,
    settings: Settings | None = None,
    upsert: Any = None,
    push_jira: Any = None,
    mark_processed: Any = None,
    transport: Any = None,
) -> PipelineResult:
    """classify -> route -> extract -> graph write -> push to Jira.

    `upsert`, `push_jira`, `mark_processed` and `transport` are injectable so
    the suite exercises every branch with no LLM, no database, no Memgraph.
    `transport` passes straight through to `extractor.extract_meeting`, which
    already exposes it for exactly this purpose. Defaults wire the real
    modules for production use.
    """
    settings = settings or get_settings()
    if upsert is None:
        from meeting_notes import graph_client

        upsert = graph_client.upsert_meeting_graph
    if push_jira is None:
        from meeting_notes import jira_pusher

        push_jira = jira_pusher.push_action_items
    if mark_processed is None:
        from meeting_notes import db

        mark_processed = db.mark_processed

    bound = log.bind(source=record.source_type, source_id=record.source_id, step="classify")
    payload = record.payload

    text = adapter.text(payload)
    score = classifier.classify(text, adapter.classify_metadata(payload))

    if not adapter.skip_score_gate(payload) and score < settings.classifier_score_threshold:
        bound.info("pipeline.skipped", score=round(score, 3))
        await mark_processed(record.id)
        return PipelineResult(status="skipped_low_score", score=score)

    bound = bound.bind(step="extract")
    meeting: ExtractedMeeting | None = await extractor.extract_meeting(
        text,
        adapter.source_type,
        context=adapter.extract_context(payload),
        type_hint=adapter.router_hint(payload),
        settings=settings,
        transport=transport,
    )

    if meeting is None:
        bound.warning("pipeline.extract_failed")
        await mark_processed(record.id)
        return PipelineResult(status="extract_failed", score=score)

    bound = bound.bind(step="graph_write", meeting_title=meeting.title)
    meeting_id: str = await upsert(meeting, record.source_id)

    bound = bound.bind(step="jira_push")
    await push_jira(meeting.action_items, meeting, record.source_id)

    await mark_processed(record.id)
    bound.info("pipeline.processed", score=round(score, 3), meeting_id=meeting_id)
    return PipelineResult(status="processed", meeting_id=meeting_id, score=score)
