"""Dev agent orchestrator — find candidates, implement one ticket, poll.

**No in-process scheduler.** v5 ran an `AsyncIOScheduler` inside its own
FastAPI service — a direct violation of the rule the rest of v6 already
holds to. `poll_and_process()` here is a plain function; `jobs/dev_agent_poll.py`
is what Cloud Scheduler calls, on its own cadence.

Every external call `process_ticket` and `poll_and_process` make is
injectable, so the ADR-020 fix can be proven at the orchestration level, not
just unit-by-unit in `lifecycle.py` and `db.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.dev_agent import backend, git_ops, guardrails, session_memory
from meeting_notes.dev_agent import lifecycle as lc
from meeting_notes.dev_agent.models import AgentRunResult

log = structlog.get_logger()


# A ticket names its own repo, so one agent can serve many. Accepts
# "repo: owner/name", "repository: owner/name", or a github.com URL.
_REPO_PATTERNS = (
    re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?=[/\s#?)\]]|$)", re.I),
    re.compile(r"\brepo(?:sitory)?\s*[:=]\s*([\w.-]+)/([\w.-]+)", re.I),
)


def repo_dir_for(owner: str, repo: str, settings: Settings) -> str:
    """Checkout directory for one repository.

    Keyed by owner and name: the agent serves whichever repo a ticket names,
    and a single shared directory would have two repos overwriting each
    other's checkout between tickets.
    """
    return f"{settings.dev_agent_repo_dir}/{owner}__{repo}"


def repo_for_ticket(ticket: dict[str, Any], settings: Settings) -> tuple[str, str]:
    """(owner, repo) for this ticket, from its description.

    Falls back to GITHUB_OWNER/GITHUB_REPO so a ticket that says nothing still
    works, but the ticket wins: the agent is meant to serve whichever
    repository the work belongs to, not one configured at deploy time.
    """
    text = ticket.get("description") or ""
    for pattern in _REPO_PATTERNS:
        found = pattern.search(text)
        if found:
            return found.group(1), found.group(2)
    return settings.github_owner, settings.github_repo


def build_prompt(
    ticket: dict[str, Any],
    resume_context: str | None = None,
    repo: tuple[str, str] | None = None,
    base_branch: str = "main",
) -> str:
    """The instructions given to the headless coding agent.

    The agent never merges its own PR — that instruction has zero tolerance
    (CLAUDE.md), and `CLOSED` is written only by a real human merge via
    `/webhook/github`.
    """
    key = ticket["key"]
    summary = ticket.get("summary", "")
    description = ticket.get("description", "")
    resume_block = (
        f"\nResume context from a previous attempt (use it, do not start over):\n{resume_context}\n"
        if resume_context else ""
    )
    branch = f"agent/{key}"
    target = f"{repo[0]}/{repo[1]}" if repo else ""
    repo_line = f"\nTarget repository: {target}\n" if target else ""
    return f"""Read CLAUDE.md and follow all conventions in this repository.
{repo_line}

Implement the following Jira ticket in full:

Ticket: {key}
Summary: {summary}
Description:
{description}
{resume_block}
Instructions:
- Implement the ticket completely.
- Run the test suite and confirm it passes before finishing.
- Do NOT modify .env files, secrets, or anything outside the repository working directory.
- Do NOT merge or attempt to merge any PR yourself.
- After implementation is complete and tests pass, commit and push:
    git add -A
    git commit -m "[{key}] {summary[:60]}"
    git push -u origin {branch}
- Then open a PR:
    gh pr create --title "[{key}] {summary[:80]}" \
        --body "Implements {key}: {summary}. See ticket for full description." \
        --base {base_branch} --head {branch}{f" --repo {target}" if target else ""}
- On the very last line of your output, print the PR URL exactly like this:
    PR_URL: <url>
