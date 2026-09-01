"""Shared helpers with no I/O: deterministic ids, retries, logging, parsing.

Ported from v5 (`transform_service/utils.py`). Typing is modernised to 3.11+
and return hints added; behaviour is deliberately unchanged. `uuid5_id` in
particular must keep producing byte-identical ids — a change there silently
forks every node id and MERGE starts creating duplicates instead of matching.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import re
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any, TypeVar, cast

import structlog

F = TypeVar("F", bound=Callable[..., Any])

_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def uuid5_id(namespace: str, value: str) -> str:
    """Deterministic id for a node.

    Two-step on purpose: derive a per-namespace UUID first, then the value
    under it. Do not "simplify" this to a single uuid5 over a joined string —
    it produces different ids, and every id already in a graph would fork.
    """
    ns = uuid.uuid5(_NAMESPACE, namespace)
    return str(uuid.uuid5(ns, value))


# Jira-style ticket key: 2+ uppercase letters, hyphen, digits (e.g. SCRUM-47). Word
# boundaries avoid matching inside longer tokens. Used for MENTIONS edges
# (Meeting -> Ticket) via regex over meeting text — no LLM.
_TICKET_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def extract_ticket_keys(text: str | None) -> list[str]:
    """Return de-duplicated Jira ticket keys found in free text, order-preserving."""
    if not text:
        return []
    seen: dict[str, None] = {}
    for m in _TICKET_KEY_RE.findall(text):
        seen.setdefault(m, None)
    return list(seen)


def gmail_thread_url(source_id: Any) -> str | None:
    """Deep link to the originating Gmail thread, or None if there isn't one.

    Only `gmail:` sources have one. Calendar rows and Meet transcripts reach
    the caller too, and a Gmail URL built for a Meet transcript is a link that
    goes nowhere -- which an LLM will happily cite as a source.
    """
    sid = str(source_id or "")
    if not sid.startswith("gmail:"):
        return None
    thread_id = sid.split(":")[-1].strip()
    if not thread_id:
        return None
    return f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"


def strip_json_fences(raw: str) -> str:
    """Local models often wrap JSON responses in ```json ... ``` fences despite
    being told to respond with raw JSON only. Strip them before json.loads()."""
    stripped = (raw or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()


def configure_logging() -> structlog.BoundLogger:
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    # structlog.get_logger() is untyped, and pyproject sets warn_return_any.
    # The cast is honest: wrapper_class above pins the concrete type.
    return cast(structlog.BoundLogger, structlog.get_logger())


def with_retry(max_attempts: int = 3, base_delay: float = 2.0) -> Callable[[F], F]:
    """Retry an async callable with exponential backoff.

    Async only — the wrapper awaits the wrapped function. Transport errors are
    what this is for; a JSON parse failure at temperature 0 is deterministic
    and must NOT be retried (CLAUDE.md).
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            log = structlog.get_logger()
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts:
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    log.warning(
                        "retry",
                        fn=fn.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

        return wrapper  # type: ignore[return-value]

    return decorator


def priority_from_due(due: date | None) -> str:
    """Map a due date to a Jira priority. No due date is 'low', not 'medium'."""
    if due is None:
        return "low"
    delta = (due - date.today()).days
    if delta <= 14:
        return "high"
    if delta <= 60:
        return "medium"
    return "low"
