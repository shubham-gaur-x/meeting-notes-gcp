"""Review guardrails for the dev agent.

Two layers protect every PR the agent opens:

1. Seven DETERMINISTIC gates (this module). Each is a pure function returning
   a `GateResult`, so it is trivially unit-testable with a planted violation.
2. An independent LLM reviewer — `reviewer.py`, which owns the prompt and
   `ReviewOutcome`. It is given the ticket, the diff and these gate results,
   so it judges what the gates cannot rather than re-deriving them.

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
    """One gate's verdict, with the evidence that produced it.

    `evidence` is not decoration: it is what lands in the Jira comment when a
    run is blocked, and it is the only thing a human has to go on before
    opening the PR. A gate that fails without saying why is barely better
    than one that does not run.
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    passed: bool
    evidence: str


class ReviewFinding(BaseModel):
    """One issue the LLM reviewer raised against a diff.

    Only `severity == "high"` blocks a ship. Lower severities are surfaced in
    the Jira comment and left for the human reviewer, because a model that
    can block on any nitpick will eventually block on all of them.
    """

    model_config = ConfigDict(extra="ignore")

    severity: str  # "low" | "medium" | "high"
    file: str = ""
    issue: str
    suggested_fix: str = ""


# ─── Gate 1/2 — tests + lint/type ──────────────────────────────────────────────

CommandRunner = Callable[[], tuple[int, str]]


def gate_tests_green(runner: CommandRunner) -> GateResult:
    """The project's own test suite, run inside the agent's worktree.

    A runner that cannot execute at all reports a nonzero code, which fails
    the gate. That is deliberate: a gate that cannot run is a failure, never
    a skip (CLAUDE.md).
    """

    code, output = runner()
    return GateResult(
        name="tests_green",
        passed=code == 0,
        evidence=(output or "").strip()[-800:] or ("passed" if code == 0 else "failed"),
    )


def gate_lint_type_clean(lint: CommandRunner, typecheck: CommandRunner) -> GateResult:
    """ruff and mypy together, as one gate.

    Both run even when the first fails, so a diff with both kinds of problem
    reports both at once rather than making the agent discover them over two
    attempts.
    """

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


def gate_diff_budget(  # noqa: D417 - thresholds documented in the body

    changed_files: Sequence[str],
    changed_lines: int,
    max_files: int = 10,
    max_lines: int = 600,
) -> GateResult:
    """Refuse a change far larger than the ticket implies.

    Not a quality judgement — a big diff can be perfectly good. It is a
    scope tripwire: an agent that has misunderstood a ticket tends to rewrite
    far more than one that has understood it, and a human should look before
    that lands.
    """
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
    """Scan ADDED lines only for credential-shaped strings.

    Added lines rather than the whole file: a pre-existing example key in the
    repo is not this diff's fault, and flagging it would train whoever reads
    the result to ignore the gate.
    """

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


# ─── diff parsing ─────────────────────────────────────────────────────────────


class DiffFacts(BaseModel):
    """What the gates need to know about a unified diff.

    One parser, so the diff budget, the secret scan and the session-memory
    record can never disagree about what the PR actually changed —
    `session_memory.files_from_diff` delegates here rather than re-parsing.
    """

    model_config = ConfigDict(extra="ignore")

    changed_files: list[str] = []
    added_lines: list[str] = []
    removed_lines: list[str] = []
    added_dependency_lines: list[str] = []

    @property
    def changed_lines(self) -> int:
        """Additions plus deletions — a pure deletion is still a large change."""
        return len(self.added_lines) + len(self.removed_lines)


def parse_diff(diff: str) -> DiffFacts:
    """Extract changed files and +/- lines from a unified diff.

    `+++`/`---` are file headers, not content, so they are skipped; counting
    them would inflate the budget by two lines per file.
    """
    files: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    dep_lines: list[str] = []
    current = ""

    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            if len(parts) == 2 and parts[1].strip():
                current = parts[1].strip()
                files.append(current)
            continue
        if line.startswith(("+++", "---", "@@", "index ")):
            continue
        if line.startswith("+"):
            body = line[1:]
            added.append(body)
            if any(current.replace("\\", "/").endswith(d) for d in _DEP_FILES):
                dep_lines.append(body)
        elif line.startswith("-"):
            removed.append(line[1:])

    return DiffFacts(
        changed_files=files, added_lines=added,
        removed_lines=removed, added_dependency_lines=dep_lines,
    )