"""


async def find_sprint_candidates(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Eligible tickets: active sprint, in the configured status, labelled for
    the agent, not skip-labelled.

    A second, independent confidence gate: if the ticket traces to an
    extracted ActionItem below `dev_agent_confidence_threshold`, it is held
    back even though it is labelled — the label alone is not trusted. A
    ticket with no linked ActionItem (human-authored) passes this gate.
    """
    from meeting_notes import graph_client, jira_client

    settings = settings or get_settings()
    candidates = await jira_client.list_active_sprint_tickets(
        settings.jira_project_key,
        ["To Do"],
        ["dev-agent"],
        ["meeting-action-item"],
        settings=settings,
    )
    eligible = []
    for ticket in candidates:
        conf = await graph_client.get_action_confidence(ticket["key"])
        if conf is not None and conf < settings.dev_agent_confidence_threshold:
            log.info(
                "orchestrator.triage.low_confidence_skip",
                key=ticket["key"], confidence=round(conf, 2),
            )
            continue
        eligible.append(ticket)
    return eligible


async def _advance_state(key: str, new_state: str, set_state: Any, get_run: Any) -> None:
    """Validate and persist a lifecycle transition.

    A sequencing bug here must not crash ticket processing — log and still
    persist, matching lifecycle.py's own stated intent that illegal
    transitions are a loud failure, not a silent one, without letting that
    loudness take down a real run over a logging-level bug.
    """
    run = await get_run(key)
    current = run.state if run else None
    if current and current != new_state and not lc.can_transition(current, new_state):
        log.warning(
            "orchestrator.illegal_state_transition",
            ticket_key=key, from_state=current, to_state=new_state,
        )
    await set_state(key, new_state)


@dataclass(frozen=True)
class _Dependencies:
    """Every I/O call `process_ticket` makes, resolved once.

    These exist so the whole flow is testable with no live Jira, git, GitHub
    or Memgraph. They were once eighteen `if x is None:` blocks inline, which
    was most of this function's branching on its own.
    """

    claim_run: Any
    set_state: Any
    get_run: Any
    finish_run: Any
    transition_issue: Any
    add_comment: Any
    get_issue_detail: Any
    ensure_repo_cloned: Any
    create_worktree: Any
    remove_worktree: Any
    run_agent: Any
    find_open_pr: Any
    get_pr_diff: Any
    verify_pr: Any
    write_run_provenance: Any
    load_resume_context: Any
    record_session_memory: Any
    run_gates: Any
    review_pr: Any


def _default_dependencies() -> dict[str, Any]:
    """The real implementations. Imported here rather than at module scope so
    importing the orchestrator does not drag in a database driver."""
    from meeting_notes import db, jira_client
    from meeting_notes.dev_agent import (
        gate_runner,
        gemini_runner,
        github_client,
        reviewer,
        self_verify,
    )
    from meeting_notes.graph_client import write_run_provenance

    return {
        "claim_run": db.claim_dev_agent_run,
        "set_state": db.set_dev_agent_state,
        "get_run": db.get_dev_agent_run,
        "finish_run": db.finish_dev_agent_run,
        "transition_issue": jira_client.transition_issue,
        "add_comment": jira_client.add_comment,
        "get_issue_detail": jira_client.get_issue_detail,
        "ensure_repo_cloned": git_ops.ensure_repo_cloned,
        "create_worktree": git_ops.create_worktree,
        "remove_worktree": git_ops.remove_worktree,
        "run_agent": gemini_runner.run_agent,
        "find_open_pr": github_client.find_open_pr,
        "get_pr_diff": github_client.get_pr_diff,
        "verify_pr": self_verify.verify_pr,
        "write_run_provenance": write_run_provenance,
        "load_resume_context": session_memory.load_resume_context,
        "record_session_memory": session_memory.record,
        "run_gates": gate_runner.run_gates,
        "review_pr": reviewer.review_pr,
    }


def _resolve_dependencies(overrides: dict[str, Any]) -> _Dependencies:
    """Real implementations, with any override substituted.

    An unknown key raises rather than being ignored: a mistyped injection in a
    test would otherwise silently leave the REAL implementation in place, and
    for `review_pr` or `run_agent` that means a live billed model call.
    """
    unknown = set(overrides) - {f.name for f in fields(_Dependencies)}
    if unknown:
        raise TypeError(f"unknown dependency override(s): {sorted(unknown)}")
    resolved = _default_dependencies()
    resolved.update({k: v for k, v in overrides.items() if v is not None})
    return _Dependencies(**resolved)


