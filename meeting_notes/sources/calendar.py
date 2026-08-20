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

Transport = Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]


def event_time(slot: dict[str, Any] | None) -> str:
    """A start/end slot as a string, whichever shape it uses."""
    if not slot:
        return ""
    return slot.get("dateTime") or slot.get("date") or ""


class CalendarSource:
    source_type = "calendar_event"

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
    async def _get(self, url: str) -> dict[str, Any]:
        return await self._transport(url, {"Authorization": f"Bearer {self._token}"})

    async def fetch(self, since: str | None) -> list[FetchedRecord]:
        url = (
            f"{CALENDAR_API}?maxResults={self._max_results}"
            "&singleEvents=true&orderBy=updated"
        )
        if since:
            url += f"&updatedMin={since}"

        body = await self._get(url)

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


async def _default_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
