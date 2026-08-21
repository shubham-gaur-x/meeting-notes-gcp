"""Runs the guardrail gates against a PR, inside the agent's own worktree.

`guardrails.py` is deliberately pure — every gate is a function over data. The
I/O those gates need (running the test/lint/type commands, reading the changed
files) lives here, so the gates stay unit-testable with a planted violation and
no subprocess.

The commands run **in the worktree**, not the checked-out repo, so they see the
agent's changes. That is also why this must be called before the worktree is
removed.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
from pathlib import Path
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.dev_agent import guardrails as gr

log = structlog.get_logger()

# Reading every changed file into memory is fine for a diff that passed the
# budget gate, but a runaway diff should not be able to exhaust the job's
# memory before that gate is even evaluated.
_MAX_FILE_BYTES = 512_000


async def run_command(command: str, cwd: str, timeout_seconds: int = 900) -> tuple[int, str]:
    """Run one shell command in `cwd`, returning (exit_code, combined output).

    A missing binary or a timeout is a gate FAILURE, not an exception: an
    unrunnable test suite is exactly the state a human needs to look at, and
    raising here would skip the remaining gates.
    """
    argv = shlex.split(command)
    if not argv:
        return 127, "empty command"
    # `ruff`, `mypy` and `pytest` are not on PATH in a bare worktree -- they
    # live in the venv or container image running this job. Resolving a
    # leading `python` to the interpreter actually executing us is what makes
    # `python -m ruff ...` work there. Found live: a bare `ruff check .`
    # exited 127, which would have escalated every PR for the wrong reason.
    if argv[0] in ("python", "python3"):
        argv[0] = sys.executable

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, ValueError) as exc:
        return 127, f"could not run {command!r}: {exc}"

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=float(timeout_seconds))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"{command!r} timed out after {timeout_seconds}s"

    return proc.returncode or 0, stdout.decode(errors="replace")


def read_changed_files(work_dir: str, changed_files: list[str]) -> dict[str, str]:
    """Read the changed Python files from the worktree for the boundary gate.

    Only `.py` files: the boundary rules are about Python module ownership, and
    the gate parses each file as Python. A file the agent deleted is simply
    absent — nothing to check.
    """
    contents: dict[str, str] = {}
    root = Path(work_dir).resolve()
    for rel in changed_files:
        if not rel.endswith(".py"):
            continue
        target = (root / rel).resolve()
        # A diff path that escapes the worktree is already a protected_paths
        # violation; never follow it off disk.
        if root not in target.parents:
            continue
        try:
            if target.stat().st_size > _MAX_FILE_BYTES:
                continue
            contents[rel] = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return contents


async def run_gates(
    work_dir: str,
    diff: str,
    ticket_description: str,
    settings: Settings | None = None,
    *,
    command: Any = None,
) -> list[gr.GateResult]:
    """Evaluate all seven gates for the PR built in `work_dir`."""
    settings = settings or get_settings()
    command = command or run_command
    facts = gr.parse_diff(diff)

    # Concurrently: these are three independent read-only commands and the
    # test suite dominates the wall clock.
    tests, lint, typecheck = await asyncio.gather(
        command(settings.dev_agent_test_command, work_dir, settings.dev_agent_gate_timeout_seconds),
        command(settings.dev_agent_lint_command, work_dir, settings.dev_agent_gate_timeout_seconds),
        command(
            settings.dev_agent_typecheck_command, work_dir,
            settings.dev_agent_gate_timeout_seconds,
        ),
    )

    results = gr.evaluate_gates(
        diff=diff,
        ticket_description=ticket_description,
        file_contents=read_changed_files(work_dir, facts.changed_files),
        tests=tests, lint=lint, typecheck=typecheck,
        max_files=settings.dev_agent_max_diff_files,
        max_lines=settings.dev_agent_max_diff_lines,
    )
    log.info(
        "gate_runner.done",
        passed=[r.name for r in results if r.passed],
        failed=[r.name for r in gr.failed_gates(results)],
    )
    return results