async def _run_coding_agent(
    key: str, detail: dict[str, Any], settings: Settings, deps: _Dependencies,
    *, work_dir: str, branch_name: str, dev_backend: str, repo: tuple[str, str],
    logger: Any,
) -> AgentRunResult:
    """Take the ticket from PLANNED to a finished agent run."""
    owner, name = repo
    repo_dir = repo_dir_for(owner, name, settings)
    await deps.ensure_repo_cloned(repo_dir, owner, name, settings.github_token)
    base = await deps.create_worktree(repo_dir, work_dir, branch_name)
    resume_context = await deps.load_resume_context(key)
    prompt = build_prompt(
        detail, resume_context=resume_context, repo=repo, base_branch=base or "main"
    )

    await _advance_state(key, lc.IMPLEMENTING, deps.set_state, deps.get_run)
    result: AgentRunResult = await deps.run_agent(
        work_dir, prompt,
        timeout_seconds=settings.dev_agent_timeout_seconds,
        model=backend.model_for_run(dev_backend, settings),
        settings=settings,
    )
    await _advance_state(key, lc.DEBUGGING, deps.set_state, deps.get_run)
    return result


async def _finish_without_pr(
    key: str, detail: dict[str, Any], result: AgentRunResult,
    settings: Settings, deps: _Dependencies, *, logger: Any,
) -> None:
    """No PR exists, so there is nothing to review and nothing to preserve.

    The ticket returns to To Do — the opposite of the has-a-PR paths, which
    never revert it.

    No graph Blocker is written: a Blocker hangs off a Meeting (CLAUDE.md's
    schema, `Meeting-[:RAISES_BLOCKER]->Blocker`) and a dev-agent failure has
    no meeting behind it. The reason is in the Jira comment and in session
    memory, which is what a retry actually reads.
    """
    reason = (result.result_text or "").strip()[:500] or "no error detail captured"
    if result.success:
        logger.error("orchestrator.pr_not_found")
        await deps.finish_run(key, lc.FAILED, error="reported success but no PR was found")
        await deps.add_comment(
            key, "Dev agent reported success but no PR was found. Needs human follow-up.",
            settings=settings,
        )
    else:
        logger.error("orchestrator.agent_failed", error=result.result_text[:200])
        await deps.finish_run(key, lc.FAILED, error=result.result_text[:2000])
        await deps.add_comment(
            key,
            "Dev agent could not complete this ticket automatically. Needs human "
            f"follow-up.\n\nError: {reason}",
            settings=settings,
        )
    await deps.record_session_memory(
        detail, outcome="failed", error=reason, raw_notes=result.result_text or ""
    )
    await _advance_state(key, lc.FAILED, deps.set_state, deps.get_run)
    await deps.transition_issue(key, "To Do", settings=settings)


async def _self_verify(
    ticket: dict[str, Any], pr: dict[str, Any], settings: Settings, deps: _Dependencies,
    *, dev_backend: str, repo: tuple[str, str], logger: Any,
) -> tuple[str, Any]:
    """Fetch the diff and score it against the ticket. Never blocks (ADR-020)."""
    diff = ""
    verdict = None
    try:
        diff = await deps.get_pr_diff(
            repo[0], repo[1], pr["number"], settings.github_token
        )
        verdict = await deps.verify_pr(
            ticket, diff, model=backend.model_for_run(dev_backend, settings),
            threshold=settings.dev_agent_verify_threshold,
        )
    except Exception:  # noqa: BLE001 - self-verify never blocks the review
        logger.warning("orchestrator.self_verify_failed", exc_info=True)
    return diff, verdict


async def _evaluate_pr(
    detail: dict[str, Any], diff: str, work_dir: str, settings: Settings,
    deps: _Dependencies, *, dev_backend: str, logger: Any,
) -> tuple[list[Any], Any]:
    """Both safety-net layers (ADR-020, ADR-022, ADR-024).

    The gates run in the worktree, so this must happen before it is removed.
    The reviewer is skipped when a gate already failed: the run is stopping
    either way, and the call would be spent reaching a settled conclusion.
    """
    try:
        gates = await deps.run_gates(work_dir, diff, detail.get("description", ""), settings)
    except Exception as exc:  # noqa: BLE001 - an unrunnable gate is a human's problem
        logger.error("orchestrator.gates_errored", exc_info=True)
        gates = [
            guardrails.GateResult(
                name="gates_errored", passed=False,
                evidence=f"the gate step itself failed: {exc}",
            )
        ]

    review = None
    if not guardrails.failed_gates(gates):
        try:
            review = await deps.review_pr(
                detail, diff, gates, model=backend.model_for_run(dev_backend, settings)
            )
        except Exception:  # noqa: BLE001 - a model outage must not halt the run
            logger.warning("orchestrator.review_errored", exc_info=True)
    return gates, review


