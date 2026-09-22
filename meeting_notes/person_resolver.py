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

_JUNK_NAMES = {
    "unknown",
    "unknown speaker",
    "speaker",
    "speaker 1",
    "speaker 2",
    "speaker 3",
    "speaker 4",
    "speaker 5",
    "unidentified",
    "unidentified speaker",
    "none",
    "nobody",
    "the group",
    "all",
    "everyone",
    "someone",
    "n/a",
    "na",
    "—",
    "-",
}


def is_junk_name(n: str | None) -> bool:
    """Return True if candidate name is an empty placeholder or transcription artifact."""
    if not n or not str(n).strip():
        return True
    norm = normalize_name(n)
    if norm in _JUNK_NAMES:
        return True
    if re.match(r"^speaker\s*\d*$", norm):
        return True
    if re.match(r"^unknown(\s*speaker)?$", norm):
        return True
    if re.match(r"^unidentified(\s*speaker)?$", norm):
        return True
    return False


@dataclass
class ContactProfile:
    """Canonical contact profile linking full names, corporate emails, nicknames, first names, and initials."""
    full_name: str
    email: str
    first_names: list[str] = field(default_factory=list)
    nicknames: list[str] = field(default_factory=list)
    initials: list[str] = field(default_factory=list)
    role: str = ""
    organization: str = "Onix"

    def all_mentions(self) -> list[str]:
        candidates = [self.full_name, self.email] + self.nicknames + self.first_names + self.initials
        seen: set[str] = set()
        res: list[str] = []
        for c in candidates:
            k = normalize_name(c)
            if k and k not in seen:
                seen.add(k)
                res.append(c)
        return res

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.full_name,
            "email": self.email,
            "first_names": self.first_names,
            "nicknames": self.nicknames,
            "initials": self.initials,
            "role": self.role,
            "organization": self.organization,
        }


# Central team contact dictionary
CONTACT_PROFILES: dict[str, ContactProfile] = {
    "leepatrick.mcintire@onixnet.com": ContactProfile(
        full_name="LeePatrick McIntire",
        email="leepatrick.mcintire@onixnet.com",
        first_names=["LeePatrick", "Lee-Patrick", "Lee Patrick", "Lee"],
        nicknames=["LP", "L.P.", "L P"],
        initials=["LP"],
        role="Lead Architect",
    ),
    "coley.woyak@onixnet.com": ContactProfile(
        full_name="Coley Woyak",
        email="coley.woyak@onixnet.com",
        first_names=["Coley"],
        nicknames=["Coley", "Colin", "Coalie", "Colie", "Coaly", "Coley Perry"],
        initials=["CW"],
        role="Client Director",
    ),
    "matteo.vaiente@onixnet.com": ContactProfile(
        full_name="Matteo Vaiente",
        email="matteo.vaiente@onixnet.com",
        first_names=["Matteo"],
        nicknames=["Matteo"],
        initials=["MV"],
        role="Capability Lead",
    ),
    "michael.baylard@onixnet.com": ContactProfile(
        full_name="Michael Baylard",
        email="michael.baylard@onixnet.com",
        first_names=["Michael"],
        nicknames=["Michael", "Baylard"],
        initials=["MB"],
        role="Enterprise Data Architect",
    ),
    "katrisa.brock@onixnet.com": ContactProfile(
        full_name="Katrisa Brock",
        email="katrisa.brock@onixnet.com",
        first_names=["Katrisa"],
        nicknames=["Katrisa"],
        initials=["KB"],
        role="Delivery Operations",
    ),
    "deliveryexcellence@onixnet.com": ContactProfile(
        full_name="Sanjay Pradhan",
        email="deliveryexcellence@onixnet.com",
        first_names=["Sanjay"],
        nicknames=["Sanjay Pradhan", "Delivery Excellence"],
        initials=["SP"],
        role="Delivery Excellence",
    ),
    "mallory.webber@onixnet.com": ContactProfile(
        full_name="Mallory Webber",
        email="mallory.webber@onixnet.com",
        first_names=["Mallory"],
        nicknames=["Mallory"],
        initials=["MW"],
        role="Engagement Manager",
    ),
    "natalie.miller@onixnet.com": ContactProfile(
        full_name="Natalie Miller",
        email="natalie.miller@onixnet.com",
        first_names=["Natalie"],
        nicknames=["Natalie"],
        initials=["NM"],
        role="Cloud Consultant",
    ),
    "gaurav.bharara@onixnet.com": ContactProfile(
        full_name="Gaurav Bharara",
        email="gaurav.bharara@onixnet.com",
        first_names=["Gaurav"],
        nicknames=["Gaurav"],
        initials=["GB"],
        role="Cloud Architect",
    ),
}


