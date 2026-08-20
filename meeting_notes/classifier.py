"""Rules-based "is this worth processing" score. No LLM.

Ported from v5 (`transform_service/classifier.py`) with typing modernised and
a return hint added. **The weights are deliberately unchanged** — they were
fitted against real v5 data, and this phase is a port, not a retune.

This is the cheap gate in front of extraction (ARCHITECTURE §5 step 3): below
`classifier_score_threshold` the record is marked processed and no LLM is
called. v5 shipped this with no test coverage at all, which is why the Phase 2
suite covers it.
"""

from __future__ import annotations

import re
from typing import Any

_MEETING_KEYWORDS = {
    "meeting", "call", "standup", "sync", "review", "demo", "interview",
    "discussion", "conference", "webinar", "workshop", "session", "agenda",
    "minutes", "recap", "follow-up", "followup",
    # additional work meeting terms
    "touchpoint", "touchpoints", "update", "updates", "pilot", "kickoff",
    "onboarding", "training", "debrief", "retrospective", "retro", "planning",
    "sprint", "checkin", "handoff", "walkthrough", "briefing", "alignment",
}

_ACTION_PATTERNS = [
    re.compile(r"\baction item\b", re.I),
    re.compile(r"\btodo\b", re.I),
    re.compile(r"\bto-do\b", re.I),
    re.compile(r"\baction required\b", re.I),
    re.compile(r"\bnext step\b", re.I),
    re.compile(r"\bplease\b.{0,40}\bby\b", re.I),
    re.compile(r"\bdeadline\b", re.I),
    re.compile(r"\bdue\b.{0,20}\bdate\b", re.I),
    re.compile(r"\bassigned to\b", re.I),
    re.compile(r"\bowner\b", re.I),
]

_DECISION_PATTERNS = [
    re.compile(r"\bwe (decided|agreed|concluded|resolved)\b", re.I),
    re.compile(r"\bdecision\b", re.I),
    re.compile(r"\bgoing forward\b", re.I),
    re.compile(r"\bapproved\b", re.I),
    re.compile(r"\brejected\b", re.I),
    re.compile(r"\bwe will\b", re.I),
]

_TIME_PATTERNS = [
    re.compile(r"\b\d{1,2}:\d{2}\s*(am|pm)?\b", re.I),
    re.compile(r"\bduration\b", re.I),
    re.compile(r"\bhour(s)?\b", re.I),
    re.compile(r"\bminute(s)?\b", re.I),
]

_EMAIL_NOISE_PATTERNS = [
    re.compile(r"\bunsubscribe\b", re.I),
    re.compile(r"\bpromotion\b", re.I),
    re.compile(r"\bnewsletter\b", re.I),
    re.compile(r"\bno.reply\b", re.I),
    re.compile(r"\bnoreply\b", re.I),
    re.compile(r"\bmarketing\b", re.I),
]


def classify(text: str, metadata: dict[str, Any]) -> float:
    score = 0.0
    text_lower = text.lower()
    words = set(re.findall(r"\b\w+\b", text_lower))

    # Penalty for noise patterns (marketing/auto emails)
    noise_hits = sum(1 for p in _EMAIL_NOISE_PATTERNS if p.search(text))
    if noise_hits >= 2:
        return 0.0

    # Signal 1: meeting keywords in subject/title (strong signal)
    keyword_hits = len(words & _MEETING_KEYWORDS)
    score += min(keyword_hits * 0.12, 0.35)

    # Signal 2: has attendees metadata
    if metadata.get("attendees") or metadata.get("attendees_count", 0) > 0:
        score += 0.15

    # Signal 3: action item patterns
    action_hits = sum(1 for p in _ACTION_PATTERNS if p.search(text))
    score += min(action_hits * 0.05, 0.20)

    # Signal 4: decision language
    decision_hits = sum(1 for p in _DECISION_PATTERNS if p.search(text))
    score += min(decision_hits * 0.06, 0.18)

    # Signal 5: time/duration references
    time_hits = sum(1 for p in _TIME_PATTERNS if p.search(text))
    score += min(time_hits * 0.04, 0.12)

    # Signal 6: multiple participant indicators (email addresses in body)
    email_count = len(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
    if email_count >= 2:
        score += 0.10
    elif email_count >= 1:
        score += 0.05

    # Signal 7: calendar event metadata presence
    if metadata.get("start_time") or metadata.get("end_time"):
        score += 0.15

    return min(score, 1.0)
