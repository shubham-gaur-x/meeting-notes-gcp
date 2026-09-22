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


def _repair_metadata(data: dict[str, Any], ctx: dict[str, Any]) -> None:
    if _is_null_like(data.get("platform")):
        data["platform"] = ctx.get("platform", "unknown")
    if _is_null_like(data.get("date")):
        data["date"] = ctx.get("date") or datetime.now(UTC).strftime("%Y-%m-%d")
    if _is_null_like(data.get("summary")):
        data["summary"] = data.get("title") or "No summary available"


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
        if o:
            if o != "Unknown" and is_junk_name(o):
                item["owner"] = "Unassigned"
            elif o.lower() in ("colin", "coalie", "colie", "coaly"):
                item["owner"] = "Coley"
            elif o.lower() in ("lp", "l.p.", "l p"):
                item["owner"] = "LeePatrick McIntire"


def _repair_attendees(attendees: list[Any]) -> list[dict[str, Any]]:
    from meeting_notes.person_resolver import is_junk_name

    cleaned: list[dict[str, Any]] = []
    for att in attendees:
        if not isinstance(att, dict) or is_junk_name(att.get("name")):
            continue
        n = str(att.get("name", "")).strip()
        if n.lower() in ("colin", "coalie", "colie", "coaly"):
            att["name"] = "Coley"
        elif n.lower() in ("lp", "l.p.", "l p"):
            att["name"] = "LeePatrick McIntire"
            att["email"] = "leepatrick.mcintire@onixnet.com"
        cleaned.append(att)
    return cleaned


def repair(data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill required fields the model left null-like, in place.

    Carried from v5 unchanged. Every check goes through `_is_null_like` rather
    than a truthiness test, because the literal string "null" is truthy.
    """
    ctx = context or {}
    _repair_metadata(data, ctx)

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

    if isinstance(data.get("summary"), str):
        data["summary"] = re.sub(r"\bColin\b", "Coley", data["summary"])

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
        meeting = ExtractedMeeting.model_validate(repair(data, context))
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
