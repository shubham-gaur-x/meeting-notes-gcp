"""Phase 5 — the connectors. No live credentials, no network, no database.

Every source takes an injected transport and an injected staging callable, so
the whole file runs offline. The live checks are Task 8 of the plan and are
run by hand against the real Onix account.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from meeting_notes.sources.base import FetchedRecord, stage_all

# ─── the staging seam ─────────────────────────────────────────────────────────


class RecordingStager:
    """Stands in for db.stage_record + db.set_watermark."""

    def __init__(self, already_staged: set[str] | None = None) -> None:
        self.staged: list[FetchedRecord] = []
        self.watermarks: dict[str, str] = {}
        self._already = already_staged or set()

    async def stage(self, record: FetchedRecord) -> str | None:
        if record.source_id in self._already:
            return None  # ON CONFLICT DO NOTHING
        self._already.add(record.source_id)
        self.staged.append(record)
        return f"id-{record.source_id}"

    async def set_watermark(self, source_type: str, value: str) -> None:
        self.watermarks[source_type] = value


class FakeSource:
    source_type = "email"

    def __init__(self, records: list[FetchedRecord], fail_after: int | None = None) -> None:
        self._records = records
        self._fail_after = fail_after

    async def fetch(self, since: str | None) -> list[FetchedRecord]:
        return self._records


async def test_stage_all_stages_every_fetched_record() -> None:
    stager = RecordingStager()
    records = [
        FetchedRecord("m1", "email", {"subject": "a"}, watermark="100"),
        FetchedRecord("m2", "email", {"subject": "b"}, watermark="200"),
    ]
    result = await stage_all(FakeSource(records), stager.stage, stager.set_watermark, since=None)

    assert result.staged == 2
    assert [r.source_id for r in stager.staged] == ["m1", "m2"]


async def test_stage_all_advances_the_watermark_to_the_newest_record() -> None:
    stager = RecordingStager()
    records = [
        FetchedRecord("m1", "email", {}, watermark="100"),
        FetchedRecord("m2", "email", {}, watermark="300"),
        FetchedRecord("m3", "email", {}, watermark="200"),
    ]
    await stage_all(FakeSource(records), stager.stage, stager.set_watermark, since=None)

    assert stager.watermarks["email"] == "300", "the watermark must be the max, not the last"


async def test_the_watermark_advances_only_after_staging_succeeds() -> None:
    """Ordering is a correctness property, not a preference.

    Advancing first means a mid-batch failure permanently skips records — and
    that is invisible until someone asks why a week of meetings is missing.
    """
    calls: list[str] = []

    async def failing_stage(record: FetchedRecord) -> str | None:
        calls.append("stage")
        raise RuntimeError("database went away")

    async def watermark(source_type: str, value: str) -> None:
        calls.append("watermark")

    records = [FetchedRecord("m1", "email", {}, watermark="100")]
    with pytest.raises(RuntimeError):
        await stage_all(FakeSource(records), failing_stage, watermark, since=None)

    assert "watermark" not in calls, "the watermark advanced despite staging failing"


async def test_restaging_a_known_record_is_counted_as_skipped_not_staged() -> None:
    """Re-running a connector must stage no duplicates (exit criterion)."""
    stager = RecordingStager(already_staged={"m1"})
    records = [
        FetchedRecord("m1", "email", {}, watermark="100"),
        FetchedRecord("m2", "email", {}, watermark="200"),
    ]
    result = await stage_all(FakeSource(records), stager.stage, stager.set_watermark, since=None)

    assert result.staged == 1
    assert result.skipped == 1


async def test_an_empty_fetch_leaves_the_watermark_untouched() -> None:
    """No records means nothing new; moving the watermark would be a lie."""
    stager = RecordingStager()
    result = await stage_all(FakeSource([]), stager.stage, stager.set_watermark, since="500")

    assert result.staged == 0
    assert stager.watermarks == {}


async def test_the_since_value_is_passed_through_to_the_source() -> None:
    seen: dict[str, Any] = {}

    class Recording(FakeSource):
        async def fetch(self, since: str | None) -> list[FetchedRecord]:
            seen["since"] = since
            return []

    await stage_all(Recording([]), RecordingStager().stage, RecordingStager().set_watermark,
                    since="watermark-value")
    assert seen["since"] == "watermark-value"


# ─── google_auth: the expiry path is an exit criterion ────────────────────────

from meeting_notes.config import Settings  # noqa: E402
from meeting_notes.google_auth import TokenExpired, get_access_token  # noqa: E402


def _google_settings(**over: object) -> Settings:
    base = dict(
        _env_file=None,
        GOOGLE_OAUTH_CLIENT_ID="cid",
        GOOGLE_OAUTH_CLIENT_SECRET="csecret",
        GOOGLE_REFRESH_TOKEN="rtoken-leakcanary",
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


async def test_a_good_refresh_returns_an_access_token() -> None:
    async def ok(url: str, data: dict) -> tuple[int, str]:
        return 200, json.dumps({"access_token": "at-123", "expires_in": 3599})

    token = await get_access_token(_google_settings(), transport=ok)
    assert token == "at-123"


async def test_an_expired_refresh_token_raises_rather_than_returning_none() -> None:
    """Exit criterion: a deliberately expired token produces a visible alert,
    not silent failure.

    Returning None here would let a connector stage zero rows and report
    success, which looks exactly like "no new meetings this week" — the single
    most misleading outcome available on a 7-day token clock.
    """
    async def expired(url: str, data: dict) -> tuple[int, str]:
        return 400, json.dumps({"error": "invalid_grant", "error_description": "Token expired"})

    with pytest.raises(TokenExpired) as exc:
        await get_access_token(_google_settings(), transport=expired)

    assert "auth-spike" in str(exc.value), "the alert must name the command that fixes it"
    assert "--reconsent" in str(exc.value)


async def test_the_refresh_token_is_never_in_the_error_message() -> None:
    """docs/GOOGLE_AUTH.md §7 — the token value is never emitted, and an
    exception message is the easiest place for one to leak into logs."""
    async def expired(url: str, data: dict) -> tuple[int, str]:
        return 400, json.dumps({"error": "invalid_grant"})

    with pytest.raises(TokenExpired) as exc:
        await get_access_token(_google_settings(), transport=expired)

    assert "leakcanary" not in str(exc.value)


async def test_a_missing_refresh_token_is_a_clear_error_not_a_crash() -> None:
    with pytest.raises(TokenExpired) as exc:
        await get_access_token(_google_settings(GOOGLE_REFRESH_TOKEN=""))
    assert "auth-spike" in str(exc.value)


async def test_a_server_error_is_not_mistaken_for_an_expired_token() -> None:
    """A 500 is transient; calling it "expired" would send someone to
    re-consent a token that was fine."""
    async def boom(url: str, data: dict) -> tuple[int, str]:
        return 503, "upstream unavailable"

    with pytest.raises(Exception) as exc:
        await get_access_token(_google_settings(), transport=boom)
    assert not isinstance(exc.value, TokenExpired)


# ─── gmail ────────────────────────────────────────────────────────────────────

import base64  # noqa: E402

from meeting_notes.sources.gmail import GmailSource, extract_body, header  # noqa: E402


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extracts_a_plain_text_body() -> None:
    payload = {"mimeType": "text/plain", "body": {"data": _b64("hello there")}}
    assert extract_body(payload) == "hello there"


def test_extracts_a_body_from_nested_multipart_parts() -> None:
    """Real Gmail nests: multipart/mixed > multipart/alternative > text/plain.
    A single-level scan silently returns empty for most real mail."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("the real body")}},
                    {"mimeType": "text/html", "body": {"data": _b64("<p>ignored</p>")}},
                ],
            }
        ],
    }
    assert extract_body(payload) == "the real body"


