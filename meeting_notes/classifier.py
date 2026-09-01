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

# High-confidence automated-noise patterns: a single match is enough to
# discard the email regardless of sender. These are machine-generated phrases
# that a human does not write to another human — a one-time passcode is never
# the SUBJECT of a discussion, it is the message.
#
# The bar for this tier is deliberately high. Anything a colleague might
# plausibly say in a genuine thread belongs in the OPERATIONAL tier below,
# because a single match here discards the email before extraction and that
# loss is silent.
_EMAIL_NOISE_PATTERNS_HIGH = [
    # 2FA / OTP / Sign-in alerts
    re.compile(r"\bone-time (code|passcode|password)\b", re.I),
    re.compile(r"\bverification code\b", re.I),
    re.compile(r"\bsecurity code\b", re.I),
    re.compile(r"\bsign-on notification\b", re.I),
    re.compile(r"\bnew login to\b", re.I),
    # Out of office / Auto-responses
    re.compile(r"\b(out of office|automatic reply|auto[- ]?reply|autoreply)\b", re.I),
]

# Operational tier: real phrases from HR, billing and IT notification systems
# that are ALSO ordinary things to hold a meeting about. "Timecard" is a
# payroll nag and a migration project; "reset your password" is an Okta email
# and a spec line. Matching one of these is evidence, not proof, so it drops
# the mail only alongside a second hit or an automated sender.
#
# These lived in the HIGH tier originally, where each one silently discarded
# genuine threads: "Weekly sync: timecard system migration kickoff" scored 0.0.
_EMAIL_NOISE_PATTERNS_OPERATIONAL = [
    # Credentials — split, not alternated, so a real reset mail (which says
    # both) still reaches two hits without a sender.
    re.compile(r"\bpassword reset\b", re.I),
    re.compile(r"\breset your password\b", re.I),
    re.compile(r"\btemporary password\b", re.I),
    # HR / payroll
    re.compile(r"\btimecard\b", re.I),
    re.compile(r"\bmissing time\b", re.I),
    re.compile(r"\bpay statement\b", re.I),
    # Billing / receipts. `order .* confirmed` was unanchored and spanned the
    # whole body, so "In order to move forward we need the design confirmed"
    # matched; the bounded form below cannot reach across a sentence.
    re.compile(r"\border(\s+#?\w+)?\s+(has been\s+|is\s+)?confirmed\b", re.I),
    re.compile(r"\bbilling statement\b", re.I),
    re.compile(r"\bpayment received\b", re.I),
    re.compile(r"\binvoice #", re.I),
    # Security training
    re.compile(r"\bphishing simulation\b", re.I),
    re.compile(r"\bsecurity awareness\b", re.I),
]

# Weak patterns: common in automated emails but also appear in legitimate
# threads. Require >= 2 matches (or a no-reply sender + >= 1 match) to drop.
_EMAIL_NOISE_PATTERNS_WEAK = [
    re.compile(r"\bunsubscribe\b", re.I),
    re.compile(r"\bpromotion\b", re.I),
    re.compile(r"\bnewsletter\b", re.I),
    re.compile(r"\bno[-.]?reply\b", re.I),
    re.compile(r"\bdonotreply\b", re.I),
    re.compile(r"\bmarketing\b", re.I),
]

# Senders that only ever emit machine mail. One soft hit from one of these is
# enough, because a human is not on the other end to be misread.
_AUTOMATED_SENDER_TERMS = ("no-reply", "noreply", "donotreply", "notifications")

# Keep the old name as a combined alias for backwards compatibility with any
# direct imports in tests; classify() now uses the split lists above.
_EMAIL_NOISE_PATTERNS = (
    _EMAIL_NOISE_PATTERNS_HIGH
    + _EMAIL_NOISE_PATTERNS_OPERATIONAL
    + _EMAIL_NOISE_PATTERNS_WEAK
)


def classify(text: str, metadata: dict[str, Any]) -> float:
    score = 0.0
    text_lower = text.lower()
    words = set(re.findall(r"\b\w+\b", text_lower))

    # Penalty for noise patterns (marketing/auto emails/auth alerts), in three
    # tiers of decreasing confidence. Only the first drops the mail on its own;
    # the other two need corroboration, because a false positive here is
    # invisible — the email never reaches extraction and nothing reports it.
    if any(p.search(text) for p in _EMAIL_NOISE_PATTERNS_HIGH):
        return 0.0

    soft_hits = sum(
        1
        for p in (*_EMAIL_NOISE_PATTERNS_OPERATIONAL, *_EMAIL_NOISE_PATTERNS_WEAK)
        if p.search(text)
    )
    if soft_hits >= 1:
        sender = str(metadata.get("from", "")).lower()
        if any(term in sender for term in _AUTOMATED_SENDER_TERMS):
            return 0.0
        if soft_hits >= 2:
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
