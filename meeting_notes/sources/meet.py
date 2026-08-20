"""Google Meet transcripts — ported from v5's `meet_ingest.py`.

The one connector v5 actually owned, because Airbyte has no Meet-transcript
source. Workspace Events publishes
`google.workspace.meet.transcript.v2.fileGenerated` to a Pub/Sub topic; we
**pull** rather than push, so no inbound endpoint is needed — the pattern v5
already proved.

**An unset `MEET_PUBSUB_SUBSCRIPTION` disables this cleanly as a no-op**, per
`.env.example`. Phase 0.5 confirmed Meet transcription IS enabled on the Onix
tenant (ADR-012), so this is a first-class source rather than the degraded
path `GOOGLE_AUTH.md` §6 once assumed.

Messages are acked **only after** staging succeeds. Acking first means a
crash mid-stage loses that transcript permanently — Pub/Sub will not redeliver
an acked message, and Meet transcripts cannot be re-fetched once the event is
gone.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from meeting_notes.sources.base import FetchedRecord
from meeting_notes.utils import with_retry

log = structlog.get_logger()

MEET_API = "https://meet.googleapis.com/v2"
PUBSUB_API = "https://pubsub.googleapis.com/v1"

# (method, url, headers, params, json_body) -> parsed json
Transport = Callable[
    [str, str, dict[str, str], dict[str, Any] | None, dict[str, Any] | None],
    Awaitable[dict[str, Any]],
]


def decode_event(message: dict[str, Any]) -> dict[str, Any] | None:
    """Decode one Pub/Sub message into transcript coordinates.

    The fileGenerated event carries a resource name shaped
    `conferenceRecords/{cr}/transcripts/{t}`. Returns None for anything that
    does not parse — a malformed event should be skipped and logged, not
    crash the pull loop and block every other transcript behind it.
    """
    try:
        raw = (message.get("message") or {}).get("data", "")
        decoded = base64.b64decode(raw).decode("utf-8") if raw else "{}"
        event = json.loads(decoded)
        name = event.get("name") or event.get("resourceName") or ""
        parts = name.split("/")
        conference_record = parts[1] if len(parts) > 1 else None
        transcript = parts[3] if len(parts) > 3 else None
        if not conference_record or not transcript:
            return None
        return {
            "conference_record": conference_record,
            "transcript": transcript,
            "title": event.get("title", ""),
            "start_time": event.get("startTime"),
        }
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        log.warning("meet.decode_failed", source_event="fileGenerated", error=str(exc))
        return None


def entries_to_text(entries: list[dict[str, Any]]) -> str:
    """Speaker-tagged plain text, which is what the extractor expects."""
    lines = []
    for entry in entries:
        who = (entry.get("participant", "") or "").split("/")[-1] or "speaker"
        lines.append(f"{who}: {entry.get('text', '')}")
    return "\n".join(lines)


class MeetSource:
    source_type = "meet"

    def __init__(
        self,
        access_token: str,
        subscription: str,
        *,
        transport: Transport | None = None,
        max_messages: int = 20,
    ) -> None:
        self._token = access_token
        self._subscription = subscription
        self._transport = transport or _default_transport
        self._max_messages = max_messages
        self._ack_ids: list[str] = []

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    @with_retry(max_attempts=3, base_delay=2.0)
    async def _call(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._transport(method, url, self._headers(), params, json_body)

    async def _transcript_text(self, conference_record: str, transcript: str) -> str:
        url = (
            f"{MEET_API}/conferenceRecords/{conference_record}"
            f"/transcripts/{transcript}/entries"
        )
        entries: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            data = await self._call("GET", url, params=params)
            entries.extend(data.get("transcriptEntries") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return entries_to_text(entries)

    async def fetch(self, since: str | None) -> list[FetchedRecord]:
        """Pull pending transcript events. `since` is unused — Pub/Sub itself
        is the watermark, since an acked message is never redelivered."""
        if not self._subscription.strip():
            log.info("meet.no_subscription", source_event="skip")
            return []

        pulled = await self._call(
            "POST",
            f"{PUBSUB_API}/{self._subscription}:pull",
            json_body={"maxMessages": self._max_messages},
        )

        records: list[FetchedRecord] = []
        self._ack_ids = []

        for message in pulled.get("receivedMessages") or []:
            event = decode_event(message)
            if event is None:
                # Ack it anyway: a malformed event will never become valid, and
                # leaving it unacked blocks the subscription forever.
                self._ack_ids.append(message["ackId"])
                continue

            text = await self._transcript_text(event["conference_record"], event["transcript"])
            records.append(
                FetchedRecord(
                    source_id=f"{event['conference_record']}/{event['transcript']}",
                    source_type=self.source_type,
                    payload={
                        "title": event["title"],
                        "start_time": event["start_time"],
                        "conference_record": event["conference_record"],
                        "transcript": event["transcript"],
                        "text": text,
                    },
                    watermark=event["start_time"],
                )
            )
            self._ack_ids.append(message["ackId"])

        log.info("meet.fetched", source_event="pull", count=len(records))
        return records

    async def acknowledge(self) -> None:
        """Ack the messages from the last fetch.

        Called by the job AFTER staging succeeds. Acking inside fetch() would
        lose a transcript permanently on a staging failure: Pub/Sub does not
        redeliver an acked message and Meet transcripts cannot be re-fetched
        once the event is gone.
        """
        if not self._ack_ids:
            return
        await self._call(
            "POST",
            f"{PUBSUB_API}/{self._subscription}:acknowledge",
            json_body={"ackIds": self._ack_ids},
        )
        log.info("meet.acknowledged", source_event="ack", count=len(self._ack_ids))
        self._ack_ids = []


async def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.request(
            method, url, headers=headers, params=params, json=json_body
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json() if response.content else {}
        return result
