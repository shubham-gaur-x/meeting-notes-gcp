"""P3 entity resolution: resolve extracted attendees to canonical people.

Two tiers, run BEFORE ``memgraph_client.upsert_meeting_graph`` writes:
  1. Deterministic — normalize the email (fixes the duplicate-Person / duplicate-PageRank
     bug where any variant created a distinct node) and match against a synced roster
     (primary email + aliases).
  2. Probabilistic — fuzzy-match names that miss tier 1 against roster + existing Person
     nodes; below threshold, route to a review queue instead of auto-creating a node.

The no-email case is handled explicitly: hold for review, never silently drop (the old
``if not attendee.email: continue``). ``tracked`` is an opt-in gate (default False) that
per-person analytics must respect. This module issues NO Cypher — the caller supplies
known people via ``memgraph_client.get_known_people``.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

FUZZY_THRESHOLD = 0.85


def normalize_email(email: str | None) -> str:
    """Lowercase, trim, and drop any ``+tag`` from the local part."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return e
    local, _, domain = e.partition("@")
    local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def _norm_name(n: str | None) -> str:
    return re.sub(r"\s+", " ", (n or "").strip().lower())


def _name_sim(a: str, b: str) -> float:
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _given_name_matches(
    mention: str, known_people: list[dict[str, Any]]
) -> list[tuple[str | None, str | None, bool]]:
    """Known people whose given name equals a single-token mention.

    Only fires for a one-word mention: a full name that failed fuzzy matching
    should not be rescued by its first token, or "John Smith" would match
    "John Doe".
    """
    tokens = _norm_name(mention).split()
    if len(tokens) != 1:
        return []
    first = tokens[0]
    if len(first) < 3:  # "TK", "JD" -- initials are not a given name
        return []

    out: list[tuple[str | None, str | None, bool]] = []
    for person in known_people:
        parts = _norm_name(person.get("name")).split()
        if parts and parts[0] == first:
            out.append((person.get("email"), person.get("name"), bool(person.get("tracked", False))))
    return out


@dataclass
class RosterEntry:
    name: str
    email: str
    aliases: list[str] = field(default_factory=list)
    tracked: bool = False


@dataclass
class Resolution:
    name: str
    role: str = "attendee"
    email: str | None = None          # canonical email if resolved, else None
    status: str = "resolved"          # "resolved" | "review"
    tracked: bool = False
    reason: str = ""


class Roster:
    def __init__(self, entries: list[RosterEntry]):
        self.entries = entries
        self._by_email: dict[str, RosterEntry] = {}
        for e in entries:
            self._by_email[normalize_email(e.email)] = e
            for alias in e.aliases:
                self._by_email[normalize_email(alias)] = e

    def match_email(self, email: str) -> RosterEntry | None:
        return self._by_email.get(normalize_email(email))

    def match_name(
        self, name: str, threshold: float = FUZZY_THRESHOLD
    ) -> tuple[RosterEntry | None, float]:
        best: RosterEntry | None = None
        best_score = 0.0
        for e in self.entries:
            s = _name_sim(name, e.name)
            if s > best_score:
                best, best_score = e, s
        return (best, best_score) if best and best_score >= threshold else (None, best_score)


def load_roster(path: str | None) -> Roster:
    """Load the canonical roster from `path` (a JSON list), or an empty roster.

    v5 read PERSON_ROSTER_PATH from os.environ here. Nothing outside
    config.py may do that (CLAUDE.md), and injecting the path also makes
    this testable without touching the process environment. Callers pass
    `get_settings().person_roster_path`.
    """
    path = (path or "").strip()
    if not path or not Path(path).exists():
        return Roster([])
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("person_resolver.roster_load_failed", path=path, error=str(exc))
        return Roster([])
    return Roster([
        RosterEntry(
            name=d.get("name", ""),
            email=normalize_email(d.get("email", "")),
            aliases=[normalize_email(a) for a in d.get("aliases", [])],
            tracked=bool(d.get("tracked", False)),
        )
        for d in data if d.get("email")
    ])