def _rejection_reason(failed: list[Any], review: Any) -> str:
    parts = []
    if failed:
        parts.append("Failed gates:\n" + "\n".join(f"- {g.name}: {g.evidence}" for g in failed))
    if review is not None and review.blocking:
        parts.append("Reviewer findings:\n" + review.summary())
    return "\n\n".join(parts)


@dataclass(frozen=True)
class _Outcome:
    """Everything the terminal steps need about one finished agent run.

    `_ship` and `_escalate_to_human` took twelve and fourteen positional
    arguments respectively — the same clump each time, in an order a caller
    had to get exactly right with no help from the type checker, since most
    of them were `dict[str, Any]`. Grouping them means adding a field is one
    edit rather than four, and a mis-ordered call becomes a name error.
    """

    key: str
    ticket: dict[str, Any]
    detail: dict[str, Any]
    pr: dict[str, Any]
    result: AgentRunResult
    diff: str
    verdict: Any
    verified: bool | None
    branch_name: str
    settings: Settings
    deps: _Dependencies
    logger: Any


async def _record_provenance(ctx: _Outcome, status: str) -> None:
    """Write the AgentRun node the merge webhook later finds by PR url.

    Best-effort: a graph hiccup must not lose the PR link or undo the Jira
    transition that already happened.
    """
    run_after = await ctx.deps.get_run(ctx.key)
    try:
        await ctx.deps.write_run_provenance(
            ticket_key=ctx.key, attempt=run_after.attempt_count if run_after else 1,
            pr_url=ctx.pr["html_url"], pr_number=ctx.pr.get("number"),
            branch=ctx.branch_name, ticket_summary=ctx.ticket.get("summary", ""),
            status=status, verified=ctx.verified,
        )
    except Exception:  # noqa: BLE001 - provenance is not worth failing the run over
        ctx.logger.warning("orchestrator.provenance_write_failed", exc_info=True)


async def _escalate_to_human(ctx: _Outcome, failed: list[Any], review: Any) -> None:
    """A PR that did not pass review. NEEDS_HUMAN is terminal, so the poller
    will not retry it, and the PR is deliberately left open: the work is real,
    it just needs a person."""
    ctx.logger.warning(
        "orchestrator.review_blocked", failed=[g.name for g in failed],
        review_blocking=bool(review and review.blocking), pr_url=ctx.pr["html_url"],
    )
    await ctx.deps.add_comment(
        ctx.key,
        "Dev agent opened a PR but it did NOT pass review, so it has not been marked "
        f"shipped.\n\n{_rejection_reason(failed, review)}\n\n"
        f"PR: {ctx.pr['html_url']}\n\nA human needs to review this before it merges.",
        settings=ctx.settings,
    )
    if not await ctx.deps.transition_issue(ctx.key, "In Review", settings=ctx.settings):
        ctx.logger.warning("orchestrator.review_transition_failed")
    await ctx.deps.finish_run(
        ctx.key, lc.NEEDS_HUMAN, pr_url=ctx.pr["html_url"], pr_number=ctx.pr["number"],
        error=(
            "failed gates: " + ", ".join(g.name for g in failed) if failed
            else "reviewer requested changes"
        ),
    )
    await _advance_state(ctx.key, lc.NEEDS_HUMAN, ctx.deps.set_state, ctx.deps.get_run)
    await _record_provenance(ctx, lc.NEEDS_HUMAN)
    await ctx.deps.record_session_memory(
        ctx.detail, outcome="pr_opened", pr=ctx.pr,
        files_changed=session_memory.files_from_diff(ctx.diff),
        verdict=ctx.verdict, raw_notes=ctx.result.result_text or "",
    )


