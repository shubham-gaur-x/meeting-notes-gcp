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

from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.dev_agent import backend, git_ops, guardrails, session_memory
from meeting_notes.dev_agent import lifecycle as lc
from meeting_notes.dev_agent.models import AgentRunResult

log = structlog.get_logger()


def build_prompt(ticket: dict[str, Any], resume_context: str | None = None) -> str:
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
    return f"""Read CLAUDE.md and follow all conventions in this repository.

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
        --base main --head {branch}
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


async def process_ticket(
    ticket: dict[str, Any],
    settings: Settings | None = None,
    *,
    claim_run: Any = None,
    set_state: Any = None,
    get_run: Any = None,
    finish_run: Any = None,
    transition_issue: Any = None,
    add_comment: Any = None,
    get_issue_detail: Any = None,
    create_worktree: Any = None,
    remove_worktree: Any = None,
    run_agent: Any = None,
    find_open_pr: Any = None,
    get_pr_diff: Any = None,
    verify_pr: Any = None,
    write_run_provenance: Any = None,
    load_resume_context: Any = None,
    record_session_memory: Any = None,
    run_gates: Any = None,
    review_pr: Any = None,
) -> None:
    """Implement one ticket end to end. Every I/O dependency is injectable so
    the whole flow is testable with no live Jira, git, GitHub, or Memgraph."""
    settings = settings or get_settings()

    if claim_run is None:
        from meeting_notes.db import claim_dev_agent_run as claim_run
    if set_state is None:
        from meeting_notes.db import set_dev_agent_state as set_state
    if get_run is None:
        from meeting_notes.db import get_dev_agent_run as get_run
    if finish_run is None:
        from meeting_notes.db import finish_dev_agent_run as finish_run
    if transition_issue is None:
        from meeting_notes.jira_client import transition_issue
    if add_comment is None:
        from meeting_notes.jira_client import add_comment
    if get_issue_detail is None:
        from meeting_notes.jira_client import get_issue_detail
    if create_worktree is None:
        create_worktree = git_ops.create_worktree
    if remove_worktree is None:
        remove_worktree = git_ops.remove_worktree
    if run_agent is None:
        from meeting_notes.dev_agent.gemini_runner import run_agent
    if find_open_pr is None:
        from meeting_notes.dev_agent.github_client import find_open_pr
    if get_pr_diff is None:
        from meeting_notes.dev_agent.github_client import get_pr_diff
    if verify_pr is None:
        from meeting_notes.dev_agent.self_verify import verify_pr
    if write_run_provenance is None:
        from meeting_notes.graph_client import write_run_provenance
    if load_resume_context is None:
        load_resume_context = session_memory.load_resume_context
    if record_session_memory is None:
        record_session_memory = session_memory.record
    if run_gates is None:
        from meeting_notes.dev_agent.gate_runner import run_gates
    if review_pr is None:
        from meeting_notes.dev_agent.reviewer import review_pr

    key = ticket["key"]
    bound_log = log.bind(ticket_key=key)
    branch_name = f"agent/{key}"
    dev_backend = backend.select_backend(settings)

    await claim_run(key, lc.TRIAGED, branch_name)

    try:
        ok = await transition_issue(key, "In Progress", settings=settings)
        if not ok:
            bound_log.warning("orchestrator.in_progress_transition_failed")
        await add_comment(key, f"Picked up by dev_agent (backend={dev_backend}).", settings=settings)

        detail = await get_issue_detail(key, settings=settings)
        await _advance_state(key, lc.PLANNED, set_state, get_run)
        work_dir = f"{settings.dev_agent_work_root}/{key}"

        await create_worktree(settings.dev_agent_repo_dir, work_dir, branch_name)
        resume_context = await load_resume_context(key)
        prompt = build_prompt(detail, resume_context=resume_context)

        await _advance_state(key, lc.IMPLEMENTING, set_state, get_run)
        result: AgentRunResult = await run_agent(
            work_dir, prompt,
            timeout_seconds=settings.dev_agent_timeout_seconds,
            model=backend.model_for_run(dev_backend, settings),
            settings=settings,
        )
        await _advance_state(key, lc.DEBUGGING, set_state, get_run)

        # The PR check gates the outcome, not result.success: a run can push a
        # branch and open a PR, then still report failure on a later step
        # (e.g. hits the turn limit on verification). Dropping that PR and
        # reverting the ticket to TO DO would lose good work.
        pr = await find_open_pr(
            settings.github_owner, settings.github_repo, branch_name, settings.github_token
        )

        if pr is None:
            reason = (result.result_text or "").strip()[:500] or "no error detail captured"
            if result.success:
                bound_log.error("orchestrator.pr_not_found")
                await finish_run(key, lc.FAILED, error="reported success but no PR was found")
                await add_comment(
                    key, "Dev agent reported success but no PR was found. Needs human follow-up.",
                    settings=settings,
                )
            else:
                bound_log.error("orchestrator.agent_failed", error=result.result_text[:200])
                await finish_run(key, lc.FAILED, error=result.result_text[:2000])
                await add_comment(
                    key,
                    "Dev agent could not complete this ticket automatically. Needs human "
                    f"follow-up.\n\nError: {reason}",
                    settings=settings,
                )
            await record_session_memory(
                detail, outcome="failed", error=reason, raw_notes=result.result_text or ""
            )
            # No graph Blocker write here: a Blocker hangs off a Meeting
            # (CLAUDE.md's schema: Meeting-[:RAISES_BLOCKER]->Blocker) and is
            # written inside that meeting's transaction from the extraction. A
            # dev-agent failure has no meeting behind it. The failure reason is
            # already in the Jira comment above and in session_memory, which is
            # what a retry actually reads from -- inventing a meeting_id to
            # force-fit the schema would misrepresent the data.
            await _advance_state(key, lc.FAILED, set_state, get_run)
            await transition_issue(key, "To Do", settings=settings)
            return

        await _advance_state(key, lc.REVIEWING, set_state, get_run)
        verdict = None
        diff = ""
        try:
            diff = await get_pr_diff(
                settings.github_owner, settings.github_repo, pr["number"], settings.github_token
            )
            verdict = await verify_pr(
                ticket, diff, model=backend.model_for_run(dev_backend, settings),
                threshold=settings.dev_agent_verify_threshold,
            )
        except Exception:
            bound_log.warning("orchestrator.self_verify_failed", exc_info=True)
        verified = verdict.passed if (verdict and verdict.checked) else None

        # The deterministic half of the safety net (ADR-020). Runs in the
        # worktree, so it must happen before the `finally` removes it. A gate
        # that fails means this PR is NOT shippable: the run escalates to
        # NEEDS_HUMAN, which is terminal, so the poller will not silently
        # retry it. The PR itself is deliberately left open — the work is
        # real, it just needs a person.
        try:
            gates = await run_gates(work_dir, diff, detail.get("description", ""), settings)
        except Exception as exc:  # noqa: BLE001 - an unrunnable gate is a human's problem
            bound_log.error("orchestrator.gates_errored", exc_info=True)
            gates = [
                guardrails.GateResult(
                    name="gates_errored", passed=False,
                    evidence=f"the gate step itself failed: {exc}",
                )
            ]
        failed = guardrails.failed_gates(gates)

        # Layer 2 (ADR-020): an independent reviewer, given the gate results so
        # it judges what they cannot rather than re-deriving them. It is skipped
        # when a gate already failed -- the run is stopping either way, and the
        # model call would be spent to reach a conclusion already reached.
        review = None
        if not failed:
            try:
                review = await review_pr(
                    detail, diff, gates,
                    model=backend.model_for_run(dev_backend, settings),
                )
            except Exception:  # noqa: BLE001 - an outage must not halt the run
                bound_log.warning("orchestrator.review_errored", exc_info=True)

        blocked_by_review = bool(review and review.blocking)

        if failed or blocked_by_review:
            reasons = []
            if failed:
                reasons.append(
                    "Failed gates:\n" + "\n".join(f"- {g.name}: {g.evidence}" for g in failed)
                )
            if blocked_by_review and review is not None:
                reasons.append("Reviewer findings:\n" + review.summary())
            detail_text = "\n\n".join(reasons)
            bound_log.warning(
                "orchestrator.review_blocked", failed=[g.name for g in failed],
                review_blocking=blocked_by_review, pr_url=pr["html_url"],
            )
            await add_comment(
                key,
                "Dev agent opened a PR but it did NOT pass review, so it has "
                f"not been marked shipped.\n\n{detail_text}\n\n"
                f"PR: {pr['html_url']}\n\nA human needs to review this before it merges.",
                settings=settings,
            )
            if not await transition_issue(key, "In Review", settings=settings):
                bound_log.warning("orchestrator.review_transition_failed")
            await finish_run(
                key, lc.NEEDS_HUMAN, pr_url=pr["html_url"], pr_number=pr["number"],
                error=(
                    "failed gates: " + ", ".join(g.name for g in failed) if failed
                    else "reviewer requested changes"
                ),
            )
            await _advance_state(key, lc.NEEDS_HUMAN, set_state, get_run)
            run_after = await get_run(key)
            try:
                await write_run_provenance(
                    ticket_key=key, attempt=run_after.attempt_count if run_after else 1,
                    pr_url=pr["html_url"], pr_number=pr.get("number"), branch=branch_name,
                    ticket_summary=ticket.get("summary", ""), status=lc.NEEDS_HUMAN,
                    verified=verified,
                )
            except Exception:
                bound_log.warning("orchestrator.provenance_write_failed", exc_info=True)
            await record_session_memory(
                detail, outcome="pr_opened", pr=pr,
                files_changed=session_memory.files_from_diff(diff),
                verdict=verdict, raw_notes=result.result_text or "",
            )
            return

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
        await add_comment(key, f"{base}{flag} PR: {pr['html_url']}", settings=settings)

        ok = await transition_issue(key, "In Review", settings=settings)
        if not ok:
            bound_log.warning("orchestrator.review_transition_failed")

        await finish_run(key, lc.SHIPPED, pr_url=pr["html_url"], pr_number=pr["number"])
        # SHIPPED: PR opened, ticket moved to review. CLOSED happens only via
        # /webhook/github's pull_request.merged handler — an actual human merge.
        await _advance_state(key, lc.SHIPPED, set_state, get_run)

        # Provenance: the AgentRun node /webhook/github's merge handler later
        # finds by PR url. Best-effort -- a graph hiccup must not lose the PR
        # link or block the Jira transition that already happened above.
        run_after = await get_run(key)
        attempt = run_after.attempt_count if run_after else 1
        try:
            await write_run_provenance(
                ticket_key=key, attempt=attempt, pr_url=pr["html_url"],
                pr_number=pr.get("number"), branch=branch_name,
                ticket_summary=ticket.get("summary", ""), status="SHIPPED",
                verified=verified,
            )
        except Exception:
            bound_log.warning("orchestrator.provenance_write_failed", exc_info=True)
        await record_session_memory(
            detail, outcome="pr_opened", pr=pr,
            files_changed=session_memory.files_from_diff(diff),
            verdict=verdict, raw_notes=result.result_text or "",
        )
        bound_log.info(
            "orchestrator.ticket_done", pr_url=pr["html_url"],
            run_success=result.success, verified=verified,
        )

    except Exception as exc:
        bound_log.error("orchestrator.unexpected_error", exc_info=True)
        error_text = str(exc)
        steps: list[Any] = [
            lambda: finish_run(key, lc.FAILED, error=error_text),
            lambda: _advance_state(key, lc.FAILED, set_state, get_run),
            lambda: record_session_memory(ticket, outcome="failed", error=error_text),
            lambda: transition_issue(key, "To Do", settings=settings),
        ]
        for step in steps:
            try:
                await step()
            except Exception:
                pass
    finally:
        work_dir = f"{settings.dev_agent_work_root}/{key}"
        await remove_worktree(settings.dev_agent_repo_dir, work_dir, branch_name, ignore_errors=True)


async def poll_and_process(
    settings: Settings | None = None,
    *,
    preflight: Any = None,
    ensure_repo_cloned: Any = None,
    get_active_run: Any = None,
    should_attempt: Any = None,
    get_issue_detail: Any = None,
    find_sprint_candidates: Any = find_sprint_candidates,
    process_ticket: Any = process_ticket,
) -> dict[str, Any]:
    """One poll cycle: preflight, resume a crashed run, then take new candidates.

    **The ADR-020 fix, end to end.** A run `get_active_run` returns must ALSO
    pass `should_attempt` before being resumed — not merely rely on the
    terminal-state exclusion the query already applies. That second,
    independent check is what stops a future drift in the terminal set from
    silently reproducing the SHIPPED resume loop.
    """
    settings = settings or get_settings()

    if preflight is None:
        preflight = backend.preflight
    if ensure_repo_cloned is None:
        ensure_repo_cloned = git_ops.ensure_repo_cloned
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

    try:
        await ensure_repo_cloned(
            settings.dev_agent_repo_dir, settings.github_owner, settings.github_repo,
            settings.github_token,
        )
    except Exception as exc:
        log.error("orchestrator.poll.repo_unavailable", error=str(exc))
        return {"attempted": 0, "reason": "repo_unavailable"}

    active = await get_active_run()
    if active is not None:
        # The independent second check (ADR-020) — resuming still requires
        # should_attempt to agree, regardless of what the exclusion query said.
        if not await should_attempt(active.ticket_key, settings.dev_agent_max_attempts):
            log.info(
                "orchestrator.poll.active_run_not_attemptable",
                ticket_key=active.ticket_key, state=active.state,
            )
        else:
            log.info(
                "orchestrator.poll.resuming_crashed_run",
                ticket_key=active.ticket_key, state=active.state,
            )
            try:
                active_detail = await get_issue_detail(active.ticket_key, settings=settings)
                await process_ticket(active_detail, settings)
            except Exception:
                log.error(
                    "orchestrator.poll.resume_failed", ticket_key=active.ticket_key, exc_info=True
                )

    tickets = await find_sprint_candidates(settings)
    eligible = []
    for ticket in tickets:
        if await should_attempt(ticket["key"], settings.dev_agent_max_attempts):
            eligible.append(ticket)

    batch = eligible[: settings.dev_agent_poll_batch_size]
    skipped = len(eligible) - len(batch)
    log.info(
        "orchestrator.poll.batch", considered=len(tickets), eligible=len(eligible),
        attempting=len(batch), deferred=skipped,
    )

    for ticket in batch:
        await process_ticket(ticket, settings)

    log.info("orchestrator.poll.done", attempted=len(batch))
    return {"attempted": len(batch)}
