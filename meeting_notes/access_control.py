"""Phase 33 (core) — principal → scope access policy.

Design stance: hierarchy lives IN the graph (Person→Team→Org, Project→Team). A *subgraph*
is the traversal closure of a scope anchor, made cheap by scope-stamping nodes at write
time. ACCESS is enforced at the retrieval boundary (this policy + a single Cypher scope
filter in ``memgraph_client``) because Memgraph Community lacks label-based ACLs — LBAC is
the documented Enterprise production path.

This module is the PURE policy core: parse a scope, resolve what a principal may see, and
decide when a query must return aggregates only. It contains NO Cypher — ``memgraph_client``
consumes ``scope_predicate`` to inject the filter. Kept side-effect-free so it is fully
unit-testable without a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Role levels, least → most privileged.
MEMBER = "member"   # own team only
LEAD = "lead"       # own team + org-level rollups (aggregates), not other teams' detail
ADMIN = "admin"     # everything, including cross-team detail
ROLE_ORDER = {MEMBER: 0, LEAD: 1, ADMIN: 2}


class AccessDenied(RuntimeError):
    """Raised when a principal requests a scope its policy does not allow."""


@dataclass(frozen=True)
class Scope:
    kind: str            # "all" | "org" | "team" | "project"
    value: str | None = None     # team name / project key; None for all/org

    def token(self) -> str:
        return self.kind if self.value is None else f"{self.kind}:{self.value}"


def parse_scope(raw: str) -> Scope:
    """Parse ``all`` | ``org`` | ``team:<name>`` | ``project:<key>`` into a Scope."""
    raw = (raw or "").strip()
    if raw in ("all", "org"):
        return Scope(raw)
    if ":" in raw:
        kind, value = raw.split(":", 1)
        kind = kind.strip().lower()
        value = value.strip()
        if kind in ("team", "project") and value:
            return Scope(kind, value)
    raise ValueError(f"Unparseable scope {raw!r}; expected all|org|team:<name>|project:<key>")


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    team: str | None = None
    allowed_scopes: tuple[str, ...] = ()  # explicit scope tokens; empty => derived from role/team


# Default in-code policy; overridable via ACCESS_POLICY_FILE (YAML). Keeps the demo
# self-contained while documenting the production shape.
_DEFAULT_POLICY: dict[str, dict[str, Any]] = {
    "claude-desktop": {"role": ADMIN, "team": None},
    "action-agent": {"role": LEAD, "team": "QA AI"},
    "dev-agent": {"role": MEMBER, "team": "QA AI"},
}


def load_policy(path: str | None = None) -> dict[str, Principal]:
    """Load the principal policy map (YAML file at `path`, else the in-code default).

    v5 fell back to reading ACCESS_POLICY_FILE from the environment here.
    Nothing outside config.py may do that (CLAUDE.md); callers pass
    `get_settings().access_policy_file`.
    """
    raw: dict[str, dict[str, Any]]
    if path and Path(path).exists():
        import yaml  # lazy: only needed when a policy file is configured (no new hard dep)

        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    else:
        raw = _DEFAULT_POLICY
    policy: dict[str, Principal] = {}
    for name, spec in raw.items():
        policy[name] = Principal(
            name=name,
            role=spec.get("role", MEMBER),
            team=spec.get("team"),
            allowed_scopes=tuple(spec.get("allowed_scopes", []) or []),
        )
    return policy


def resolve_principal(name: str, policy: dict[str, Principal] | None = None) -> Principal:
    policy = policy if policy is not None else load_policy()
    if name not in policy:
        raise AccessDenied(f"unknown principal {name!r}")
    return policy[name]


def _scope_allowed(principal: Principal, scope: Scope) -> bool:
    # Explicit allow-list wins if present.
    if principal.allowed_scopes and scope.token() in principal.allowed_scopes:
        return True
    if principal.role == ADMIN:
        return True                       # admin sees everything
    if scope.kind == "all":
        return principal.role == ADMIN
    if scope.kind == "org":
        return principal.role in (LEAD, ADMIN)   # lead gets org-level (aggregates)
    if scope.kind == "team":
        return scope.value == principal.team     # own team only for member/lead
    if scope.kind == "project":
        # Project detail requires admin here; members/leads reach projects via their team.
        return principal.role == ADMIN
    return False


def authorize(
    name: str, requested_scope: str, policy: dict[str, Principal] | None = None
) -> Scope:
    """Resolve principal + scope, raising AccessDenied if the scope is not permitted."""
    principal = resolve_principal(name, policy)
    scope = parse_scope(requested_scope)
    if not _scope_allowed(principal, scope):
        raise AccessDenied(
            f"principal {name!r} (role={principal.role}) may not access scope {scope.token()!r}"
        )
    return scope


def aggregates_only(
    name: str, requested_scope: str, policy: dict[str, Principal] | None = None
) -> bool:
    """Org-level queries return AGGREGATES (counts/trends) unless the principal is admin.

    This is the concrete answer to 'org level details and access': a lead can ask
    org-wide questions but gets rollups, not other teams' row-level detail.
    """
    principal = resolve_principal(name, policy)
    scope = parse_scope(requested_scope)
    if scope.kind in ("org", "all") and principal.role != ADMIN:
        return True
    return False


def scope_predicate(scope: Scope) -> dict[str, str | None]:
    """Property filter that ``memgraph_client`` injects into generated Cypher.

    Returns ``{}`` for all/org (no per-node property filter — org rollups filter later),
    or a single-property filter for team/project. Denormalized scope stamping (scope_team /
    scope_org on every node) makes this a cheap property match, not a traversal.
    """
    if scope.kind == "team":
        return {"scope_team": scope.value}
    if scope.kind == "project":
        return {"scope_project": scope.value}
    return {}


def visible_scopes(name: str, policy: dict[str, Principal] | None = None) -> list[str]:
    """Enumerate the scope tokens a principal may access (for menus / the demo)."""
    principal = resolve_principal(name, policy)
    if principal.role == ADMIN:
        return ["all", "org"]
    out: list[str] = list(principal.allowed_scopes)
    if principal.role == LEAD:
        out.append("org")
    if principal.team:
        out.append(f"team:{principal.team}")
    return sorted(set(out))
