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

    def extract_overrides(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Fields where the SOURCE is authoritative and the model is not.

        A calendar event's `start` is ground truth; the model reading the
        description and inferring a date is strictly worse. Without this, a
        recurring series had every instance stamped with the date the
        description happened to mention -- five "QA AI Pilot" instances spread
        across five weeks all landed on 2026-01-13, which silently corrupts
        timeline order and every temporal chain built from it.
        """
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

    def extract_overrides(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Nothing. A mail header date is when the MESSAGE was sent, which is
        often not when the meeting it discusses happened -- so here the model
        reading the thread genuinely can do better."""
        return {}

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
        return {"date": self._date(payload), "platform": "google_calendar"}

    def extract_overrides(self, payload: dict[str, Any]) -> dict[str, Any]:
        """`start` and the invitee list are ground truth for a calendar event.

        The Calendar API states exactly who was invited, with addresses. The
        model only ever sees the title and description, so it infers attendees
        from prose -- names with no email, which `person_resolver` can do
        nothing with except queue for review. Rebuilding the corpus made the
        cost visible: 71 of 95 review entries were "no-email-no-match" while
        the addresses sat unused in the payload.
        """
        overrides: dict[str, Any] = {}
        date = self._date(payload)
        if date:
            overrides["date"] = date
        attendees = self._attendees(payload)
        if attendees:
            overrides["attendees"] = attendees
        return overrides

    @staticmethod
    def _attendees(payload: dict[str, Any]) -> list[dict[str, str]]:
        """Invitees carrying a real address.

        An entry without one (a room, a resource) is dropped rather than
        turned into a Person with a fabricated email.
        """
        out: list[dict[str, str]] = []
        for entry in payload.get("attendees") or []:
            email = (entry.get("email") or "").strip().lower()
            if not email:
                continue
            name = (entry.get("name") or "").strip()
            if not name:
                # Calendar often returns an address with no display name.
                # A readable placeholder keeps the node legible; the email
                # remains the identity the resolver actually keys on.
                name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
            out.append({
                "name": name,
                "email": email,
                "role": "organizer" if entry.get("organizer") else "attendee",
            })
        return out

    @staticmethod
    def _date(payload: dict[str, Any]) -> str | None:
        start = payload.get("start") or ""
        return start[:10] if len(start) >= 10 else None

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
        return {"date": self._date(payload), "platform": "google_meet"}

    def extract_overrides(self, payload: dict[str, Any]) -> dict[str, Any]:
        """A conference record's start_time is ground truth."""
        date = self._date(payload)
        return {"date": date} if date else {}

    @staticmethod
    def _date(payload: dict[str, Any]) -> str | None:
        start = payload.get("start_time") or ""
        return start[:10] if len(start) >= 10 else None

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


# The enrichment layers, in run order. Declared once here so callers and tests
# can introspect the set without executing it; `enrich` asserts the list it
# builds still matches, so the two cannot drift apart silently.
ENRICH_STEPS: tuple[str, ...] = (
    "facts", "relationships", "temporal", "causality", "procedures",
    "embed_meeting", "embed_actions", "embed_facts", "algorithms",
)


def enrich_step_names() -> tuple[str, ...]:
    """The enrichment layers `enrich()` runs, in order."""
    return ENRICH_STEPS


async def enrich(
    meeting: ExtractedMeeting,
    meeting_id: str,
    *,
    settings: Settings | None = None,
    enrich_fn: Any = None,
) -> dict[str, Any]:
    """Graph enrichment, run after the meeting is safely committed.

    **Best-effort by design.** The graph write has already committed by the
    time this runs, so a failing embedding or LLM call must never roll back or
    fail a correctly-stored meeting. Every step is caught individually: one
    failing layer does not skip the others, and the record is still marked
    processed either way.

    Deliberately does NOT import `memory.retrieval` — retrieval is query-time
    only (CLAUDE.md), and calling it here would put an LLM synthesis call on
    the ingestion path.
    """
    if enrich_fn is not None:
        result: dict[str, Any] = await enrich_fn(meeting, meeting_id)
        return result

    from meeting_notes import graph_algorithms
    from meeting_notes.memory import episodic, procedural, semantic, vector

    emails = [a.email for a in meeting.attendees if a.email]
    outcome: dict[str, Any] = {}

    steps: list[tuple[str, Any]] = [
        ("facts", lambda: semantic.extract_facts(meeting, meeting_id, settings=settings)),
        ("relationships", lambda: semantic.strengthen_relationships(meeting, meeting_id)),
        ("temporal", lambda: episodic.link_temporal_chain(meeting_id, str(meeting.date), emails)),
        ("causality", lambda: episodic.detect_causality(meeting, meeting_id, settings=settings)),
        ("procedures", lambda: procedural.match_to_procedure(meeting, meeting_id)),
        ("embed_meeting", lambda: vector.embed_meeting(meeting_id, meeting.summary, settings=settings)),
        ("embed_actions", lambda: vector.embed_action_items_for_meeting(meeting_id, settings=settings)),
        # Without this, every Fact stays outside the vector index and
        # /graph/search/facts can never return a result -- found live against
        # 83 real Facts, all unembedded.
        ("embed_facts", lambda: vector.embed_facts_for_meeting(meeting_id, settings=settings)),
        ("algorithms", lambda: graph_algorithms.run_fast()),
    ]
    assert tuple(n for n, _ in steps) == ENRICH_STEPS, "ENRICH_STEPS drifted from enrich()"

    for name, step in steps:
        try:
            outcome[name] = await step()
        except Exception as exc:  # noqa: BLE001 - enrichment never fails the record
            log.warning("pipeline.enrich_step_failed", enrich_step=name, error=str(exc))
            outcome[name] = None

    log.info("pipeline.enriched", meeting_id=meeting_id, steps=list(outcome))
    return outcome


async def process(
    record: StagedRecord,
    adapter: Adapter,
    *,
    settings: Settings | None = None,
    upsert: Any = None,
    push_jira: Any = None,
    mark_processed: Any = None,
    transport: Any = None,
    enrich_fn: Any = None,
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

    # Source-authoritative fields win over whatever the model inferred.
    overrides = adapter.extract_overrides(payload)
    if overrides:
        meeting = meeting.model_copy(update=overrides)

    bound = bound.bind(step="graph_write", meeting_title=meeting.title)
    meeting_id: str = await upsert(meeting, record.source_id)

    bound = bound.bind(step="jira_push")
    await push_jira(meeting.action_items, meeting, record.source_id)

    bound = bound.bind(step="enrich")
    try:
        await enrich(meeting, meeting_id, settings=settings, enrich_fn=enrich_fn)
    except Exception as exc:  # noqa: BLE001
        # The graph write above has already committed. Enrichment failing --
        # for any reason, including an injected one -- must never turn a
        # correctly-stored meeting into a failed record.
        bound.warning("pipeline.enrich_failed", error=str(exc))

    await mark_processed(record.id)
    bound.info("pipeline.processed", score=round(score, 3), meeting_id=meeting_id)
    return PipelineResult(status="processed", meeting_id=meeting_id, score=score)
