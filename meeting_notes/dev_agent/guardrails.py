"""Review guardrails for the dev agent.

Two layers protect every PR the agent opens:

1. Seven DETERMINISTIC gates (this module). Each is a pure function returning
   a `GateResult`, so it is trivially unit-testable with a planted violation.
2. An independent LLM reviewer (the reviewer prompt + `ReviewVerdict`) that
   gets the ticket, spec, diff, and gate evidence and returns a strict JSON
   verdict.

**The agent never merges its own PR and never bypasses a gate.** Merging
stays human — `CLOSED` is written only by `/webhook/github`'s
`pull_request.merged` handler.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict

# ─── result models ────────────────────────────────────────────────────────────


class GateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    passed: bool
    evidence: str


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    severity: str  # "low" | "medium" | "high"
    file: str = ""
    issue: str
    suggested_fix: str = ""


class ReviewVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdict: str  # "approve" | "request_changes"
    findings: list[ReviewFinding] = []


# ─── Gate 1/2 — tests + lint/type ──────────────────────────────────────────────

CommandRunner = Callable[[], tuple[int, str]]


def gate_tests_green(runner: CommandRunner) -> GateResult:
    code, output = runner()
    return GateResult(
        name="tests_green",
        passed=code == 0,
        evidence=(output or "").strip()[-800:] or ("passed" if code == 0 else "failed"),
    )


def gate_lint_type_clean(lint: CommandRunner, typecheck: CommandRunner) -> GateResult:
    lc, lo = lint()
    tc, to = typecheck()
    passed = lc == 0 and tc == 0
    parts = []
    if lc != 0:
        parts.append(f"ruff: {lo.strip()[-300:]}")
    if tc != 0:
        parts.append(f"mypy: {to.strip()[-300:]}")
    return GateResult(
        name="lint_type_clean",
        passed=passed,
        evidence="clean" if passed else " | ".join(parts),
    )


# ─── Gate 3 — diff budget ───────────────────────────────────────────────────────


def gate_diff_budget(
    changed_files: Sequence[str],
    changed_lines: int,
    max_files: int = 10,
    max_lines: int = 600,
) -> GateResult:
    n_files = len(changed_files)
    ok = n_files <= max_files and changed_lines <= max_lines
    return GateResult(
        name="diff_budget",
        passed=ok,
        evidence=f"{n_files} files (max {max_files}), {changed_lines} lines (max {max_lines})",
    )


# ─── Gate 4 — protected paths ──────────────────────────────────────────────────

_PROTECTED_PATTERNS = [
    re.compile(r"(^|/)\.env"),  # .env, .env.*  (secrets)
    re.compile(r"(^|/)\.github/workflows/"),  # CI config
    re.compile(r"(^|/)(secrets?|credentials?)(/|\.|$)", re.IGNORECASE),
    re.compile(r"\.pem$|\.key$|id_rsa"),  # key material
]


def gate_protected_paths(changed_files: Sequence[str]) -> GateResult:
    """Fail if the diff touches secrets, CI, key material, or escapes the repo.

    `.env.example` is allowed (it holds no secrets); everything else matching
    `.env` is blocked. Paths that escape the repo root (`..` or absolute)
    always fail.
    """
    violations: list[str] = []
    for f in changed_files:
        norm = f.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/"):
            violations.append(f"{f} (outside repo)")
            continue
        if norm.endswith(".env.example"):
            continue
        for pat in _PROTECTED_PATTERNS:
            if pat.search(norm):
                violations.append(f)
                break
    return GateResult(
        name="protected_paths",
        passed=not violations,
        evidence="none" if not violations else "touched: " + ", ".join(sorted(set(violations))),
    )


# ─── Gate 5 — no new dependencies without opt-in ───────────────────────────────

_DEP_FILES = ("requirements.txt", "requirements.in", "poetry.lock", "Pipfile.lock", "pyproject.toml")
_ALLOW_TOKEN = "allow-new-dependency"


def gate_no_new_deps(
    changed_files: Sequence[str],
    ticket_description: str,
    added_dep_lines: Sequence[str] | None = None,
) -> GateResult:
    """Dependency/lock files must be unchanged unless the ticket opts in.

    If opted in, any added requirement line must be version-pinned.
    """
    touched = [f for f in changed_files if any(f.replace("\\", "/").endswith(d) for d in _DEP_FILES)]
    if not touched:
        return GateResult(name="no_new_deps", passed=True, evidence="no dependency files changed")
    if _ALLOW_TOKEN not in (ticket_description or ""):
        return GateResult(
            name="no_new_deps",
            passed=False,
            evidence=f"changed {touched} without '{_ALLOW_TOKEN}' in ticket",
        )
    unpinned = [
        ln.strip()
        for ln in (added_dep_lines or [])
        if ln.strip() and not ln.lstrip().startswith("#") and not re.search(r"(==|>=|~=|@)", ln)
    ]
    if unpinned:
        return GateResult(
            name="no_new_deps", passed=False, evidence=f"allowed but unpinned: {unpinned}"
        )
    return GateResult(name="no_new_deps", passed=True, evidence=f"allowed + pinned ({touched})")


# ─── Gate 6 — secret scan ───────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),  # OpenAI/Anthropic-style
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),  # GitHub PAT
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),  # GitHub classic token
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
]


def gate_secret_scan(added_lines: Sequence[str]) -> GateResult:
    hits: list[str] = []
    for ln in added_lines:
        for pat in _SECRET_PATTERNS:
            if pat.search(ln):
                hits.append(ln.strip()[:80])
                break
    return GateResult(
        name="secret_scan",
        passed=not hits,
        evidence="clean" if not hits else f"{len(hits)} possible secret(s): {hits[:3]}",
    )


# ─── Gate 7 — module boundaries ────────────────────────────────────────────────
# CLAUDE.md's own module-boundary rules, enforced against the agent's diff:
# generic SQL only in db.py, generic Cypher only in graph_client.py, MAGE
# CALLs only in graph_algorithms.py, Jira REST only in jira_client.py.

_BOUNDARY_RULES: list[tuple[re.Pattern[str], str, frozenset[str]]] = [
    (re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+.*\bFROM\b", re.IGNORECASE), "sql", frozenset({"db.py"})),
    (re.compile(r"\bMERGE\s*\(|\bMATCH\s*\("), "cypher", frozenset({"graph_client.py"})),
    (
        re.compile(r"CALL\s+[a-z_]+\.[a-z_]+\s*\("),
        "mage-call",
        frozenset({"graph_algorithms.py"}),
    ),
    (
        re.compile(r"api\.atlassian\.com|/rest/api/\d"),
        "jira-rest",
        frozenset({"jira_client.py"}),
    ),
]


def gate_module_boundaries(file_contents: dict[str, str]) -> GateResult:
    """Flag boundary-marker strings appearing in a file not allowed to hold them.

    String/comment literals are considered for SQL/Cypher/MAGE markers (via a
    light AST walk) so ordinary identifiers never trip the gate.
    """
    violations: list[str] = []
    for path, content in file_contents.items():
        base = path.replace("\\", "/").split("/")[-1]
        haystack = _string_and_comment_text(content)
        for pat, label, allowed in _BOUNDARY_RULES:
            if base in allowed:
                continue
            if pat.search(haystack):
                violations.append(f"{label} in {path} (allowed only in {sorted(allowed)})")
    return GateResult(
        name="module_boundaries",
        passed=not violations,
        evidence="clean" if not violations else "; ".join(violations),
    )


def _string_and_comment_text(source: str) -> str:
    """Concatenate string literals (best-effort AST) so markers in code
    strings are seen. Falls back to raw source if the file does not parse (a
    partial agent edit) — the safe direction, better to over-flag."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    chunks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            chunks.append(node.value)
    return "\n".join(chunks)


# ─── aggregate ────────────────────────────────────────────────────────────────


def all_passed(results: Sequence[GateResult]) -> bool:
    return all(r.passed for r in results)


def failed_gates(results: Sequence[GateResult]) -> list[GateResult]:
    return [r for r in results if not r.passed]
