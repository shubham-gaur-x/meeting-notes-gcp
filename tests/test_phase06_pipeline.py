"""Phase 6 — the pipeline. No live services; every dependency is injected.

The live checks (real Onix data, real Vertex, real local Memgraph) are Task 5
of the plan and run by hand.
"""

from __future__ import annotations

from meeting_notes.graph_client import get_open_actions_for_owner, update_action_jira_status

# ─── graph_client fixes (Task 1) ───────────────────────────────────────────────


class _FakeResult:
    def __init__(self, records: list[dict], *, updates: int = 0) -> None:
        self._records = records
        self._updates = updates

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._records:
            raise StopAsyncIteration
        return self._records.pop(0)

    async def consume(self):
        class _Summary:
            def __init__(self, n: int) -> None:
                class _Counters:
                    def __init__(self, n: int) -> None:
                        self.properties_set = n

                self.counters = _Counters(n)

        return _Summary(self._updates)


class _FakeSession:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result
        self.calls: list[tuple[str, dict]] = []

    async def run(self, cypher: str, **params) -> _FakeResult:
        self.calls.append((cypher, params))
        return self._result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeDriver:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result
        self.session_obj: _FakeSession | None = None

    def session(self) -> _FakeSession:
        self.session_obj = _FakeSession(self._result)
        return self.session_obj


async def test_get_open_actions_for_owner_excludes_the_given_id() -> None:
    """Without exclude_id, an item can match itself at similarity 1.0 — by the
    time jira_pusher runs, upsert_meeting_graph already wrote every action
    item in the meeting, including the one currently being deduped."""
    driver = _FakeDriver(_FakeResult([]))
    await get_open_actions_for_owner("alice@corp.com", exclude_id="action-42", driver=driver)

    cypher, params = driver.session_obj.calls[0]
    assert params.get("exclude_id") == "action-42"
    assert "<>" in cypher or "exclude_id" in cypher


async def test_update_action_jira_status_reports_whether_it_matched() -> None:
    """jira_sync's matched/unmatched counters must mean something — a silent
    no-op must not be reported as a match."""
    driver = _FakeDriver(_FakeResult([], updates=1))
    matched = await update_action_jira_status("SCRUM-1", "Done", True, driver=driver)
    assert matched is True


async def test_update_action_jira_status_reports_false_for_an_unknown_key() -> None:
    """A Jira ticket created outside this pipeline is real signal, not a bug —
    the caller needs to know it found nothing to update."""
    driver = _FakeDriver(_FakeResult([], updates=0))
    matched = await update_action_jira_status("SCRUM-999", "Done", True, driver=driver)
    assert matched is False


# ─── pipeline (ADR-010: the collapse) ──────────────────────────────────────────

import json  # noqa: E402

from meeting_notes.config import Settings  # noqa: E402
from meeting_notes.models import StagedRecord  # noqa: E402
from meeting_notes.pipeline import (  # noqa: E402
    CalendarAdapter,
    EmailAdapter,
    MeetAdapter,
    adapter_for,
    process,
)


def _record(source_type: str, payload: dict, source_id: str = "s1") -> StagedRecord:
    return StagedRecord(
        id="rec-1", source_id=source_id, source_type=source_type,
        payload=payload, fetched_at="2026-08-20T00:00:00Z",
    )


def _email_payload(**over) -> dict:
    base = {
        "subject": "just an fyi, no action needed", "from": "noreply@marketing.example",
        "to": "me@corp.com", "body": "click here to unsubscribe", "date": "2026-08-20",
    }
    base.update(over)
    return base