def test_prefers_plain_text_over_html() -> None:
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("plain")}},
        ],
    }
    assert extract_body(payload) == "plain"


def test_falls_back_to_html_when_there_is_no_plain_part() -> None:
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [{"mimeType": "text/html", "body": {"data": _b64("<p>only html</p>")}}],
    }
    assert "only html" in extract_body(payload)


def test_a_message_with_no_body_returns_empty_rather_than_crashing() -> None:
    """Calendar invites and attachment-only mail have no text part at all."""
    assert extract_body({"mimeType": "multipart/mixed", "parts": []}) == ""
    assert extract_body({}) == ""


def test_undecodable_body_data_does_not_crash_the_whole_batch() -> None:
    payload = {"mimeType": "text/plain", "body": {"data": "!!!not base64!!!"}}
    assert extract_body(payload) == ""


def test_header_lookup_is_case_insensitive() -> None:
    """Gmail returns 'Subject', RFC 5322 does not guarantee the casing."""
    headers = [{"name": "subject", "value": "Weekly sync"}]
    assert header(headers, "Subject") == "Weekly sync"


def test_missing_header_returns_empty_string() -> None:
    assert header([], "Subject") == ""


# --- fetching ---


def _gmail_transport(list_body: dict, messages: dict[str, dict]):
    async def transport(url: str, headers: dict) -> dict:
        if "/messages/" in url:
            return messages[url.rsplit("/", 1)[-1].split("?")[0]]
        return list_body

    return transport


async def test_the_query_carries_the_watermark() -> None:
    seen: list[str] = []

    async def transport(url: str, headers: dict) -> dict:
        seen.append(url)
        return {"messages": []}

    source = GmailSource(access_token="at", transport=transport)
    await source.fetch(since="1700000000000")

    assert any("after/" in u or "after" in u for u in seen), f"watermark not in query: {seen}"


