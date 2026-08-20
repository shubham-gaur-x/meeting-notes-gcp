"""Token health — proactive checking, so expiry is never a silent surprise.

On the personal GCP project the refresh token dies every 7 days (External +
Testing), which makes this the single most likely runtime failure in the
system. Cloud Scheduler runs `jobs/refresh_tokens.py` every 6 hours; this is
what it calls.

The whole point is that a dead token produces a **visible, actionable
alert**. A connector that silently stages zero rows looks exactly like "no
new meetings this week".
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from meeting_notes import google_auth
from meeting_notes.config import Settings, get_settings

log = structlog.get_logger()


@dataclass(frozen=True)
class TokenHealth:
    healthy: bool
    detail: str
    remediation: str | None = None


async def check(settings: Settings | None = None, *, transport: object = None) -> TokenHealth:
    """Refresh the token to prove it still works."""
    settings = settings or get_settings()
    try:
        await google_auth.get_access_token(settings, transport=transport)  # type: ignore[arg-type]
    except google_auth.TokenExpired as exc:
        # log.error, not warning: this stops all ingestion until fixed.
        log.error("token_health.expired", reason=str(exc))
        return TokenHealth(False, "refresh token rejected", google_auth.RECONSENT_HINT)
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        log.error("token_health.check_failed", error=str(exc))
        return TokenHealth(False, f"token check failed: {exc}", "Retry; if it persists, re-consent.")

    log.info("token_health.ok")
    return TokenHealth(True, "refresh token is valid")


def render(health: TokenHealth) -> str:
    if health.healthy:
        return "  OAuth refresh token: OK"
    lines = ["", "  !! OAUTH REFRESH TOKEN PROBLEM — INGESTION IS STOPPED !!", ""]
    lines.append(f"  {health.detail}")
    if health.remediation:
        lines.append(f"  -> {health.remediation}")
    lines.append("")
    return "\n".join(lines)
