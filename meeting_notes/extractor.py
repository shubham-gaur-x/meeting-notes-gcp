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

import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

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


MAX_RAW_URL_INPUT_CHARS = 500_000
MAX_RAW_URL_LENGTH = 2048
MAX_MERGED_LINKS = 100


def _normalize_url(url: str) -> str:
    """Normalize a URL for case-insensitive deduplication, stripping trailing slashes."""
    return url.lower().rstrip("/")


def _clean_url_candidate(token: str) -> str | None:
    """Trim punctuation, apply balanced paren heuristic, and enforce candidate length bounds."""
    u = token.strip().rstrip(".,;:>\x27\"")
    while u.endswith(")") and u.count(")") > u.count("("):
        u = u[:-1]
    u = u.rstrip("]")
    if len(u) < 10:
        return None
    if len(u) > MAX_RAW_URL_LENGTH:
        log.warning(
            "extractor.raw_url_length_exceeded",
            length=len(u),
            max_length=MAX_RAW_URL_LENGTH,
        )
        return None
    return u


def _extract_raw_urls(text: str) -> list[str]:
    """Harvest genuine resource and document URLs from source text.

    Scans text for http/https URLs and filters common noise domains (schemas, fonts,
    static assets, and standard webmail links). Applies basic trailing punctuation
    trimming with a single-level heuristic to retain balanced parentheses for doc links.
    """
    if not text:
        return []

    if len(text) > MAX_RAW_URL_INPUT_CHARS:
        log.warning(
            "extractor.raw_url_input_truncated",
            length=len(text),
            max_chars=MAX_RAW_URL_INPUT_CHARS,
        )
        text = text[:MAX_RAW_URL_INPUT_CHARS]

    # Find URL candidates starting with http:// or https:// delimited by whitespace, quotes, or brackets
    raw_candidates = re.findall(r"https?://[^\s<>\"\x27`]+", text, re.IGNORECASE)
    candidate_tokens: list[str] = []
    for c in raw_candidates:
        # Split joined URLs if multiple URLs were concatenated with commas or semicolons without spaces
        for sub in re.split(r"[,;](?=https?://)", c, flags=re.IGNORECASE):
            candidate_tokens.append(sub)

    cleaned: list[str] = []
    seen: set[str] = set()

    noise_domains = (
        "schemas.microsoft.com",
        "schemas.openxmlformats.org",
        "schemas.google.com",
        "w3.org",
        "xmlsoap.org",
        "mail.google.com",
        "outlook.office.com",
        "outlook.live.com",
        "mail.yahoo.com",
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
    )

    for token in candidate_tokens:
        u = _clean_url_candidate(token)
        if u is None:
            continue
        if not re.match(r"^https?://[a-zA-Z0-9\-.]+\.[a-zA-Z]{2,}", u, re.IGNORECASE):
            continue
        parsed = urlsplit(u)
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()

        if any(netloc == d or netloc.endswith(f".{d}") for d in noise_domains):
            continue
        if any(path.endswith(ext) for ext in noise_extensions):
            continue
        norm_key = _normalize_url(u)
        if norm_key in seen:
            continue
        seen.add(norm_key)
        cleaned.append(u)

    return cleaned


def _merge_links(existing_links: list[Any] | None, raw_urls: list[str]) -> list[str]:
    """Merge model-extracted links with raw-harvested URLs.

    Existing links take precedence in order; duplicates (by normalized key)
    from raw URLs are omitted. Non-string items in existing_links trigger a warning log.
    Total merged output is capped at MAX_MERGED_LINKS.
    """
    valid_links: list[str] = []
    for link in existing_links or []:
        if isinstance(link, str) and link.strip():
            valid_links.append(link.strip())
        else:
            log.warning("extractor.invalid_link_item_skipped", item=str(link))

    seen_links: set[str] = set()
    merged: list[str] = []
    for link in valid_links + raw_urls:
        norm = _normalize_url(link)
        if norm not in seen_links:
            seen_links.add(norm)
            merged.append(link)

    if len(merged) > MAX_MERGED_LINKS:
        log.warning(
            "extractor.merged_links_capped",
            count=len(merged),
            max_links=MAX_MERGED_LINKS,
        )
        merged = merged[:MAX_MERGED_LINKS]

    return merged


def _repair_action_items(items: list[Any]) -> None:
    from meeting_notes.person_resolver import is_junk_name

    for item in items:
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

        o = str(item.get("owner", "")).strip()
        if o and o != "Unknown" and is_junk_name(o):
            item["owner"] = "Unassigned"


def _repair_attendees(attendees: list[Any]) -> list[dict[str, Any]]:
    from meeting_notes.person_resolver import is_junk_name

    cleaned: list[dict[str, Any]] = []
    for att in attendees:
        if not isinstance(att, dict) or is_junk_name(att.get("name")):
            continue
        cleaned.append(att)
    return cleaned


def repair(data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill required fields the model left null-like, in place, and merge raw URLs.

    Carried from v5 with link harvesting extension. Every null check goes through
    `_is_null_like` rather than a truthiness test, because the literal string "null"
    is truthy. Also harvests and deduplicates raw document/ecosystem URLs from context
    into data["links"].
    """
    ctx = context or {}

    if _is_null_like(data.get("platform")):
        data["platform"] = ctx.get("platform", "unknown")
    if _is_null_like(data.get("date")):
        data["date"] = ctx.get("date", datetime.now(UTC).strftime("%Y-%m-%d"))
    if _is_null_like(data.get("summary")):
        data["summary"] = data.get("title") or "No summary available"

    # Merge extracted links with raw URLs present in source text/body
    raw_urls = _extract_raw_urls(ctx.get("text", "") or ctx.get("body", "") or "")
    data["links"] = _merge_links(data.get("links"), raw_urls)

    # action_items: owner and task must be non-null strings, and an item is
    # repaired rather than dropped -- a nameless task is still a real task.
    _repair_action_items(data.get("action_items") or [])

    # decisions: the model's own validator coerces a plain string entry, so
    # only a null-like confidence on the dict form needs handling here.
    for decision in data.get("decisions") or []:
        if isinstance(decision, dict) and _is_null_like(decision.get("confidence")):
            decision["confidence"] = 1.0

    if "attendees" in data and isinstance(data["attendees"], list):
        data["attendees"] = _repair_attendees(data["attendees"])

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
        # Caller context supplies supplementary metadata, but text and source_type
        # are canonical to this extraction execution and cannot be overridden.
        enriched_ctx = {
            **(context or {}),
            "text": text,
            "source_type": source_type,
        }
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
