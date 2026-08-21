"""Self-verification: score a dev-agent PR diff against the ticket intent.

Runs one cheap scoring pass through the same coding backend the run used.
This scores *code*, so it deliberately goes through `dev_agent.backend`, not
`meeting_notes.llm_client` — the same separation the rest of this package
holds to.

**Verification NEVER blocks the review transition.** A low score only flags
the Jira comment and leaves `AgentRun.verified = false` in the graph; a human
still reviews either way. This is by design, not a missing feature: a
false-negative verification (a good PR scored badly) must not silently
prevent a human from ever seeing it.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

from meeting_notes.utils import strip_json_fences

log = structlog.get_logger()

DEFAULT_THRESHOLD = 0.6

_PROMPT = """You are reviewing whether a pull request diff actually implements a Jira ticket.

Ticket: {key}
Summary: {summary}
Description:
{description}

Diff:
{diff}

Respond ONLY with JSON matching exactly this schema:
{{"addresses": true|false, "confidence": 0.0 to 1.0, "reason": "one sentence"}}
"""


class VerifyVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    checked: bool = False  # did a scoring pass actually run AND parse?
    addresses: bool = False  # does the diff plausibly satisfy the ticket?
    confidence: float = 0.0
    reason: str = ""
    threshold: float = DEFAULT_THRESHOLD

    @property
    def passed(self) -> bool:
        """All three independently: checked AND addresses AND confidence >= threshold.

        A malformed or unreachable scoring pass leaves `checked=False`, which
        alone makes this False regardless of the other fields — an unscored
        diff is not the same as a confirmed one.
        """
        return self.checked and self.addresses and self.confidence >= self.threshold


async def verify_pr(
    ticket: dict[str, Any],
    diff: str,
    *,
    model: str | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    run_oneshot: Any = None,
) -> VerifyVerdict:
    """Score one PR diff against its ticket. Never raises — degrades to unchecked."""
    if run_oneshot is None:
        from meeting_notes.dev_agent.gemini_runner import run_oneshot as default_runner

        run_oneshot = default_runner

    prompt = _PROMPT.format(
        key=ticket.get("key", ""),
        summary=ticket.get("summary", ""),
        description=ticket.get("description", ""),
        diff=diff[:20_000],
    )

    try:
        raw = await run_oneshot(prompt, timeout_seconds=120, model=model)
        if not raw:
            return VerifyVerdict(threshold=threshold)
        parsed = json.loads(strip_json_fences(raw).strip())
        return VerifyVerdict(
            checked=True,
            addresses=bool(parsed.get("addresses", False)),
            confidence=float(parsed.get("confidence", 0.0)),
            reason=str(parsed.get("reason", ""))[:500],
            threshold=threshold,
        )
    except Exception as exc:  # noqa: BLE001 - self-verify must never block review
        log.warning("self_verify.failed", error=str(exc))
        return VerifyVerdict(threshold=threshold)