def _ship_comment(result: AgentRunResult, verdict: Any, pr: dict[str, Any]) -> str:
    base = (
        "Implemented automatically." if result.success
        else "PR opened, but the agent's run ended early (e.g. turn limit) before finishing."
    )
    if verdict and verdict.checked and not verdict.passed:
        flag = (
            " Automated check could NOT confirm the diff addresses the ticket "
            f"(confidence {verdict.confidence:.2f}: {verdict.reason}) — review carefully."
        )
    elif verdict and verdict.passed:
        flag = " Automated check: the diff appears to address the ticket."
    else:
        flag = ""
    return f"{base}{flag} PR: {pr['html_url']}"


async def _ship(ctx: _Outcome) -> None:
    """Gates and reviewer both passed. SHIPPED means the PR is open and the
    ticket is in review — CLOSED happens only when a human actually merges,
    via `/webhook/github`."""
    await ctx.deps.add_comment(
        ctx.key, _ship_comment(ctx.result, ctx.verdict, ctx.pr), settings=ctx.settings
    )
    if not await ctx.deps.transition_issue(ctx.key, "In Review", settings=ctx.settings):
        ctx.logger.warning("orchestrator.review_transition_failed")

    await ctx.deps.finish_run(
        ctx.key, lc.SHIPPED, pr_url=ctx.pr["html_url"], pr_number=ctx.pr["number"]
    )
    await _advance_state(ctx.key, lc.SHIPPED, ctx.deps.set_state, ctx.deps.get_run)
    await _record_provenance(ctx, lc.SHIPPED)
    await ctx.deps.record_session_memory(
        ctx.detail, outcome="pr_opened", pr=ctx.pr,
        files_changed=session_memory.files_from_diff(ctx.diff),
        verdict=ctx.verdict, raw_notes=ctx.result.result_text or "",
    )
    ctx.logger.info(
        "orchestrator.ticket_done", pr_url=ctx.pr["html_url"],
        run_success=ctx.result.success, verified=ctx.verified,
    )


async def process_ticket(
    ticket: dict[str, Any], settings: Settings | None = None, **overrides: Any
) -> None:
    """Implement one ticket end to end.

    Any of the I/O calls named on `_Dependencies` can be passed as a keyword
    argument to substitute a fake; an unknown name raises rather than being
    silently ignored.
    """
    settings = settings or get_settings()
    deps = _resolve_dependencies(overrides)

    key = ticket["key"]
    bound_log = log.bind(ticket_key=key)
    branch_name = f"agent/{key}"
    work_dir = f"{settings.dev_agent_work_root}/{key}"
    dev_backend = backend.select_backend(settings)

    await deps.claim_run(key, lc.TRIAGED, branch_name)

    try:
        if not await deps.transition_issue(key, "In Progress", settings=settings):
            bound_log.warning("orchestrator.in_progress_transition_failed")
        await deps.add_comment(
            key, f"Picked up by dev_agent (backend={dev_backend}).", settings=settings
        )

        detail = await deps.get_issue_detail(key, settings=settings)
        # The ticket names its own repository; the settings are only a fallback.
        repo = repo_for_ticket(detail, settings)
        bound_log = bound_log.bind(repo=f"{repo[0]}/{repo[1]}")
        await _advance_state(key, lc.PLANNED, deps.set_state, deps.get_run)

        result = await _run_coding_agent(
            key, detail, settings, deps, work_dir=work_dir,
            branch_name=branch_name, dev_backend=dev_backend, repo=repo,
            logger=bound_log,
        )

        # The PR check gates the outcome, not result.success: a run can push a
        # branch and open a PR, then still report failure on a later step
        # (e.g. hits the turn limit). Dropping that PR and reverting the ticket
        # to To Do would lose good work.
        pr = await deps.find_open_pr(
            repo[0], repo[1], branch_name, settings.github_token
        )
        if pr is None:
            await _finish_without_pr(key, detail, result, settings, deps, logger=bound_log)
            return

        await _advance_state(key, lc.REVIEWING, deps.set_state, deps.get_run)
        diff, verdict = await _self_verify(
            ticket, pr, settings, deps, dev_backend=dev_backend, repo=repo,
            logger=bound_log,
        )
        verified = verdict.passed if (verdict and verdict.checked) else None

        gates, review = await _evaluate_pr(
            detail, diff, work_dir, settings, deps, dev_backend=dev_backend, logger=bound_log
        )
        failed = guardrails.failed_gates(gates)

        outcome = _Outcome(
            key=key, ticket=ticket, detail=detail, pr=pr, result=result, diff=diff,
            verdict=verdict, verified=verified, branch_name=branch_name,
            settings=settings, deps=deps, logger=bound_log,
        )
        if failed or (review and review.blocking):
            await _escalate_to_human(outcome, failed, review)
            return

        await _ship(outcome)

    except Exception as exc:
        bound_log.error("orchestrator.unexpected_error", exc_info=True)
        error_text = str(exc)
        cleanup: list[Any] = [
            lambda: deps.finish_run(key, lc.FAILED, error=error_text),
            lambda: _advance_state(key, lc.FAILED, deps.set_state, deps.get_run),
            lambda: deps.record_session_memory(ticket, outcome="failed", error=error_text),
            lambda: deps.transition_issue(key, "To Do", settings=settings),
        ]
        for step in cleanup:
            try:
                await step()
            except Exception:  # noqa: BLE001 - best-effort bookkeeping
                pass
    finally:
        await deps.remove_worktree(
            settings.dev_agent_repo_dir, work_dir, branch_name, ignore_errors=True
        )


