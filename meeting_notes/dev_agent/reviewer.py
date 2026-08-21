"""The independent LLM reviewer — layer 2 of the PR safety net (ADR-020).

Layer 1 is `guardrails.py`: seven deterministic gates that answer questions
with a yes or no. This layer answers the question they cannot — *is the change
actually correct and safe?* — and it is deliberately given the gate results as
well as the ticket and diff, so it reasons about what is left rather than
re-deriving what the gates already established.

Like `self_verify`, this scores *code*, so it goes through `dev_agent.backend`
rather than `meeting_notes.llm_client` (CLAUDE.md).

**Blocking, but asymmetrically with the gates.** A high or medium finding stops
the run at `NEEDS_HUMAN`; a low one only annotates the Jira comment. An
unreachable or unparseable reviewer does **not** block, which is the opposite
of the gate rule and is deliberate:

* an unrunnable *gate* hides a cheap, certain fact, so its absence is treated
  as failure;
* an unreachable *model* is an availability problem. The seven gates have
  already run, no PR is ever auto-merged, and a human reviews before any merge
  — so a model outage must not halt the pipeline.

This is why `checked` is separate from `verdict`: an unscored PR is never
confused with an approved one.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

from meeting_notes.dev_agent.guardrails import GateResult, ReviewFinding
from meeting_notes.utils import strip_json_fences

log = structlog.get_logger()

# A finding at or above this severity stops the run. "low" is advisory.
BLOCKING_SEVERITIES = frozenset({"high", "medium"})

_PROMPT = """You are an independent reviewer of a pull request opened by an automated coding agent.
You did not write this code. Your job is to find what is wrong with it.

Ticket: {key}
Summary: {summary}
Description:
{description}

Deterministic checks already run against this PR (do NOT repeat these — they are settled):
{gate_evidence}

Diff:
{diff}

Judge only what the checks above cannot: correctness, unhandled failure modes,
data loss, race conditions, security holes, and whether the change actually does
what the ticket asked. Do not comment on formatting or style.

Severity means: "high" = do not merge, "medium" = must be addressed before merge,
"low" = a nit worth mentioning.

Respond ONLY with JSON matching exactly this schema:
{{"verdict": "approve" | "request_changes",
  "findings": [{{"severity": "high|medium|low", "file": "path",
                 "issue": "what is wrong", "suggested_fix": "how to fix it"}}]}}
"""


class ReviewOutcome(BaseModel):
    """The reviewer's judgement on one PR."""

    model_config = ConfigDict(extra="ignore")

    # Did a review actually run AND parse? Kept separate from `verdict` so an
    # unreachable reviewer is never mistaken for an approving one.
    checked: bool = False
    verdict: str = ""
    findings: list[ReviewFinding] = []

    @property
    def blocking(self) -> bool:
        """True only for a review that ran and found something serious."""
        if not self.checked:
            return False
        return any(f.severity.lower() in BLOCKING_SEVERITIES for f in self.findings)

    def summary(self) -> str:
        """Human-readable findings for the Jira comment."""
        if not self.checked:
            return "the reviewer did not run"
        if not self.findings:
            return "no findings"
        return "\n".join(
            f"- [{f.severity}] {f.file or 'general'}: {f.issue}"
            + (f" — suggested: {f.suggested_fix}" if f.suggested_fix else "")
            for f in self.findings
        )


def _format_gates(gates: list[GateResult]) -> str:
    if not gates:
        return "(none run)"
    return "\n".join(
        f"- {g.name}: {'PASS' if g.passed else 'FAIL'} — {g.evidence[:200]}" for g in gates
    )


async def review_pr(
    ticket: dict[str, Any],
    diff: str,
    gates: list[GateResult],
    *,
    model: str | None = None,
    run_oneshot: Any = None,
) -> ReviewOutcome:
    """Review one PR. Never raises — degrades to `checked=False`, which never blocks."""
    if run_oneshot is None:
        from meeting_notes.dev_agent.gemini_runner import run_oneshot as default_runner

        run_oneshot = default_runner

    prompt = _PROMPT.format(
        key=ticket.get("key", ""),
        summary=ticket.get("summary", ""),
        description=ticket.get("description", ""),
        gate_evidence=_format_gates(gates),
        diff=diff[:40_000],
    )

    try:
        raw = await run_oneshot(prompt, timeout_seconds=300, model=model)
        if not raw:
            return ReviewOutcome()
        parsed = json.loads(strip_json_fences(raw).strip())
        outcome = ReviewOutcome(
            checked=True,
            verdict=str(parsed.get("verdict", "")),
            findings=[ReviewFinding.model_validate(f) for f in parsed.get("findings", [])],
        )
    except Exception as exc:  # noqa: BLE001 - an unreachable reviewer must not halt the run
        log.warning("reviewer.failed", error=str(exc))
        return ReviewOutcome()

    log.info(
        "reviewer.done", verdict=outcome.verdict,
        findings=len(outcome.findings), blocking=outcome.blocking,
    )
    return outcome
