"""P6 meeting-type routing: a cheap classifier between classify() and extract_meeting().

`classify()` stays the "is this worth processing" gate. This adds a second cheap, rules-based
step that picks a meeting TYPE, so extraction can use a prompt suited to that type — different
types produce structurally different action items. The type list is derived from real meeting
titles in the data (standups/syncs/touchpoints dominate; then planning/workshops, demos/reviews,
1:1s, and email threads).

NOT the same vocabulary as `models.ExtractedMeeting.kind`. `kind` is what the
LLM says the meeting was; TYPES picks which extraction prompt to use. This
module can return `planning`, `one_on_one` or `general`, none of which are
valid `kind` values -- so `meeting.kind = route(...)` raises. The two are
deliberately separate; a test in tests/test_phase02_pure_core.py pins them
apart so a future "helpful" merge fails at build time.
"""
from __future__ import annotations

TYPES: list[str] = ["standup", "planning", "review", "one_on_one", "email_thread", "general"]

_KEYWORDS = {
    "standup": (
        "standup", "stand-up", "daily", "sync", "touchpoint", "touch point", "touchpoints",
        "status", "tool updates", "check-in", "checkin", "scrum",
    ),
    "planning": (
        "planning", "sprint", "roadmap", "kpi", "backlog", "kickoff", "kick-off",
        "strategy", "workshop", "discussion", "grooming",
    ),
    "review": (
        "demo", "review", "retro", "retrospective", "walkthrough", "education",
        "training", "showcase", "session",
    ),
    "one_on_one": ("1:1", "1-1", "one-on-one", "one on one", "catch up", "catchup"),
}


def route(title: str, text: str = "", source_type: str = "") -> str:
    """Return the meeting type for `title`/`text`. Email sources are always `email_thread`."""
    if source_type == "email":
        return "email_thread"
    hay = f"{title or ''} {text or ''}".lower()
    # Order matters: standup/planning/review checked before the generic 'session' in review.
    for mtype in ("standup", "planning", "one_on_one", "review"):
        if any(kw in hay for kw in _KEYWORDS[mtype]):
            return mtype
    return "general"


_HINTS = {
    "standup": (
        "This is a recurring status sync / standup. Action items are short, owner-scoped status "
        "follow-ups (blockers, next steps) — capture only concrete commitments, do not invent "
        "long-form tasks. Decisions are rare here."
    ),
    "planning": (
        "This is a planning / workshop session. Emphasize decisions and forward-looking action "
        "items with clear owners and due dates; capture scope and priorities."
    ),
    "review": (
        "This is a demo / review session. Emphasize feedback and follow-up fixes as action items; "
        "capture what was shown and what needs changing."
    ),
    "one_on_one": (
        "This is a 1:1. Action items are personal follow-ups / commitments; be conservative and do "
        "not over-extract shared team tasks."
    ),
    "email_thread": (
        "This is an email thread, not a live meeting. Only extract action items explicitly "
        "requested in the text; attendees are the correspondents."
    ),
    "general": "",
}


def prompt_hint(meeting_type: str) -> str:
    """Return the type-specific instruction appended to the extractor system prompt."""
    return _HINTS.get(meeting_type, "")