async def test_a_fetched_message_becomes_a_staged_record() -> None:
    list_body = {"messages": [{"id": "m1"}]}
    messages = {
        "m1": {
            "id": "m1",
            "internalDate": "1700000000000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Budget sync"},
                    {"name": "From", "value": "alice@corp.com"},
                    {"name": "To", "value": "bob@corp.com"},
                ],
                "mimeType": "text/plain",
                "body": {"data": _b64("we discussed the budget")},
            },
        }
    }
    source = GmailSource(access_token="at", transport=_gmail_transport(list_body, messages))
    records = await source.fetch(since=None)

    assert len(records) == 1
    record = records[0]
    assert record.source_id == "m1", "the Gmail message id is the dedup key"
    assert record.source_type == "email"
    assert record.watermark == "1700000000000"
    assert record.payload["subject"] == "Budget sync"
    assert record.payload["from"] == "alice@corp.com"
    assert "budget" in record.payload["body"]


async def test_no_messages_yields_no_records() -> None:
    source = GmailSource(access_token="at", transport=_gmail_transport({}, {}))
    assert await source.fetch(since=None) == []


# ─── calendar ─────────────────────────────────────────────────────────────────

from meeting_notes.sources.calendar import CalendarSource, event_time  # noqa: E402


def test_event_time_reads_a_timed_event() -> None:
    assert event_time({"dateTime": "2026-08-20T10:00:00Z"}) == "2026-08-20T10:00:00Z"


def test_event_time_reads_an_all_day_event() -> None:
    """All-day events carry `date`, not `dateTime`. Assuming dateTime is a
    KeyError on every all-day event, which is most recurring team events."""
    assert event_time({"date": "2026-08-20"}) == "2026-08-20"


def test_event_time_of_a_missing_slot_is_empty() -> None:
    assert event_time({}) == ""
    assert event_time(None) == ""


async def test_updated_min_carries_the_watermark() -> None:
    seen: list[str] = []

    async def transport(url: str, headers: dict) -> dict:
        seen.append(url)
        return {"items": []}

    await CalendarSource(access_token="at", transport=transport).fetch(
        since="2026-08-01T00:00:00Z"
    )
    assert any("updatedMin=" in u for u in seen), f"watermark not sent: {seen}"


async def test_a_cancelled_event_is_skipped() -> None:
    """Cancelled events still come back from the API. Staging them would put
    meetings in the graph that never happened."""
    body = {
        "items": [
            {"id": "e1", "status": "cancelled", "updated": "2026-08-20T10:00:00Z"},
            {
                "id": "e2", "status": "confirmed", "summary": "Real meeting",
                "updated": "2026-08-20T11:00:00Z",
                "start": {"dateTime": "2026-08-20T10:00:00Z"},
                "end": {"dateTime": "2026-08-20T11:00:00Z"},
            },
        ]
    }

    async def transport(url: str, headers: dict) -> dict:
        return body

    records = await CalendarSource(access_token="at", transport=transport).fetch(since=None)
    assert [r.source_id for r in records] == ["e2"]


async def test_attendees_and_description_survive_into_the_payload() -> None:
    body = {
        "items": [
            {
                "id": "e1", "status": "confirmed", "summary": "Planning",
                "description": "agenda: budget",
                "updated": "2026-08-20T11:00:00Z",
                "location": "Room 3",
                "start": {"dateTime": "2026-08-20T10:00:00Z"},
                "end": {"dateTime": "2026-08-20T11:00:00Z"},
                "attendees": [
                    {"email": "a@corp.com", "displayName": "Alice", "organizer": True},
                    {"email": "b@corp.com", "displayName": "Bob"},
                ],
            }
        ]
    }

    async def transport(url: str, headers: dict) -> dict:
        return body

    records = await CalendarSource(access_token="at", transport=transport).fetch(since=None)
    payload = records[0].payload

    assert payload["summary"] == "Planning"
    assert payload["description"] == "agenda: budget"
    assert payload["location"] == "Room 3"
    assert len(payload["attendees"]) == 2
    assert payload["attendees"][0]["email"] == "a@corp.com"
    assert records[0].watermark == "2026-08-20T11:00:00Z"


async def test_an_all_day_event_does_not_crash_the_batch() -> None:
    body = {
        "items": [
            {
                "id": "e1", "status": "confirmed", "summary": "Company offsite",
                "updated": "2026-08-20T11:00:00Z",
                "start": {"date": "2026-08-20"},
                "end": {"date": "2026-08-21"},
            }
        ]
    }

    async def transport(url: str, headers: dict) -> dict:
        return body

    records = await CalendarSource(access_token="at", transport=transport).fetch(since=None)
    assert records[0].payload["start"] == "2026-08-20"
