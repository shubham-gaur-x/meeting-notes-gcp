"""Google Calendar connector — new code; Airbyte did this in v5.

Incremental by `updatedMin`, with the event's own `updated` timestamp as the
watermark. `singleEvents=true` expands recurring series into instances, which
is what we want: a weekly standup should be many meetings in the graph, not
one node that keeps being overwritten.

Two shapes bite here and both have tests. Events carry either `dateTime` (a
timed event) or `date` (an all-day event) — assuming the former is a KeyError
on every all-day event, which is most recurring team events. And cancelled
events still come back from the API; staging them would put meetings in the
graph that never happened.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from meeting_notes.sources.base import FetchedRecord
from meeting_notes.utils import with_retry

log = structlog.get_logger()

CALENDAR_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

# (url, headers) -> (status, parsed json). The status is surfaced because
# a 410 is meaningful here rather than merely an error — see fetch().
Transport = Callable[[str, dict[str, str]], Awaitable[tuple[int, dict[str, Any]]]]


def event_time(slot: dict[str, Any] | None) -> str:
    """A start/end slot as a string, whichever shape it uses."""
    if not slot:
        return ""
    return slot.get("dateTime") or slot.get("date") or ""


class CalendarSource:
    source_type = "calendar"

    def __init__(
        self,
        access_token: str,
        *,
        transport: Transport | None = None,
        max_results: int = 100,
    ) -> None:
        self._token = access_token
        self._transport = transport or _default_transport
        self._max_results = max_results

    @with_retry(max_attempts=3, base_delay=2.0)
    async def _get(self, url: str) -> tuple[int, dict[str, Any]]:
        return await self._transport(url, {"Authorization": f"Bearer {self._token}"})

    def _url(self, since: str | None) -> str:
        url = (
            f"{CALENDAR_API}?maxResults={self._max_results}"
            "&singleEvents=true&orderBy=updated"
        )
        return f"{url}&updatedMin={since}" if since else url

    async def fetch(self, since: str | None) -> list[FetchedRecord]:
        status, body = await self._get(self._url(since))

        # 410 Gone means updatedMin is outside Calendar's incremental window.
        # Google's documented remedy is a full sync, and without this the
        # connector is permanently broken after its first successful run --
        # every subsequent call sends a watermark the API refuses. Found by
        # running it for real, not by review.
        if status == 410 and since:
            log.warning(
                "calendar.incremental_window_expired",
                source_event="410",
                discarded_watermark=since,
            )
            status, body = await self._get(self._url(None))

        if status >= 400:
            raise RuntimeError(f"Calendar API returned HTTP {status}")

        records: list[FetchedRecord] = []
        skipped_cancelled = 0
        for event in body.get("items") or []:
            if event.get("status") == "cancelled":
                skipped_cancelled += 1
                continue

            records.append(
                FetchedRecord(
                    source_id=event["id"],
                    source_type=self.source_type,
                    payload={
                        "summary": event.get("summary", ""),
                        "description": event.get("description", ""),
                        "location": event.get("location", ""),
                        "start": event_time(event.get("start")),
                        "end": event_time(event.get("end")),
                        "organizer": (event.get("organizer") or {}).get("email", ""),
                        "attendees": [
                            {
                                "email": a.get("email", ""),
                                "name": a.get("displayName", ""),
                                "organizer": bool(a.get("organizer")),
                            }
                            for a in event.get("attendees") or []
                        ],
                        "hangout_link": event.get("hangoutLink", ""),
                    },
                    watermark=event.get("updated"),
                )
            )

        log.info(
            "calendar.fetched",
            source_event="list",
            count=len(records),
            skipped_cancelled=skipped_cancelled,
        )
        return records


async def _default_transport(url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """Returns the status rather than raising, so fetch() can act on a 410."""
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code >= 500:
            response.raise_for_status()  # transient: let with_retry handle it
        body: dict[str, Any] = response.json() if response.content else {}
        return response.status_code, body
