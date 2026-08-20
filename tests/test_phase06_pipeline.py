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
        return json.dumps({"choices": [{"message": {"content": "not json at all"}}]})

    settings = Settings(_env_file=None, LLM_BACKEND="lmstudio", LM_STUDIO_MODEL="m",
                        LM_STUDIO_BASE_URL="http://localhost:1234/v1")
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


async def test_an_engineering_task_gets_no_label() -> None:
    """Engineering tasks flow through the normal board, not a meeting-derived
    holding label -- carried from v5 exactly."""
    seen: dict = {}

    async def transport(method, url, headers, params, json_body):
        seen.update(json_body or {})
        return 200, {"key": "SCRUM-1"}

    await create_issue(
        summary="s", description="d", priority="medium", sprint_id=None,
        is_engineering_task=True, settings=_jira_settings(), transport=transport,
    )
    assert "labels" not in seen["fields"]


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


async def test_move_to_sprint_posts_the_issue_key() -> None:
    seen: dict = {}

    async def transport(method, url, headers, params, json_body):
        seen["url"], seen["body"] = url, json_body
        return 200, {}

    await move_to_sprint("SCRUM-1", 42, settings=_jira_settings(), transport=transport)
    assert "sprint/42/issue" in seen["url"]
    assert seen["body"]["issues"] == ["SCRUM-1"]
