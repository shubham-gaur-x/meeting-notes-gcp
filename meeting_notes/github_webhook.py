"""GitHub webhook signature verification.

Webhooks are the one public surface: they cannot carry a bearer token, so
authenticity rests entirely on the HMAC. Everything here is about not getting
that wrong.

**One deliberate difference from v5.** v5 accepted any payload when
`GITHUB_WEBHOOK_SECRET` was unset — a reasonable local default and a bad
deployed one, since a missing secret in production silently turns the endpoint
into an unauthenticated graph writer. v6 accepts an unset secret only when the
configuration is clearly local (no `gcp_project_id`); deployed, an unset secret
rejects.
"""

from __future__ import annotations

import hashlib
import hmac

import structlog

from meeting_notes.config import Settings, get_settings

log = structlog.get_logger()

SIGNATURE_HEADER = "X-Hub-Signature-256"
_PREFIX = "sha256="


def sign(body: bytes, secret: str) -> str:
    """The header value GitHub would send for this body and secret."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{_PREFIX}{digest}"


def verify_signature(
    body: bytes, header: str | None, secret: str, *, settings: Settings | None = None
) -> bool:
    """Constant-time HMAC check.

    `hmac.compare_digest` rather than `==`: a naive comparison leaks how much
    of the signature matched through its timing, which is enough to forge one
    byte at a time.
    """
    if not secret:
        settings = settings or get_settings()
        is_local = not settings.gcp_project_id.strip()
        if is_local:
            log.warning("github_webhook.unverified_local", reason="no secret configured")
            return True
        # Deployed with no secret: refuse rather than accept anything. A
        # missing secret in production would otherwise leave an unauthenticated
        # write path into the graph.
        log.error("github_webhook.no_secret_configured")
        return False

    if not header:
        return False
    return hmac.compare_digest(sign(body, secret), header)
