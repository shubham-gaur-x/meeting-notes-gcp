"""Shared test guards.

CLAUDE.md: "Tests are mocked — the suite must run with no live GCP, no
database, no LLM. A test requiring live credentials is a broken test."

That rule held by convention until the LLM reviewer was wired into
`process_ticket`. A pre-existing test that did not inject `review_pr` then
reached the real `gemini` CLI and made a live, billed model call — and still
looked like an ordinary assertion failure. Convention is not enough once a
default is a network call, so the rule is enforced here instead.
"""

from __future__ import annotations

import pytest


class LiveModelCallAttempted(BaseException):
    """Raised when a test reaches the real model CLI.

    Deliberately a `BaseException`, not an `Exception`. The orchestrator wraps
    its reviewer and gate calls in broad `except Exception` handlers so a model
    outage cannot halt a run — which also swallows an ordinary assertion and
    lets the test pass while having made a live, billed call. Only something
    outside that hierarchy actually escapes, the same way `KeyboardInterrupt`
    does.
    """


@pytest.fixture(autouse=True)
def _no_live_model_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test reaches a real coding-model subprocess.

    Every dev_agent path that talks to a model takes an injectable runner, so
    a test hitting this has forgotten to inject one. Failing here names the
    cause; without it the test instead fails much later on whatever the live
    model happened to answer, or quietly passes while spending money.
    """

    import asyncio

    real_spawn = asyncio.create_subprocess_exec

    async def _guarded(program: object = "", *args: object, **kwargs: object) -> object:
        # Only the model CLI is off limits. The gate runner legitimately spawns
        # local processes (pytest, ruff, mypy) and git_ops spawns git; blocking
        # those would forbid the very thing several tests exist to prove.
        if str(program).rsplit("/", 1)[-1] == "gemini":
            raise LiveModelCallAttempted(
                "a test tried to spawn the real coding-model CLI. Inject a fake "
                "run_oneshot / run_agent / review_pr / run_gates instead "
                "(CLAUDE.md: the suite runs with no live LLM)."
            )
        return await real_spawn(program, *args, **kwargs)  # type: ignore[arg-type]

    # Patched on the module the runner resolves at call time. Its own unit
    # tests replace this same attribute and so override the guard.
    from meeting_notes.dev_agent import gemini_runner

    monkeypatch.setattr(gemini_runner.asyncio, "create_subprocess_exec", _guarded)