def resolve_to_full_name(mention: str | None) -> str:
    """Resolve any first name, nickname, initials, or email to the canonical contact full name."""
    if not mention:
        return ""
    raw = str(mention).strip()
    norm = normalize_name(raw)
    if not norm or is_junk_name(norm):
        return raw

    # 1. Match against contact profiles
    for profile in CONTACT_PROFILES.values():
        if norm == normalize_name(profile.full_name) or norm == normalize_name(profile.email):
            return profile.full_name
        for n in profile.nicknames:
            if norm == normalize_name(n):
                return profile.full_name
        for f in profile.first_names:
            if norm == normalize_name(f):
                return profile.full_name
        for init in profile.initials:
            if norm == normalize_name(init):
                return profile.full_name

    # 2. Check alias map
    alias_match = KNOWN_PERSON_ALIASES.get(norm)
    if alias_match:
        return alias_match[0]

    return raw


def expand_contact_mentions(names: list[str]) -> list[str]:
    """Expand a list of names/mentions to include full names, emails, and all known aliases."""
    expanded: set[str] = set()
    for name in names:
        if not name:
            continue
        expanded.add(name)
        norm = normalize_name(name)
        for profile in CONTACT_PROFILES.values():
            profile_mentions = [normalize_name(m) for m in profile.all_mentions()]
            if norm in profile_mentions:
                for m in profile.all_mentions():
                    expanded.add(m)
    return list(expanded)


def get_contact_directory_list() -> list[dict[str, Any]]:
    """Return all known contact profiles as serializable dictionaries."""
    return [p.to_dict() for p in CONTACT_PROFILES.values()]


# Canonical person resolution for team nicknames, initials, and transcript variants
KNOWN_PERSON_ALIASES: dict[str, tuple[str, str]] = {
    # LeePatrick McIntire (LP)
    "lp": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "l.p.": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "l p": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "leepatrick": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "lee patrick": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "lee-patrick": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "leepatrick mcintire": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "lee patrick mcintire": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    "lee-patrick mcintire": ("LeePatrick McIntire", "leepatrick.mcintire@onixnet.com"),
    # Coley Woyak / Coley Perry
    "coley": ("Coley Woyak", "coley.woyak@onixnet.com"),
    "colin": ("Coley Woyak", "coley.woyak@onixnet.com"),
    "coalie": ("Coley Woyak", "coley.woyak@onixnet.com"),
    "colie": ("Coley Woyak", "coley.woyak@onixnet.com"),
    "coaly": ("Coley Woyak", "coley.woyak@onixnet.com"),
    "coley woyak": ("Coley Woyak", "coley.woyak@onixnet.com"),
    "coley perry": ("Coley Woyak", "coley.woyak@onixnet.com"),
    # Matteo Vaiente
    "matteo": ("Matteo Vaiente", "matteo.vaiente@onixnet.com"),
    "matteo vaiente": ("Matteo Vaiente", "matteo.vaiente@onixnet.com"),
}

EMAIL_ALIASES: dict[str, str] = {
    "coley.perry@onixnet.com": "coley.woyak@onixnet.com",
}

# Retained backward compatibility mapping
COMMON_NAME_ALIASES: dict[str, str] = {
    "colin": "Coley",
    "coalie": "Coley",
    "colie": "Coley",
    "coaly": "Coley",
}


