"""LLM extraction — v5's tuned prompt, v6's swappable client.

The system prompt below is carried over from v5 **byte for byte**. It is
tuned, and `tests/test_phase04_llm_seam.py` diffs it against the v5 file so a
well-meaning reword fails the suite rather than quietly degrading extraction.

`_is_null_like` is likewise unchanged. It exists because gemma3-12b emits the
literal string `"null"` for optional fields instead of a JSON null, and a
plain `if not value` misses that — `"null"` is a non-empty string, therefore
truthy (MIGRATION_FROM_V5.md #4). Every fallback here routes through it.

The one structural change from v5: this module no longer builds an
`openai.AsyncOpenAI` itself. It calls `llm_client.chat_json`, which is the
only module allowed to construct a client (CLAUDE.md).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import structlog

from meeting_notes import llm_client
from meeting_notes.config import Settings
from meeting_notes.models import ExtractedMeeting
from meeting_notes.prompts import EXTRACTION_SYSTEM_PROMPT

log = structlog.get_logger()

# Re-exported so callers and tests have one obvious name to reach for.
_SYSTEM_PROMPT = EXTRACTION_SYSTEM_PROMPT


def _is_null_like(value: Any) -> bool:
    """True for None/empty AND for a model that emits the literal string "null"
    instead of a JSON null (observed live: gemma3-12b sometimes does this for
    optional fields). A plain ``if not data.get(...)`` misses that case since a
    non-empty string is truthy, so every fallback below routes through this."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in ("", "null", "none", "n/a"):
        return True
    return False


def build_system_prompt(type_hint: str | None = None) -> str:
    """The system prompt, optionally with meeting-type guidance appended.

    The router's hint has to actually reach the model, or routing is decorative.
    """
    if not type_hint:
        return _SYSTEM_PROMPT
    return f"{_SYSTEM_PROMPT}\n\nMeeting-type guidance:\n{type_hint}"


def _extract_raw_urls(text: str) -> list[str]:
    """Harvest real resource and document URLs from source text.

    Filters out XML namespaces, image/logo assets, font files, and webmail anchors
    so only genuine document, project, and reference links enter the graph.
    """
    import re

    if not text:
        return []

    # Find candidate http(s) URLs
    urls = re.findall(r"https?://[^\s<>\")']+", text)
    cleaned: list[str] = []

    noise_domains = (
        "schemas.microsoft.com",
        "schemas.openxmlformats.org",
        "schemas.google.com",
        "w3.org",
        "xmlsoap.org",
        "mail.google.com/mail",
        "gstatic.com",
        "googleusercontent.com",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
    )

    noise_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".webp",
        ".css",
        ".js",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".map",
    )

    for u in urls:
        # Decode HTML entities commonly present in email/calendar HTML
        u = u.replace("&amp;", "&").strip()
        u = u.lstrip("(\"'<[").rstrip(".,;:)>]'\"")
        if len(u) < 10:
            continue
        u_lower = u.lower()
        if any(noise in u_lower for noise in noise_domains):
            continue
        if any(u_lower.endswith(ext) or f"{ext}?" in u_lower for ext in noise_extensions):
            continue
        cleaned.append(u)

    return list(dict.fromkeys(cleaned))


def repair(data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill required fields the model left null-like, in place.

    Carried from v5 unchanged. Every check goes through `_is_null_like` rather
    than a truthiness test, because the literal string "null" is truthy.
    """
    ctx = context or {}

    if _is_null_like(data.get("platform")):
        data["platform"] = ctx.get("platform", "unknown")
    if _is_null_like(data.get("date")):
        data["date"] = ctx.get("date") or datetime.now(UTC).strftime("%Y-%m-%d")
    if _is_null_like(data.get("summary")):
        data["summary"] = data.get("title") or "No summary available"

    # Merge extracted links with raw URLs present in source text/body
    raw_urls = _extract_raw_urls(ctx.get("text", "") or ctx.get("body", "") or "")
    existing_links = [
        link.strip() for link in (data.get("links") or []) if isinstance(link, str) and link.strip()
    ]
    data["links"] = list(dict.fromkeys(existing_links + raw_urls))

    # action_items: owner and task must be non-null strings, and an item is
    # repaired rather than dropped -- a nameless task is still a real task.
    for item in data.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        if _is_null_like(item.get("owner")):
            item["owner"] = "Unknown"
        if _is_null_like(item.get("task")):
            item["task"] = "Follow-up required"
        if "is_engineering_task" not in item:
            item["is_engineering_task"] = False
        if _is_null_like(item.get("confidence")):
            item["confidence"] = 1.0

    # decisions: the model's own validator coerces a plain string entry, so
    # only a null-like confidence on the dict form needs handling here.
    for decision in data.get("decisions") or []:
        if isinstance(decision, dict) and _is_null_like(decision.get("confidence")):
            decision["confidence"] = 1.0

    return data


async def extract_meeting(
    text: str,
    source_type: str,
    context: dict[str, Any] | None = None,
    type_hint: str | None = None,
    *,
    settings: Settings | None = None,
    transport: Any | None = None,
) -> ExtractedMeeting | None:
    """Extract one meeting. Returns None if the model output cannot be used.

    Retry policy, made explicit: transport failures are retried inside
    `llm_client`. A parse or validation failure returns None and is NOT
    retried -- extraction runs at temperature 0.0, so an identical retry
    yields identical output.
    """
    start = time.monotonic()
    system_prompt = build_system_prompt(type_hint)
    user_prompt = f"Extract meeting information from this {source_type}:\n\n{text}"

    data = await llm_client.chat_json(
        system_prompt, user_prompt, temperature=0.0, settings=settings, transport=transport
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    if data is None:
        log.error("extractor.parse_failed", source_type=source_type, duration_ms=duration_ms)
        return None

    try:
        enriched_ctx = {"text": text, "source_type": source_type, **(context or {})}
        meeting = ExtractedMeeting.model_validate(repair(data, enriched_ctx))
    except Exception as exc:  # noqa: BLE001 - reported, then surfaced as None
        log.error(
            "extractor.validate_failed",
            source_type=source_type,
            duration_ms=duration_ms,
            error=str(exc),
        )
        return None

    log.info(
        "extractor.success",
        source_type=source_type,
        text_length=len(text),
        duration_ms=duration_ms,
        confidence=meeting.confidence,
        title=meeting.title,
    )
    return meeting
