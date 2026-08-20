"""Gmail connector — new code; Airbyte did this in v5.

Incremental by `internalDate` (epoch milliseconds), which Gmail exposes both
as a field and as an `after:` query operator. That is the watermark.

The fiddly part is the body. Gmail returns MIME as a nested tree — real mail
is routinely `multipart/mixed > multipart/alternative > text/plain` — and the
payload is base64**url**, not plain base64. A single-level scan silently
returns an empty body for most messages, which then looks like an extraction
problem rather than an ingestion one, so `extract_body` recurses and has
tests for each shape.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from meeting_notes.sources.base import FetchedRecord
from meeting_notes.utils import with_retry

log = structlog.get_logger()

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me/messages"

# Gmail's `after:` operator takes seconds; internalDate is milliseconds.
_MS_PER_SECOND = 1000

Transport = Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]


def header(headers: list[dict[str, str]], name: str) -> str:
    """Case-insensitive header lookup. RFC 5322 does not fix the casing."""
    target = name.lower()
    for entry in headers or []:
        if entry.get("name", "").lower() == target:
            return entry.get("value", "")
    return ""


def _decode(data: str) -> str:
    """base64url → text. Returns "" rather than raising.

    One unparseable body must not fail a whole batch; the message still
    stages with its headers, which are often enough to be useful.
    """
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        return ""


def _collect_parts(payload: dict[str, Any], out: dict[str, str]) -> None:
    """Walk the MIME tree, keeping the first body found per mime type."""
    mime = payload.get("mimeType", "")
    data = (payload.get("body") or {}).get("data", "")

    if data and mime not in out:
        decoded = _decode(data)
        if decoded:
            out[mime] = decoded

    for part in payload.get("parts") or []:
        _collect_parts(part, out)


def extract_body(payload: dict[str, Any]) -> str:
    """The message body as text, preferring text/plain over text/html."""
    found: dict[str, str] = {}
    _collect_parts(payload or {}, found)

    if "text/plain" in found:
        return found["text/plain"].strip()
    if "text/html" in found:
        return found["text/html"].strip()
    # Some senders use an unusual mime type; take anything textual.
    for mime, text in found.items():
        if mime.startswith("text/"):
            return text.strip()
    return ""


class GmailSource:
    """Fetch messages changed since the watermark and shape them for staging."""

    source_type = "email"

    def __init__(
        self,
        access_token: str,
        *,
        transport: Transport | None = None,
        max_results: int = 50,
    ) -> None:
        self._token = access_token
        self._transport = transport or _default_transport
        self._max_results = max_results

    @with_retry(max_attempts=3, base_delay=2.0)
    async def _get(self, url: str) -> dict[str, Any]:
        return await self._transport(url, {"Authorization": f"Bearer {self._token}"})

    async def fetch(self, since: str | None) -> list[FetchedRecord]:
        query = ""
        if since:
            # internalDate is ms; `after:` wants seconds. Subtracting nothing and
            # relying on `after:` being inclusive-ish is fine — the unique
            # constraint on (source_type, source_id) makes a re-fetch a no-op.
            try:
                query = f"&q=after:{int(since) // _MS_PER_SECOND}"
            except (TypeError, ValueError):
                query = ""

        listing = await self._get(f"{GMAIL_API}?maxResults={self._max_results}{query}")

        records: list[FetchedRecord] = []
        for stub in listing.get("messages") or []:
            message = await self._get(f"{GMAIL_API}/{stub['id']}?format=full")
            payload = message.get("payload") or {}
            headers = payload.get("headers") or []

            records.append(
                FetchedRecord(
                    source_id=message["id"],
                    source_type=self.source_type,
                    payload={
                        "subject": header(headers, "Subject"),
                        "from": header(headers, "From"),
                        "to": header(headers, "To"),
                        "cc": header(headers, "Cc"),
                        "date": header(headers, "Date"),
                        "thread_id": message.get("threadId", ""),
                        "body": extract_body(payload),
                    },
                    watermark=str(message.get("internalDate", "")) or None,
                )
            )

        log.info("gmail.fetched", source_event="list", count=len(records))
        return records


async def _default_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
