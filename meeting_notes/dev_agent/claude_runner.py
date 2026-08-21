"""Headless Claude Code runner for the dev agent.

Spawns the `claude` CLI as a subprocess with the environment `backend.py`
resolves for the selected coding backend. This is genuinely a different kind
of call from everything else in `meeting_notes` — a subprocess with tool
access, not a structured completion — which is why it lives here rather than
behind `llm_client.py`.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.dev_agent.backend import resolve_backend_env, select_backend
from meeting_notes.dev_agent.models import ClaudeRunResult

log = structlog.get_logger()


async def run_oneshot(
    prompt: str,
    timeout_seconds: int,
    model: str | None = None,
    settings: Settings | None = None,
) -> str | None:
    """Run a single-turn, no-tools ``claude -p`` through the selected backend.

    Returns the model's answer text or None on failure. For cheap scoring
    passes (self-verify) — NOT for code work: no tools, no work_dir,
    ``--max-turns 1``.
    """
    settings = settings or get_settings()
    backend = select_backend(settings)
    env = os.environ.copy()
    env.update(resolve_backend_env(backend, settings))

    cmd = ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "1"]
    if model:
        cmd += ["--model", model]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=float(timeout_seconds))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        log.warning("claude_runner.oneshot_timeout", timeout_seconds=timeout_seconds)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("claude_runner.oneshot_error", error=str(exc))
        return None

    out = stdout_bytes.decode(errors="replace")
    try:
        result: str | None = json.loads(out).get("result", "") or None
        return result
    except (json.JSONDecodeError, ValueError):
        return out or None


async def run_claude_code(
    work_dir: str,
    prompt: str,
    timeout_seconds: int,
    max_turns: int,
    model: str | None = None,
    settings: Settings | None = None,
) -> ClaudeRunResult:
    """Run Claude Code to completion on a real coding task, in `work_dir`.

    Grants Read/Glob/Grep/Edit/Write/Bash with `acceptEdits`, so the agent can
    actually implement the ticket, run tests, and (via Bash) commit/push/open
    a PR. The prompt is the only thing telling it not to merge — see
    `orchestrator.build_prompt`.
    """
    settings = settings or get_settings()
    backend = select_backend(settings)
    env = os.environ.copy()
    env.update(resolve_backend_env(backend, settings))

    cmd = [
        "claude", "-p", prompt,
        "--allowedTools", "Read,Glob,Grep,Edit,Write,Bash",
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
        "--max-turns", str(max_turns),
    ]
    if model:
        cmd += ["--model", model]

    log.info("claude_runner.start", work_dir=work_dir, model=model, max_turns=max_turns)
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
            log.error("claude_runner.timeout", work_dir=work_dir, timeout_seconds=timeout_seconds)
            return ClaudeRunResult(
                success=False, returncode=-1, timed_out=True,
                result_text="timed out", duration_ms=duration_ms,
            )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        log.error("claude_runner.subprocess_error", error=str(exc))
        return ClaudeRunResult(
            success=False, returncode=-1, result_text=str(exc), duration_ms=duration_ms
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    stdout_str = stdout_bytes.decode(errors="replace")
    stderr_str = stderr_bytes.decode(errors="replace")

    if proc.returncode != 0:
        # claude's own JSON error result (the actually useful message) is
        # written to stdout even on nonzero exit — stderr is frequently
        # empty. Prefer the parsed "result" field, fall back to raw stdout,
        # then stderr, so a real message always surfaces.
        error_detail = stderr_str.strip()
        if not error_detail and stdout_str.strip():
            try:
                parsed = json.loads(stdout_str)
                error_detail = parsed.get("result") or stdout_str
            except (json.JSONDecodeError, ValueError):
                error_detail = stdout_str

        log.error(
            "claude_runner.nonzero_exit", returncode=proc.returncode,
            error_detail=error_detail[-2000:],
        )
        return ClaudeRunResult(
            success=False, returncode=proc.returncode or 0,
            result_text=error_detail[-2000:], duration_ms=duration_ms,
        )

    try:
        data = json.loads(stdout_str)
        result_text = data.get("result", "")
        num_turns = data.get("num_turns")
        is_error = bool(data.get("is_error", False))
    except (json.JSONDecodeError, ValueError):
        log.warning("claude_runner.json_parse_failed", stdout_snippet=stdout_str[-500:])
        return ClaudeRunResult(
            success=True, returncode=0, result_text=stdout_str[-2000:], duration_ms=duration_ms
        )

    log.info("claude_runner.finish", duration_ms=duration_ms, num_turns=num_turns, is_error=is_error)
    return ClaudeRunResult(
        success=not is_error, returncode=proc.returncode, result_text=result_text,
        num_turns=num_turns, duration_ms=duration_ms,
    )