def resolve(
    attendee: Any,
    roster: Roster,
    known_people: list[dict[str, Any]] | None = None,
    threshold: float = FUZZY_THRESHOLD,
) -> Resolution:
    """Resolve one attendee (anything with .name/.email/.role) to a canonical Resolution."""
    known_people = known_people or []
    # A mapping reads through getattr as an attendee with no fields at all,
    # which resolves to "no-email-no-match" instead of failing -- silent data
    # loss. Accept both shapes rather than trusting every caller to validate.
    if isinstance(attendee, Mapping):
        name = attendee.get("name") or ""
        role = attendee.get("role") or "attendee"
        email = attendee.get("email")
    else:
        name = getattr(attendee, "name", "") or ""
        role = getattr(attendee, "role", "attendee") or "attendee"
        email = getattr(attendee, "email", None)

    # Tier 1 — deterministic (email present)
    if email and "@" in email:
        ne = normalize_email(email)
        entry = roster.match_email(ne)
        if entry:
            return Resolution(
                entry.name or name, role, entry.email, "resolved", entry.tracked, "roster-email"
            )
        # Real email, not in roster → canonical is the normalized email (a new person).
        return Resolution(name, role, ne, "resolved", False, "email-normalized")

    # Tier 2 — probabilistic (no email): fuzzy name against roster, then known Person nodes.
    entry, score = roster.match_name(name, threshold)
    if entry:
        return Resolution(
            entry.name, role, entry.email, "resolved", entry.tracked, f"roster-name:{score:.2f}"
        )

    # `tracked` is carried in the tuple deliberately. v5 read it off `p`
    # after the loop -- the LAST person iterated, not the one that matched --
    # so the governance gate was decided by list ordering. Person.tracked is
    # opt-in (CLAUDE.md); getting it from the wrong person is a real leak.
    best: tuple[str | None, str | None, float, bool] = (None, None, 0.0, False)
    for p in known_people:
        s = _name_sim(name, p.get("name", ""))
        if s > best[2]:
            best = (p.get("email"), p.get("name"), s, bool(p.get("tracked", False)))
    if best[0] and best[2] >= threshold:
        return Resolution(
            best[1] or name, role, best[0], "resolved", best[3], f"person-name:{best[2]:.2f}"
        )

    # Unambiguous first-name match.
    #
    # Meeting notes refer to colleagues by first name constantly, and whole-string
    # similarity is hopeless at it: "Matteo" vs "Matteo Vaiente" scores 0.60 against a
    # 0.85 threshold, so EVERY first-name mention of a known person landed in the review
    # queue. Measured on the real corpus, that was most of it.
    #
    # Resolves only when the mention matches exactly ONE known person's given name. Two
    # Matteos means genuine ambiguity, and guessing between colleagues is worse than
    # asking -- so it stays in review.
    given = _given_name_matches(name, known_people)
    if len(given) == 1:
        email, full, tracked = given[0]
        return Resolution(full or name, role, email, "resolved", tracked, "person-given-name")
    if len(given) > 1:
        return Resolution(name, role, None, "review", False, "ambiguous-given-name")

    # Give up → review. Never silently drop.
    return Resolution(name, role, None, "review", False, "no-email-no-match" if not email else "unresolved")


def resolve_attendees(
    attendees: list[Any],
    roster: Roster,
    known_people: list[dict[str, Any]] | None = None,
) -> tuple[list[Resolution], list[Resolution]]:
    """Return (resolved, reviews) for a list of attendees."""
    resolved: list[Resolution] = []
    reviews: list[Resolution] = []
    for a in attendees:
        r = resolve(a, roster, known_people=known_people)
        (resolved if r.status == "resolved" else reviews).append(r)
    return resolved, reviews


async def reresolve_reviews(
    driver: Any = None, *, roster_path: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """Retry the review queue against everyone the graph now knows.

    Resolution is order-dependent: a meeting processed before any Person node
    existed sends its attendees to review, and they stay there even once a
    later meeting introduces the same person with an email. Measured on the
    real corpus, 39% of the queue was resolvable at the time of writing.

    So the queue is not a backlog of failures — it is a snapshot of what was
    unknowable *then*. This re-runs it against what is known *now*, attaches
    the attendee properly, and clears the review.

    Unresolvable entries are left alone: they are the genuine queue, and a
    human still needs to look at them.
    """
    from meeting_notes.graph_client import get_driver, get_known_people
    from meeting_notes.models import Attendee
    from meeting_notes.utils import uuid5_id

    driver = driver or get_driver()
    known = await get_known_people(driver)
    roster = load_roster(roster_path)

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (m:Meeting)-[:NEEDS_REVIEW]->(r:PersonReview)
            WHERE coalesce(r.status, 'pending') = 'pending'
            RETURN r.id AS review_id, r.name AS name, r.role AS role, m.id AS meeting_id
            """
        )
        pending = [dict(x) async for x in result]

    resolved = 0
    for row in pending:
        outcome = resolve(
            Attendee(name=row["name"], role=row["role"] or "attendee"), roster, known_people=known
        )
        if outcome.status != "resolved" or not outcome.email:
            continue
        resolved += 1
        if dry_run:
            continue

        now = datetime.now(UTC).isoformat()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (p:Person {email: $email})
                ON CREATE SET p.created_at = $now, p.tracked = $tracked
                SET p.name = $name, p.id = $person_id, p.updated_at = $now
                WITH p
                MATCH (m:Meeting {id: $meeting_id})
                MERGE (p)-[:ATTENDED {role: $role}]->(m)
                WITH p
                MATCH (r:PersonReview {id: $review_id})
                SET r.status = 'resolved', r.resolved_to = $email, r.updated_at = $now
                """,
                email=outcome.email,
                name=outcome.name,
                person_id=uuid5_id("person", outcome.email),
                tracked=outcome.tracked,
                role=row["role"] or "attendee",
                meeting_id=row["meeting_id"],
                review_id=row["review_id"],
                now=now,
            )

    log.info(
        "person_resolver.reresolved",
        pending=len(pending), resolved=resolved, remaining=len(pending) - resolved,
    )
    return {"pending": len(pending), "resolved": resolved, "remaining": len(pending) - resolved}
