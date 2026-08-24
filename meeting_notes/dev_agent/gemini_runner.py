"""Headless Gemini CLI runner for the dev agent.

Spawns the `gemini` CLI as a subprocess with the environment `backend.py`
resolves. This is genuinely a different kind of call from everything else in
`meeting_notes` — a subprocess with tool access, not a structured completion —
which is why it lives here rather than behind `llm_client.py` (CLAUDE.md).

Flag mapping, verified live against gemini-cli 0.42.0:

    -p/--prompt              headless (non-interactive) mode
    -o json                  machine-readable result
    --approval-mode yolo     auto-approve all tools. auto_edit approves EDIT
                             tools only, so the agent could edit files but not
                             commit, push, or open a PR -- it finished looking
                             successful with nothing shipped.
    --skip-trust             the worktree is created fresh per ticket, so the
                             CLI's folder-trust prompt has nothing to protect
                             and would otherwise silently downgrade the
                             approval mode back to "default" and hang.
    -m/--model               pinned model id

The CLI has no `--max-turns`; a run is bounded by `timeout_seconds` instead.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.dev_agent.backend import resolve_backend_env, select_backend
from meeting_notes.dev_agent.models import AgentRunResult

log = structlog.get_logger()


def _parse_result(stdout: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _turns_from_stats(stats: Any) -> int | None:
    """Total API requests across models — the CLI's nearest thing to a turn count."""
    if not isinstance(stats, dict):
        return None
    models = stats.get("models")
    if not isinstance(models, dict):
        return None
    total = 0
    for entry in models.values():
        if isinstance(entry, dict):
            api = entry.get("api")
            if isinstance(api, dict):
                total += api.get("totalRequests") or 0
    return total or None


async def run_oneshot(
    prompt: str,
    timeout_seconds: int,
    model: str | None = None,
    settings: Settings | None = None,
) -> str | None:
    """Run a single-turn, read-only ``gemini -p`` through the selected backend.

    Returns the model's answer text or None on failure. For cheap scoring
    passes (self-verify) — NOT for code work: ``--approval-mode plan`` keeps
    it read-only and no work_dir is set.
    """
    settings = settings or get_settings()
    backend = select_backend(settings)
    env = os.environ.copy()
    env.update(resolve_backend_env(backend, settings))

    cmd = ["gemini", "-p", prompt, "-o", "json", "--skip-trust", "--approval-mode", "plan"]
    if model:
        cmd += ["-m", model]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=float(timeout_seconds))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        log.warning("gemini_runner.oneshot_timeout", timeout_seconds=timeout_seconds)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("gemini_runner.oneshot_error", error=str(exc))
        return None

    out = stdout_bytes.decode(errors="replace")
    parsed = _parse_result(out)
    if parsed is None:
        return out or None
    response: str | None = parsed.get("response") or None
    return response


async def run_agent(
    work_dir: str,
    prompt: str,
    timeout_seconds: int,
    model: str | None = None,
    settings: Settings | None = None,
) -> AgentRunResult:
    """Run the coding agent to completion on a real task, in `work_dir`.

    ``--approval-mode yolo`` is what lets it implement the ticket, run tests,
    and (via shell) commit, push and open a PR. The prompt is the only thing
    telling it not to merge — see `orchestrator.build_prompt`. Isolation comes
    from the per-ticket worktree, and nothing ships until the gates and the
    reviewer agree.

    There is no turn cap: the CLI exposes none. `timeout_seconds` and the
    guardrail gates are the bounds.
    """
    settings = settings or get_settings()
    backend = select_backend(settings)
    env = os.environ.copy()
    env.update(resolve_backend_env(backend, settings))

    cmd = [
        "gemini", "-p", prompt,
        "-o", "json",
        "--skip-trust",
        # `auto_edit` approves EDIT tools only. The agent is instructed to
        # commit, push and open a PR -- all shell -- and headless there is
        # nobody to approve those, so it edited files and silently stopped.
        # `yolo` is the only mode that lets it finish the job; the isolation
        # is the worktree, and the gates and reviewer are what decide whether
        # any of it ships.
        "--approval-mode", "yolo",
    ]
    if model:
        cmd += ["-m", model]

    log.info("gemini_runner.start", work_dir=work_dir, model=model, backend=backend)
    start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=work_dir, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout_seconds)
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            duration_ms = int((time.monotonic() - start) * 1000)
            log.error("gemini_runner.timeout", work_dir=work_dir, timeout_seconds=timeout_seconds)
            return AgentRunResult(
                success=False, returncode=-1, timed_out=True,
                result_text="timed out", duration_ms=duration_ms,
            )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        log.error("gemini_runner.subprocess_error", error=str(exc))
        return AgentRunResult(
            success=False, returncode=-1, result_text=str(exc), duration_ms=duration_ms
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    return _result_from_output(
        proc.returncode or 0,
        stdout_bytes.decode(errors="replace"),
        stderr_bytes.decode(errors="replace"),
        duration_ms,
    )


def _result_from_output(
    returncode: int, stdout_str: str, stderr_str: str, duration_ms: int
) -> AgentRunResult:
    """Interpret one finished CLI run. Pure, so the awkward cases are testable.

    Three of them, all seen live:

    * nonzero exit — the useful message is the CLI's own JSON on *stdout*,
      not stderr, which is usually just warnings;
    * unparseable stdout — treated as success, because the run may well have
      done the work and the PR check is what actually decides;
    * a stream-level error alongside completed work — the CLI wrote the file
      correctly, then emitted `{"error": {"type": "INVALID_STREAM"}}` on the
      way out. `success` records what the CLI claimed; the orchestrator gates
      on whether a PR exists, never on this flag alone (ADR-020).
    """
    parsed = _parse_result(stdout_str)

    if returncode != 0:
        error_detail = ""
        if parsed is not None:
            error = parsed.get("error")
            if isinstance(error, dict):
                error_detail = error.get("message") or ""
        if not error_detail:
            error_detail = stderr_str.strip() or stdout_str
        log.error(
            "gemini_runner.nonzero_exit", returncode=returncode,
            error_detail=error_detail[-2000:],
        )
        return AgentRunResult(
            success=False, returncode=returncode,
            result_text=error_detail[-2000:], duration_ms=duration_ms,
        )

    if parsed is None:
        log.warning("gemini_runner.json_parse_failed", stdout_snippet=stdout_str[-500:])
        return AgentRunResult(
            success=True, returncode=0, result_text=stdout_str[-2000:], duration_ms=duration_ms
        )

    error = parsed.get("error")
    error = error if isinstance(error, dict) and error else None
    result_text = parsed.get("response") or ""
    if error is not None and not result_text:
        result_text = error.get("message") or ""

    turns = _turns_from_stats(parsed.get("stats"))
    log.info(
        "gemini_runner.finish", duration_ms=duration_ms,
        num_turns=turns, is_error=error is not None,
    )
    return AgentRunResult(
        success=error is None, returncode=returncode, result_text=result_text,
        num_turns=turns, duration_ms=duration_ms,
    )