class RecordingGraph:
    """Stands in for graph_client.upsert_meeting_graph."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def __call__(self, meeting, source_id, **kw):
        self.calls.append((meeting, source_id))
        return "meeting-id-1"


class RecordingPusher:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def __call__(self, action_items, meeting, source_id, **kw):
        self.calls.append((action_items, meeting, source_id))
        return []


def _fake_settings(fixture_dir) -> Settings:
    return Settings(_env_file=None, LLM_BACKEND="fake", LLM_FIXTURE_DIR=str(fixture_dir))


class RecordingMarker:
    """Async stand-in for db.mark_processed."""

    def __init__(self) -> None:
        self.ids: list[str] = []

    async def __call__(self, record_id: str) -> None:
        self.ids.append(record_id)


async def test_a_low_score_record_is_marked_processed_and_stops() -> None:
    """The cheap gate stays cheap: no LLM call for obvious noise."""
    record = _record("email", _email_payload())
    graph = RecordingGraph()
    marked = RecordingMarker()

    result = await process(
        record, EmailAdapter(),
        settings=None, upsert=graph, push_jira=RecordingPusher(),
        mark_processed=marked,
    )

    assert result.status == "skipped_low_score"
    assert marked.ids == ["rec-1"]
    assert graph.calls == [], "no LLM/graph work for a below-threshold record"


async def test_a_failed_extraction_is_marked_processed_not_retried() -> None:
    """Temperature 0: an identical retry yields identical output, so a parse
    failure is marked done rather than looped on forever."""
    payload = _email_payload(
        subject="Weekly Planning Sync Meeting Recap",
        body=(
            "We met with alice@corp.com and bob@corp.com about the budget. "
            "We decided to ship next week per our discussion. Action item: "
            "Alice will write the doc as a follow-up. Duration: 30 minutes."
        ),
    )
    record = _record("email", payload)
    marked = RecordingMarker()

    async def garbage_transport(url, payload, headers):
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]})

    settings = Settings(_env_file=None, LLM_BACKEND="vertex", GCP_PROJECT_ID="proj-x",
                        VERTEX_CHAT_MODEL="gemini-3.7-flash", VERTEX_LOCATION="global")
    result = await process(
        record, EmailAdapter(), settings=settings,
        upsert=RecordingGraph(), push_jira=RecordingPusher(),
        mark_processed=marked, transport=garbage_transport,
    )

    assert result.status == "extract_failed"
    assert marked.ids == ["rec-1"]


async def test_a_successful_record_reaches_the_graph_write(tmp_path) -> None:
    from meeting_notes.extractor import build_system_prompt
    from meeting_notes.llm_client import fixture_key

    payload = _email_payload(
        subject="Weekly Planning Sync Meeting Recap",
        body=(
            "We met with alice@corp.com and bob@corp.com about the budget. "
            "We decided to ship next week per our discussion. Action item: "
            "Alice will write the doc as a follow-up. Duration: 30 minutes."
        ),
    )
    record = _record("email", payload)
    adapter = EmailAdapter()

    system = build_system_prompt(adapter.router_hint(payload))
    user = f"Extract meeting information from this email:\n\n{adapter.text(payload)}"
    (tmp_path / f"{fixture_key(system, user, 0.0)}.json").write_text(json.dumps({
        "title": "Weekly Planning Sync", "kind": "meeting", "platform": "email",
        "date": "2026-08-20", "summary": "budget discussion",
        "action_items": [{"owner": "Alice", "task": "write the doc"}],
    }))

    graph = RecordingGraph()
    marked = RecordingMarker()
    result = await process(
        record, adapter, settings=_fake_settings(tmp_path),
        upsert=graph, push_jira=RecordingPusher(), mark_processed=marked,
    )

    assert result.status == "processed"
    assert len(graph.calls) == 1
    assert marked.ids == ["rec-1"]


async def test_meet_adapter_bypasses_the_score_gate_when_transcript_present() -> None:
    """A real transcript is strong signal on its own — v5's one deliberate
    behavioural difference between adapters, carried forward here."""
    adapter = MeetAdapter()
    payload = {"title": "x", "text": "short", "start_time": "2026-08-20T10:00:00Z"}
    assert adapter.skip_score_gate(payload) is True


async def test_meet_adapter_uses_the_score_gate_with_no_transcript() -> None:
    adapter = MeetAdapter()
    payload = {"title": "x", "text": "", "start_time": "2026-08-20T10:00:00Z"}
    assert adapter.skip_score_gate(payload) is False


async def test_adapter_for_selects_by_source_type() -> None:
    assert isinstance(adapter_for("email"), EmailAdapter)
    assert isinstance(adapter_for("calendar"), CalendarAdapter)
    assert isinstance(adapter_for("meet"), MeetAdapter)


async def test_calendar_adapter_shapes_text_and_context() -> None:
    adapter = CalendarAdapter()
    payload = {
        "summary": "Planning", "description": "budget review",
        "start": "2026-08-20T10:00:00Z", "attendees": [{"email": "a@corp.com"}],
    }
    assert "Planning" in adapter.text(payload)
    assert "budget review" in adapter.text(payload)
    ctx = adapter.extract_context(payload)
    assert ctx["date"] == "2026-08-20"
    assert ctx["platform"] == "google_calendar"


# ─── jira_client additions (Task 3) ────────────────────────────────────────────

from meeting_notes.jira_client import active_sprint_id, create_issue, move_to_sprint  # noqa: E402


def _jira_settings(**over) -> Settings:
    base = dict(_env_file=None, JIRA_DOMAIN="x.atlassian.net", JIRA_EMAIL="e",
               JIRA_API_TOKEN="t", JIRA_PROJECT_KEY="SCRUM", JIRA_BOARD_ID=1,
               JIRA_ISSUE_TYPE="Task")
    base.update(over)
    return Settings(**base)


async def test_priority_maps_to_jiras_three_levels() -> None:
    seen: dict = {}

    async def transport(method, url, headers, params, json_body):
        seen.update(json_body or {})
        return 200, {"key": "SCRUM-1"}

    await create_issue(
        summary="s", description="d", priority="high", sprint_id=None,
        is_engineering_task=False, settings=_jira_settings(), transport=transport,
    )
    assert seen["fields"]["priority"]["name"] == "High"


async def test_a_non_engineering_task_gets_the_meeting_action_item_label() -> None:
    seen: dict = {}

    async def transport(method, url, headers, params, json_body):
        seen.update(json_body or {})
        return 200, {"key": "SCRUM-1"}

    await create_issue(
        summary="s", description="d", priority="medium", sprint_id=None,
        is_engineering_task=False, settings=_jira_settings(), transport=transport,
    )
    assert seen["fields"]["labels"] == ["meeting-action-item"]


async def test_an_engineering_task_is_labelled_for_the_dev_agent() -> None:
    """v5 left engineering tasks unlabelled and this test pinned that.

    It is the bug: `dev_agent.find_sprint_candidates` selects on the
    `dev-agent` label, so an unlabelled engineering ticket is invisible to the
    agent forever. Producer and consumer disagreed about how a coding task is
    marked, and each half looked correct on its own.
    """
    seen: dict = {}

    async def transport(method, url, headers, params, json_body):
        seen.update(json_body or {})
        return 200, {"key": "SCRUM-1"}

    await create_issue(
        summary="s", description="d", priority="medium", sprint_id=None,
        is_engineering_task=True, settings=_jira_settings(), transport=transport,
    )
    assert seen["fields"]["labels"] == ["dev-agent"], (
        "the agent selects on this label; without it the ticket is never picked up"
    )


async def test_a_high_priority_issue_is_moved_to_the_active_sprint() -> None:
    calls: list[str] = []

    async def transport(method, url, headers, params, json_body):
        calls.append(url)
        return 200, {"key": "SCRUM-1"}

    await create_issue(
        summary="s", description="d", priority="high", sprint_id=42,
        is_engineering_task=False, settings=_jira_settings(), transport=transport,
    )
    assert any("sprint/42/issue" in u for u in calls)


async def test_a_medium_priority_issue_is_not_moved_to_the_sprint() -> None:
    calls: list[str] = []

    async def transport(method, url, headers, params, json_body):
        calls.append(url)
        return 200, {"key": "SCRUM-1"}

    await create_issue(
        summary="s", description="d", priority="medium", sprint_id=42,
        is_engineering_task=False, settings=_jira_settings(), transport=transport,
    )
    assert not any("sprint/42/issue" in u for u in calls)


async def test_a_sprint_move_failure_does_not_fail_issue_creation() -> None:
    """The issue already exists and is more valuable un-sprinted than lost."""
    async def transport(method, url, headers, params, json_body):
        if "sprint" in url:
            return 500, {}
        return 200, {"key": "SCRUM-1"}

    key = await create_issue(
        summary="s", description="d", priority="high", sprint_id=42,
        is_engineering_task=False, settings=_jira_settings(), transport=transport,
    )
    assert key == "SCRUM-1"


async def test_active_sprint_id_returns_none_when_no_sprint_is_active() -> None:
    async def transport(method, url, headers, params, json_body):
        return 200, {"values": []}

    assert await active_sprint_id(settings=_jira_settings(), transport=transport) is None


async def test_active_sprint_id_returns_the_first_active_sprint() -> None:
    async def transport(method, url, headers, params, json_body):
        return 200, {"values": [{"id": 7}, {"id": 8}]}

    assert await active_sprint_id(settings=_jira_settings(), transport=transport) == 7


async def test_a_kanban_boards_400_is_not_retried_and_returns_none() -> None:
    """Regression test for a live finding: a Kanban board returns 400 'the
    board does not support sprints' for this endpoint, a permanent property
    of the board rather than a transient failure. Retrying it three times
    wasted ~14s on every push for no benefit, since jira_pusher already
    treats any failure here as 'proceed without a sprint'."""
    import httpx

    calls: list[str] = []

    async def transport(method, url, headers, params, json_body):
        calls.append(url)
        request = httpx.Request("GET", url)
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("400", request=request, response=response)

    result = await active_sprint_id(settings=_jira_settings(), transport=transport)
    assert result is None
    assert len(calls) == 1, "a permanent 400 must not be retried"


async def test_move_to_sprint_posts_the_issue_key() -> None:
    seen: dict = {}

    async def transport(method, url, headers, params, json_body):
        seen["url"], seen["body"] = url, json_body
        return 200, {}

    await move_to_sprint("SCRUM-1", 42, settings=_jira_settings(), transport=transport)
    assert "sprint/42/issue" in seen["url"]
    assert seen["body"]["issues"] == ["SCRUM-1"]


# ─── jira_pusher (exit criteria: confidence gating, dedup) ────────────────────
#
# push_action_items takes each graph_client / jira_client call it makes as its
# own injectable keyword — the same flat-injection style as pipeline.process —
# rather than a bundled object, so a test only wires the calls it cares about.

from meeting_notes.models import ExtractedMeeting  # noqa: E402


def _meeting(**over) -> ExtractedMeeting:
    base = {"title": "Sync", "kind": "meeting", "platform": "email", "date": "2026-08-20",
           "summary": "s"}
    base.update(over)
    return ExtractedMeeting.model_validate(base)


async def test_below_threshold_items_go_to_needs_review_and_create_no_ticket() -> None:
    """Exit criterion: confidence gating works."""
    from meeting_notes import jira_pusher

    reviewed: list[tuple] = []
    created_calls: list[dict] = []

    async def mark_needs_review(action_id, reason, **kw):
        reviewed.append((action_id, reason))

    async def create_issue(**kw):
        created_calls.append(kw)
        return "SCRUM-1"

    settings = _jira_settings(JIRA_ENABLED=True, JIRA_CONFIDENCE_THRESHOLD=0.6)
    meeting = _meeting(action_items=[
        {"owner": "alice@corp.com", "task": "low confidence item", "confidence": 0.3}
    ])
    keys = await jira_pusher.push_action_items(
        meeting.action_items, meeting, "src-1", settings=settings,
        mark_needs_review=mark_needs_review, create_issue=create_issue,
    )

    assert keys == []
    assert created_calls == [], "no Jira call for a below-threshold item"
    assert len(reviewed) == 1


async def test_above_threshold_items_create_a_ticket() -> None:
    from meeting_notes import jira_pusher

    updated_keys: list[tuple] = []

    async def create_issue(**kw):
        return "SCRUM-1"

    async def update_jira_key(action_id, jira_key, **kw):
        updated_keys.append((action_id, jira_key))

    settings = _jira_settings(
        JIRA_ENABLED=True, JIRA_CONFIDENCE_THRESHOLD=0.6, JIRA_DEDUP_ENABLED=False
    )
    meeting = _meeting(action_items=[
        {"owner": "alice@corp.com", "task": "ship it", "confidence": 0.9}
    ])
    keys = await jira_pusher.push_action_items(
        meeting.action_items, meeting, "src-1", settings=settings,
        create_issue=create_issue, update_jira_key=update_jira_key,
    )

    assert keys == ["SCRUM-1"]
    assert updated_keys[0][1] == "SCRUM-1"


async def test_a_near_duplicate_links_mentioned_in_instead_of_a_second_ticket() -> None:
    """Exit criterion: dedup works — the same action item raised twice does
    not open a second ticket."""
    from meeting_notes import jira_pusher

    existing = {
        "id": "action-old", "task": "ship it", "jira_key": "SCRUM-1", "embedding": [1.0, 0.0]
    }
    created_calls: list[dict] = []
    linked: list[tuple] = []

    async def get_open_actions(owner_email, *, exclude_id, **kw):
        return [existing]

    async def create_issue(**kw):
        created_calls.append(kw)
        return "SCRUM-999"

    async def fake_embed(text, **kw):
        return [1.0, 0.0]  # identical to the existing item -> similarity 1.0

    async def link_mentioned_in(action_id, meeting_id, **kw):
        linked.append((action_id, meeting_id))

    settings = _jira_settings(JIRA_ENABLED=True, JIRA_DEDUP_ENABLED=True, JIRA_DEDUP_THRESHOLD=0.9)
    meeting = _meeting(action_items=[
        {"owner": "alice@corp.com", "task": "ship it", "confidence": 0.9}
    ])
    keys = await jira_pusher.push_action_items(
        meeting.action_items, meeting, "src-1", settings=settings,
        get_open_actions=get_open_actions, create_issue=create_issue,
        embed=fake_embed, link_mentioned_in=link_mentioned_in,
    )

    assert keys == [], "a duplicate must not report a newly-created key"
    assert created_calls == [], "no second Jira ticket for a near-duplicate"
    assert linked, "the duplicate must link MENTIONED_IN to the existing item"


async def test_disabled_jira_is_a_clean_no_op() -> None:
    from meeting_notes import jira_pusher

    settings = _jira_settings(JIRA_ENABLED=False)
    meeting = _meeting(action_items=[{"owner": "a", "task": "t", "confidence": 0.9}])
    keys = await jira_pusher.push_action_items(meeting.action_items, meeting, "src-1", settings=settings)
    assert keys == []


async def test_no_action_items_is_a_clean_no_op() -> None:
    from meeting_notes import jira_pusher

    settings = _jira_settings(JIRA_ENABLED=True)
    meeting = _meeting(action_items=[])
    keys = await jira_pusher.push_action_items([], meeting, "src-1", settings=settings)
    assert keys == []


# ─── jira_sync ─────────────────────────────────────────────────────────────────


async def test_jira_sync_marks_the_record_processed_whether_or_not_it_matched() -> None:
    from meeting_notes import jira_sync

    async def update_status(key, status, done, **kw):
        return key == "SCRUM-1"  # only this key exists in the graph

    marked = RecordingMarker()
    matched = await jira_sync.sync_one(
        {"key": "SCRUM-999", "status": "Done"}, record_id="rec-2",
        update_status=update_status, mark_processed=marked,
    )

    assert matched is False, "an unmatched key is real signal, not a bug"
    assert marked.ids == ["rec-2"], "still marked processed either way"


async def test_jira_sync_reports_a_match() -> None:
    from meeting_notes import jira_sync

    async def update_status(key, status, done, **kw):
        return True

    marked = RecordingMarker()
    matched = await jira_sync.sync_one(
        {"key": "SCRUM-1", "status": "Done"}, record_id="rec-1",
        update_status=update_status, mark_processed=marked,
    )
    assert matched is True


async def test_jira_sync_computes_done_from_status() -> None:
    from meeting_notes import jira_sync

    seen = {}

    async def update_status(key, status, done, **kw):
        seen["done"] = done
        return True

    await jira_sync.sync_one(
        {"key": "SCRUM-1", "status": "Closed"}, record_id="r",
        update_status=update_status, mark_processed=RecordingMarker(),
    )
    assert seen["done"] is True


# ─── pipeline_drain (Task 5: the drain loop) ───────────────────────────────────

from meeting_notes.pipeline_drain import drain_batch  # noqa: E402


def _staged(source_type: str, record_id: str = "r1", payload: dict | None = None) -> StagedRecord:
    return StagedRecord(
        id=record_id, source_id=f"src-{record_id}", source_type=source_type,
        payload=payload or {}, fetched_at="2026-08-20T00:00:00Z",
    )


async def test_drain_routes_jira_records_to_jira_sync() -> None:
    calls: list[str] = []

    async def fake_process(record, adapter, **kw):
        calls.append("pipeline")
        return None

    async def fake_sync(payload, *, record_id, **kw):
        calls.append("jira_sync")
        return True

    await drain_batch(
        [_staged("jira", payload={"key": "SCRUM-1", "status": "Done"})],
        process=fake_process, sync_jira=fake_sync,
    )
    assert calls == ["jira_sync"]


async def test_drain_routes_meeting_sources_to_the_pipeline() -> None:
    calls: list[str] = []

    async def fake_process(record, adapter, **kw):
        calls.append(record.source_type)
        return None

    for source_type in ("email", "calendar", "meet"):
        await drain_batch([_staged(source_type)], process=fake_process, sync_jira=None)
    assert calls == ["email", "calendar", "meet"]


async def test_one_bad_record_does_not_stop_the_batch() -> None:
    """v5's process_new_emails used asyncio.gather(..., return_exceptions=True)
    for exactly this reason: one exploding record must not silently drop
    every other record behind it in the same batch."""
    processed: list[str] = []

    async def flaky_process(record, adapter, **kw):
        if record.id == "bad":
            raise RuntimeError("boom")
        processed.append(record.id)
        return None

    records = [_staged("email", "ok1"), _staged("email", "bad"), _staged("email", "ok2")]
    result = await drain_batch(records, process=flaky_process, sync_jira=None)

    assert processed == ["ok1", "ok2"]
    assert result.errors == 1
    assert result.processed == 2


async def test_drain_reports_batch_counters() -> None:
    async def fake_process(record, adapter, **kw):
        return None

    result = await drain_batch(
        [_staged("email"), _staged("calendar")], process=fake_process, sync_jira=None
    )
    assert result.processed == 2
    assert result.errors == 0


# ─── source-authoritative dates (found auditing the real corpus) ──────────────


def test_a_calendar_events_start_overrides_the_models_guess() -> None:
    """Regression test for a real corruption found in the live graph.

    A recurring series had five instances -- Jan 13, Jan 20, Feb 3, Feb 10,
    Feb 17 -- all stamped 2026-01-13, because the model read a date out of the
    event description and `repair()` only fills a date when the model returns
    a null-like one. `start` is ground truth for a calendar event; the model
    inferring one from prose is strictly worse, and getting it wrong silently
    corrupts timeline order and every temporal chain built from it.
    """
    from meeting_notes.pipeline import adapter_for

    adapter = adapter_for("calendar")
    overrides = adapter.extract_overrides({"start": "2026-02-17T11:00:00-08:00"})
    assert overrides == {"date": "2026-02-17"}


def test_a_meet_recordings_start_time_overrides_too() -> None:
    from meeting_notes.pipeline import adapter_for

    adapter = adapter_for("meet")
    assert adapter.extract_overrides({"start_time": "2026-03-01T09:00:00Z"}) == {
        "date": "2026-03-01"
    }


def test_an_email_date_does_NOT_override() -> None:
    """A mail header date is when the MESSAGE was sent, which is often not when
    the meeting it discusses happened. Here the model reading the thread
    genuinely can do better, so it must keep its answer."""
    from meeting_notes.pipeline import adapter_for

    adapter = adapter_for("email")
    assert adapter.extract_overrides({"date": "2026-02-17T10:00:00Z"}) == {}


def test_a_missing_start_overrides_nothing() -> None:
    """No ground truth means no override -- never blank out a date the model
    supplied with an empty one."""
    from meeting_notes.pipeline import adapter_for

    assert adapter_for("calendar").extract_overrides({}) == {}
    assert adapter_for("meet").extract_overrides({"start_time": ""}) == {}


async def test_process_actually_applies_the_override_to_the_written_meeting() -> None:
    """The tests above check extract_overrides() in isolation, which passes
    even if process() never calls it. This drives the real path and asserts
    the meeting HANDED TO THE GRAPH carries the corrected date."""
    from meeting_notes import extractor, pipeline
    from meeting_notes.models import ExtractedMeeting, StagedRecord

    written: dict = {}

    async def capture_upsert(meeting, source_id):
        written["date"] = str(meeting.date)
        return "m1"

    async def noop_push(actions, meeting, source_id):
        return None

    async def noop_mark(record_id):
        return None

    async def fake_extract(*a, **kw):
        # The model infers the series' start date from the description --
        # exactly what happened live.
        return ExtractedMeeting.model_validate({
            "title": "QA AI Pilot : Touchpoints", "kind": "meeting",
            "platform": "google_calendar", "date": "2026-01-13", "summary": "recurring sync",
        })

    record = StagedRecord(
        id="r1", source_id="s1", source_type="calendar",
        payload={"summary": "QA AI Pilot : Touchpoints standup",
                 "description": ("Recurring sync; series began 2026-01-13. Agenda: review "
                                 "action items, decide on scope, assign owners for follow-up."),
                 "start": "2026-02-17T11:00:00-08:00",
                 "end": "2026-02-17T11:30:00-08:00",
                 "attendees": [{"email": "a@corp.com"}, {"email": "b@corp.com"}]},
        fetched_at="2026-02-17T00:00:00Z", processed=False,
    )

    original = extractor.extract_meeting
    extractor.extract_meeting = fake_extract  # type: ignore[assignment]
    try:
        result = await pipeline.process(
            record, pipeline.adapter_for("calendar"),
            upsert=capture_upsert, push_jira=noop_push, mark_processed=noop_mark,
            enrich_fn=lambda m, mid: None,
        )
    finally:
        extractor.extract_meeting = original  # type: ignore[assignment]

    assert result.status == "processed"
    assert written["date"] == "2026-02-17", (
        "the calendar event's own start must win over the model's inferred date"
    )


# ─── calendar attendees are ground truth, not something to infer ──────────────


def test_calendar_attendee_emails_override_the_models_guess() -> None:
    """The Calendar API tells us exactly who was invited, with addresses.

    Found by rebuilding the graph from scratch: the adapter passed only the
    title, the date and an attendee *count*, so the extractor inferred
    attendees from prose like "Matteo <> Shubham: Daily CBS Standup" -- names
    with no emails, which person_resolver can only send to the review queue.
    That one meeting produced people=0, unresolved=2 while both addresses sat
    unused in the payload. Across the corpus it was 71 "no-email-no-match"
    reviews and 20 ATTENDED edges where the source knew better.
    """
    from meeting_notes.pipeline import adapter_for

    payload = {
        "summary": "Matteo <> Shubham: Daily CBS Standup",
        "description": "",
        "start": "2026-02-26T11:30:00-08:00",
        "end": "2026-02-26T11:45:00-08:00",
        "attendees": [
            {"name": "", "email": "matteo.vaiente@onixnet.com", "organizer": True},
            {"name": "Shubham Gaur", "email": "shubham.gaur@onixnet.com", "organizer": False},
        ],
    }
    overrides = adapter_for("calendar").extract_overrides(payload)

    assert "attendees" in overrides, "the invitee list must override the model's guess"
    by_email = {a["email"]: a for a in overrides["attendees"]}
    assert set(by_email) == {"matteo.vaiente@onixnet.com", "shubham.gaur@onixnet.com"}
    # A blank name in the payload still has to produce something resolvable.
    assert by_email["matteo.vaiente@onixnet.com"]["name"].strip()
    assert by_email["shubham.gaur@onixnet.com"]["name"] == "Shubham Gaur"
    assert by_email["matteo.vaiente@onixnet.com"]["role"] == "organizer"
    # The date override must survive alongside it.
    assert overrides["date"] == "2026-02-26"


def test_a_calendar_event_with_no_attendees_overrides_nothing() -> None:
    """A payload without an invitee list must not blank out what the model found."""
    from meeting_notes.pipeline import adapter_for

    overrides = adapter_for("calendar").extract_overrides(
        {"summary": "Focus time", "start": "2026-02-26T11:30:00-08:00", "attendees": []}
    )
    assert "attendees" not in overrides


def test_an_attendee_without_an_email_is_not_invented() -> None:
    """A resource row (a room, a mailing list with no address) must not become
    a Person with a fabricated email."""
    from meeting_notes.pipeline import adapter_for

    overrides = adapter_for("calendar").extract_overrides(
        {"summary": "s", "start": "2026-02-26T11:30:00-08:00",
         "attendees": [{"name": "Conf Room A", "email": ""},
                       {"name": "Real Person", "email": "real@onixnet.com"}]}
    )
    assert [a["email"] for a in overrides["attendees"]] == ["real@onixnet.com"]


async def test_source_overrides_are_validated_not_just_assigned() -> None:
    """`model_copy(update=...)` does NOT validate.

    Passing the calendar invitee list through it left `meeting.attendees` as
    raw dicts, and `person_resolver.resolve` reads attributes with getattr, so
    every dict silently became an attendee with no name and no email and went
    straight to the review queue. Re-running 10 calendar records with the
    override in place moved Person 6 -> 6 and PersonReview 95 -> 103: the fix
    made things worse, silently.

    The date override survived the same bug only by luck -- a str where a date
    was expected still renders through str().
    """
    from meeting_notes.models import Attendee
    from meeting_notes.pipeline import apply_source_overrides

    meeting = _meeting(attendees=[{"name": "Guessed", "role": "attendee"}])
    updated = apply_source_overrides(meeting, {
        "date": "2026-02-26",
        "attendees": [{"name": "Matteo Vaiente", "email": "matteo@onixnet.com",
                       "role": "organizer"}],
    })

    assert all(isinstance(a, Attendee) for a in updated.attendees), (
        "attendees must be validated models, not raw dicts"
    )
    assert updated.attendees[0].email == "matteo@onixnet.com"
    assert str(updated.date) == "2026-02-26"


def test_a_mapping_attendee_still_resolves_by_email() -> None:
    """Defence in depth for the failure above: `resolve` accepts Any, and a
    dict silently produced an empty attendee rather than failing loudly."""
    from meeting_notes.person_resolver import Roster, resolve

    r = resolve({"name": "Matteo Vaiente", "email": "matteo@onixnet.com"}, Roster([]))
    assert r.email == "matteo@onixnet.com", f"a mapping was dropped: {r.reason}"
    assert r.status == "resolved"


def test_email_adapter_resolves_first_name_against_header_recipients() -> None:
    """EmailAdapter extracts header recipients and enriches first-name mentions."""
    from meeting_notes.pipeline import EmailAdapter, apply_source_overrides

    adapter = EmailAdapter()
    payload = {
        "from": "Mallory Webber <mallory.webber@onixnet.com>",
        "to": "Michael Baylard <michael.baylard@onixnet.com>, Natalie Miller <natalie.miller@onixnet.com>",
        "body": "Best, Mallory & Natalie",
    }
    overrides = adapter.extract_overrides(payload)
    assert "_header_recipients" in overrides
    assert any(r["email"] == "natalie.miller@onixnet.com" for r in overrides["_header_recipients"])

    extracted_meeting = _meeting(attendees=[
        {"name": "Mallory Webber", "email": "mallory.webber@onixnet.com", "role": "organizer"},
        {"name": "Natalie", "role": "organizer"},  # no email in extracted body
    ])
    enriched = apply_source_overrides(extracted_meeting, overrides)
    natalie = next(a for a in enriched.attendees if "Natalie" in a.name)
    assert natalie.email == "natalie.miller@onixnet.com"
    assert natalie.name == "Natalie Miller"