async def _resume_crashed_run(
    active: Any, settings: Settings, *, should_attempt: Any, get_issue_detail: Any,
    process: Any,
) -> None:
    """Resume a run left active by a crash — if it is still attemptable.

    **The ADR-020 fix, end to end.** A run `get_active_run` returns must ALSO
    pass `should_attempt` before being resumed, rather than relying on the
    terminal-state exclusion the query already applies. That second,
    independent check is what stops a future drift in the terminal set from
    silently reproducing the SHIPPED resume loop — 61 AgentRun nodes for one
    ticket in the live v5 graph.
    """
    if not await should_attempt(active.ticket_key, settings.dev_agent_max_attempts):
        log.info(
            "orchestrator.poll.active_run_not_attemptable",
            ticket_key=active.ticket_key, state=active.state,
        )
        return

    log.info(
        "orchestrator.poll.resuming_crashed_run",
        ticket_key=active.ticket_key, state=active.state,
    )
    try:
        detail = await get_issue_detail(active.ticket_key, settings=settings)
        await process(detail, settings)
    except Exception:  # noqa: BLE001 - a bad resume must not stop new work
        log.error("orchestrator.poll.resume_failed", ticket_key=active.ticket_key, exc_info=True)


async def poll_and_process(
    settings: Settings | None = None,
    *,
    preflight: Any = None,
    get_active_run: Any = None,
    should_attempt: Any = None,
    get_issue_detail: Any = None,
    find_sprint_candidates: Any = find_sprint_candidates,
    process_ticket: Any = process_ticket,
) -> dict[str, Any]:
    """One poll cycle: preflight, resume a crashed run, then take new candidates."""
    settings = settings or get_settings()

    if preflight is None:
        preflight = backend.preflight
    if get_active_run is None:
        from meeting_notes.db import get_active_dev_agent_run as get_active_run
    if should_attempt is None:
        from meeting_notes.db import should_attempt_dev_agent_run as should_attempt
    if get_issue_detail is None:
        from meeting_notes.jira_client import get_issue_detail

    log.info("orchestrator.poll.start")

    dev_backend = backend.select_backend(settings)
    try:
        detail = await preflight(dev_backend, settings)
        log.info("orchestrator.poll.preflight_ok", backend=dev_backend, detail=detail)
    except backend.PreflightError as exc:
        log.error("orchestrator.poll.preflight_failed", error=str(exc))
        return {"attempted": 0, "reason": "preflight_failed"}

    active = await get_active_run()
    if active is not None:
        await _resume_crashed_run(
            active, settings, should_attempt=should_attempt,
            get_issue_detail=get_issue_detail, process=process_ticket,
        )

    tickets = await find_sprint_candidates(settings)
    eligible = [
        ticket for ticket in tickets
        if await should_attempt(ticket["key"], settings.dev_agent_max_attempts)
    ]

    batch = eligible[: settings.dev_agent_poll_batch_size]
    log.info(
        "orchestrator.poll.batch", considered=len(tickets), eligible=len(eligible),
        attempting=len(batch), deferred=len(eligible) - len(batch),
    )

    for ticket in batch:
        await process_ticket(ticket, settings)

    log.info("orchestrator.poll.done", attempted=len(batch))
    return {"attempted": len(batch)}