def _is_test_path(path: str) -> bool:
    p = path.replace("\\", "/")
    return p.startswith("tests/") or p.split("/")[-1].startswith("test_")


# A ticket that is itself about tests legitimately touches only tests.
_TEST_TICKET_RE = re.compile(r"\btests?\b|\bcoverage\b", re.IGNORECASE)

_ASSERTION_MARKERS = ("assert", "pytest.raises", "pytest.warns", "self.assert")


def gate_scope_affinity(
    changed_files: Sequence[str],
    file_contents: dict[str, str],
    ticket_description: str = "",
) -> GateResult:
    """Catch the agent making the suite green by editing the suite.

    Two rules, both chosen because a failed gate escalates to NEEDS_HUMAN and
    that is terminal -- a gate that cries wolf permanently stops good runs, so
    precision matters more than recall here.

    1. Tests changed and no implementation file changed at all. An agent that
       has implemented a ticket has, by definition, touched something other
       than a test.
    2. A changed test file that no longer asserts anything. A test with no
       assertion cannot fail, which is the most direct way to turn a red suite
       green without fixing the code.

    Filename affinity -- pairing `tests/test_foo.py` with `foo.py` -- was tried
    first and removed. This repo's tests are `test_phaseNN_<area>.py` and
    deliberately do not map one-to-one onto modules, so the pairing never held
    and needed a keyword exemption list to stay quiet. That list ("sync",
    "api", "pipeline", "data_layer", "pure_core", "llm_seam", "doctor",
    "dev_agent") happened to spell out most of the suite: it exempted 8 of 12
    real test files, leaving a gate that fired only on filenames the repo does
    not contain. Its unit test passed because it invented one.
    """
    violations: list[str] = []
    test_files = [f for f in changed_files if _is_test_path(f)]
    impl_files = [f for f in changed_files if not _is_test_path(f)]

    if test_files and not impl_files and not _TEST_TICKET_RE.search(ticket_description):
        violations.append(
            "tests changed with no implementation change: " + ", ".join(sorted(test_files))
        )

    for path in sorted(test_files):
        content = file_contents.get(path)
        if content is None:
            # Cannot be judged, so it is not waved through: a gate that cannot
            # run is a failure, never a skip (CLAUDE.md).
            violations.append(f"no content supplied to verify assertions in {path}")
        elif not any(marker in content for marker in _ASSERTION_MARKERS):
            violations.append(f"test file asserts nothing after the change: {path}")

    return GateResult(
        name="scope_affinity",
        passed=not violations,
        evidence="clean" if not violations else "; ".join(violations),
    )


# ─── aggregate ────────────────────────────────────────────────────────────────


CommandResult = tuple[int, str]


def evaluate_gates(
    *,
    diff: str,
    ticket_description: str,
    file_contents: dict[str, str],
    tests: CommandResult,
    lint: CommandResult,
    typecheck: CommandResult,
    max_files: int = 10,
    max_lines: int = 600,
) -> list[GateResult]:
    """Run all eight gates over one PR.

    Pure: the caller runs the test/lint/typecheck commands and reads the
    changed files, then hands the results in. That keeps every gate — and this
    aggregation — unit-testable with a planted violation and no subprocess.
    """
    facts = parse_diff(diff)
    return [
        gate_tests_green(lambda: tests),
        gate_lint_type_clean(lambda: lint, lambda: typecheck),
        gate_diff_budget(facts.changed_files, facts.changed_lines, max_files, max_lines),
        gate_protected_paths(facts.changed_files),
        gate_no_new_deps(facts.changed_files, ticket_description, facts.added_dependency_lines),
        gate_secret_scan(facts.added_lines),
        gate_module_boundaries(file_contents),
        gate_scope_affinity(facts.changed_files, file_contents, ticket_description),
    ]


def all_passed(results: Sequence[GateResult]) -> bool:
    """True only when every gate passed. An empty list is vacuously True --
    callers must ensure the gates actually ran."""

    return all(r.passed for r in results)


def failed_gates(results: Sequence[GateResult]) -> list[GateResult]:
    """The failures, in the order they ran, for the blocking Jira comment."""

    return [r for r in results if not r.passed]