def normalize_email(email: str | None) -> str:
    """Lowercase, trim, and drop any ``+tag`` from the local part."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return e
    local, _, domain = e.partition("@")
    local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def normalize_name(n: str | None) -> str:
    """Lowercase, trim, and collapse internal whitespace.

    Public because `graph_client` resolves action-item owners against a
    meeting's attendee roster and has to normalise names the same way this
    module does. Two spellings of "normalise" is how the two ends of a match
    drift apart, so there is one implementation and callers import it.
    """
    return re.sub(r"\s+", " ", (n or "").strip().lower())


# Retained: this module refers to it by the private name throughout.
_norm_name = normalize_name


def _name_sim(a: str, b: str) -> float:
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _initials_matches(
    mention: str, known_people: list[dict[str, Any]]
) -> list[tuple[str | None, str | None, bool]]:
    """Known people whose initials match a 2-3 letter mention (e.g. 'LP')."""
    m = _norm_name(mention).replace(".", "").replace(" ", "")
    if len(m) < 2 or len(m) > 3 or not m.isalpha():
        return []

    out: list[tuple[str | None, str | None, bool]] = []
    for person in known_people:
        p_name = _norm_name(person.get("name", ""))
        parts = p_name.split()
        if len(parts) >= 2:
            initials = "".join(p[0] for p in parts if p)
            if initials == m:
                out.append((person.get("email"), person.get("name"), bool(person.get("tracked", False))))
            elif parts[0].startswith("lee") and "patrick" in parts[0] and m == "lp":
                out.append((person.get("email"), person.get("name"), bool(person.get("tracked", False))))
    return out


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
    if len(first) < 3:  # Initials handled separately in _initials_matches
        return []

    out: list[tuple[str | None, str | None, bool]] = []
    for person in known_people:
        parts = _norm_name(person.get("name")).split()
        if parts and parts[0] == first:
            out.append((person.get("email"), person.get("name"), bool(person.get("tracked", False))))
    return out


@dataclass
class RosterEntry:
    """One known person from the operator-supplied roster file.

    The roster is the only place `tracked` can be turned on: opting someone
    into per-person analytics is a deliberate act by whoever maintains that
    file, never something extraction infers.
    """

    name: str
    email: str
    aliases: list[str] = field(default_factory=list)
    tracked: bool = False


@dataclass
class Resolution:
    """The outcome of matching one attendee to a person.

    `status` is "resolved" or "review". `reason` records HOW -- roster-email,
    person-name, no-email-no-match -- which is what makes the review queue
    diagnosable rather than a pile of names.
    """

    name: str
    role: str = "attendee"
    email: str | None = None          # canonical email if resolved, else None
    status: str = "resolved"          # "resolved" | "review"
    tracked: bool = False
    reason: str = ""


class Roster:
    """Indexed lookup over the roster file, by email and by normalised name."""

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

    # 1. Filter out junk placeholder speaker names immediately
    if is_junk_name(name):
        return Resolution(name, role, None, "dropped", False, "junk-name")

    # 2. Check canonical known person aliases (LP, Coley, Colin, Matteo, etc.)
    norm_n = _norm_name(name)
    alias_match = KNOWN_PERSON_ALIASES.get(norm_n)
    if alias_match and (not email or "@" not in email):
        c_name, c_email = alias_match
        return Resolution(c_name, role, c_email, "resolved", False, "known-alias")

    # Retained backward compatibility mapping
    alias = COMMON_NAME_ALIASES.get(norm_n)
    if alias:
        name = alias

    # Tier 1 — deterministic (email present)
    if email and "@" in email:
        ne = normalize_email(email)
        ne = EMAIL_ALIASES.get(ne, ne)
        entry = roster.match_email(ne)
        if entry:
            return Resolution(
                entry.name or name, role, entry.email, "resolved", entry.tracked, "roster-email"
            )
        # Check if known_people has this email to retain full canonical display name
        for kp in known_people:
            if normalize_email(kp.get("email")) == ne and kp.get("name"):
                return Resolution(kp["name"], role, ne, "resolved", bool(kp.get("tracked", False)), "known-email")
        # Real email, not in roster → canonical is the normalized email (a new person).
        return Resolution(name, role, ne, "resolved", False, "email-normalized")

    # Tier 2 — probabilistic (no email): fuzzy name against roster, then known Person nodes.
    entry, score = roster.match_name(name, threshold)
    if entry:
        return Resolution(
            entry.name, role, entry.email, "resolved", entry.tracked, f"roster-name:{score:.2f}"
        )

    best: tuple[str | None, str | None, float, bool] = (None, None, 0.0, False)
    for p in known_people:
        s = _name_sim(name, p.get("name", ""))
        if s > best[2]:
            best = (p.get("email"), p.get("name"), s, bool(p.get("tracked", False)))
    if best[0] and best[2] >= threshold:
        return Resolution(
            best[1] or name, role, best[0], "resolved", best[3], f"person-name:{best[2]:.2f}"
        )

    # Initials match (e.g. "LP" matching "LeePatrick McIntire")
    initials_candidates = _initials_matches(name, known_people)
    if len(initials_candidates) == 1:
        email, full, tracked = initials_candidates[0]
        return Resolution(full or name, role, email, "resolved", tracked, "person-initials")

    # Unambiguous first-name match.
    given = _given_name_matches(name, known_people)
    if len(given) == 1:
        email, full, tracked = given[0]
        return Resolution(full or name, role, email, "resolved", tracked, "person-given-name")
    if len(given) > 1:
        return Resolution(name, role, None, "review", False, "ambiguous-given-name")

    # Give up → review. Never silently drop real human names.
    return Resolution(name, role, None, "review", False, "no-email-no-match" if not email else "unresolved")


def resolve_attendees(
    attendees: list[Any],
    roster: Roster,
    known_people: list[dict[str, Any]] | None = None,
) -> tuple[list[Resolution], list[Resolution]]:
    """Return (resolved, reviews) for a list of attendees.

    Junk speakers (e.g. 'Unknown speaker') are dropped from both queues.
    """
    resolved: list[Resolution] = []
    reviews: list[Resolution] = []
    for a in attendees:
        r = resolve(a, roster, known_people=known_people)
        if r.status == "resolved":
            resolved.append(r)
        elif r.status == "review":
            reviews.append(r)
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


async def reresolve_action_owners(
    driver: Any = None,
    *,
    roster_path: str | None = None,
    known_people: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Attach ASSIGNED_TO for action items whose owner is resolvable now.

    Same order-dependence `reresolve_reviews` exists for, on a different edge.
    `upsert_meeting_graph` reads the known-people set once, before the
    transaction, so an action item extracted before anyone was in the graph
    can never match. Measured on a full rebuild: meetings written at 23:13:37,
    the first Person node created at 23:15:15 — everything in those 98 seconds
    lost its owner edge permanently, while the resolver matched the same names
    at confidence 1.00 when asked afterwards.

    The ActionItem keeps its raw `owner` string either way; this only adds the
    edge. An owner that is not a person — "The group", "Unassigned" — resolves
    to nothing and is left alone.
    """
    from meeting_notes.graph_client import get_driver, get_known_people
    from meeting_notes.models import Attendee
    from meeting_notes.utils import uuid5_id

    driver = driver or get_driver()
    known = known_people if known_people is not None else await get_known_people(driver)
    roster = load_roster(roster_path)

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:ActionItem)
            WHERE a.owner IS NOT NULL AND NOT (a)-[:ASSIGNED_TO]->(:Person)
            RETURN a.id AS action_id, a.owner AS owner
            """
        )
        pending = [dict(x) async for x in result]

    resolved = 0
    for row in pending:
        owner = row["owner"] or ""
        outcome = resolve(
            Attendee(name=owner, email=owner if "@" in owner else None),
            roster,
            known_people=known,
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
                MATCH (a:ActionItem {id: $action_id})
                MERGE (a)-[:ASSIGNED_TO]->(p)
                """,
                email=outcome.email,
                name=outcome.name,
                person_id=uuid5_id("person", outcome.email),
                tracked=outcome.tracked,
                action_id=row["action_id"],
                now=now,
            )

    log.info(
        "person_resolver.action_owners_reresolved",
        pending=len(pending), resolved=resolved, remaining=len(pending) - resolved,
    )
    return {"pending": len(pending), "resolved": resolved, "remaining": len(pending) - resolved}
