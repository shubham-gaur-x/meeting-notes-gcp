"""Google OAuth for the connectors: refresh token in, access token out.

`scripts/auth_spike.py` already does this correctly, but it lives in
`scripts/` and predates `config.py` by design. Connectors and
`jobs/refresh_tokens.py` need a package-resident version that reads settings.

**An expired refresh token raises.** On the personal GCP project the token
dies every 7 days (External + Testing), so this is the single most likely
runtime failure in the whole system. Returning None would let a connector
stage zero rows and report success — indistinguishable from "no new meetings
this week", which is the most misleading outcome available here.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.utils import with_retry

log = structlog.get_logger()

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Where scripts/auth_spike.py stores the token it obtains. Deployed, the
# refresh token arrives as an env var from Secret Manager; locally it lives
# here, and without this fallback every local run would need it copied by
# hand into .env.
DEFAULT_TOKEN_PATH = Path(__file__).resolve().parent.parent / "token.json"

RECONSENT_HINT = (
    "Run `make auth-spike ARGS=--reconsent` to re-consent. On the personal GCP "
    "project the refresh token expires every 7 days (External + Testing); "
    "docs/GOOGLE_AUTH.md §8 covers the permanent fix."
)

# (url, form_data) -> (status_code, body)
Transport = Callable[[str, dict[str, str]], Awaitable[tuple[int, str]]]


class TokenExpired(RuntimeError):
    """The refresh token is gone or rejected. Deliberately fatal."""


async def _default_transport(url: str, data: dict[str, str]) -> tuple[int, str]:
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, data=data)
        return response.status_code, response.text


def load_refresh_token(settings: Settings, *, path: Path | None = None) -> str:
    """The refresh token, preferring configuration over the local file.

    Settings win because that is what Cloud Run injects from Secret Manager;
    token.json is the local-development fallback that auth_spike writes.
    """
    from_settings = settings.google_refresh_token.strip()
    if from_settings:
        return from_settings

    token_path = path or DEFAULT_TOKEN_PATH
    if not token_path.exists():
        return ""
    try:
        stored: str = json.loads(token_path.read_text(encoding="utf-8")).get("refresh_token", "")
        return stored.strip()
    except (json.JSONDecodeError, ValueError, OSError):
        return ""


@with_retry(max_attempts=3, base_delay=2.0)
async def _post_token(url: str, data: dict[str, str], transport: Transport) -> tuple[int, str]:
    """Retried transport boundary. A 5xx is transient; an invalid_grant is not,
    and is handled by the caller rather than retried."""
    status, body = await transport(url, data)
    if status >= 500:
        raise RuntimeError(f"token endpoint returned {status}")
    return status, body


async def get_access_token(
    settings: Settings | None = None,
    *,
    transport: Transport | None = None,
    token_path: Path | None = None,
) -> str:
    """Exchange the stored refresh token for a short-lived access token.

    `token_path` is injected the same way every other probe in this codebase
    is, so a test can prove the no-token path without depending on whether
    the developer running it happens to have a real token.json.
    """
    settings = settings or get_settings()
    refresh_token = load_refresh_token(settings, path=token_path)

    if not refresh_token:
        raise TokenExpired(
            "No refresh token: GOOGLE_REFRESH_TOKEN is unset and there is no "
            f"token.json. {RECONSENT_HINT}"
        )

    transport = transport or _default_transport
    status, body = await _post_token(
        GOOGLE_TOKEN_URL,
        {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        transport,
    )

    if status != 200:
        # Parse defensively: the error body is not always JSON.
        try:
            error = json.loads(body).get("error", "")
        except (json.JSONDecodeError, ValueError):
            error = ""
        # Never interpolate `body` or the token into the message — an error
        # string is the easiest place for a credential to reach logs.
        if error in ("invalid_grant", "invalid_request", "unauthorized_client"):
            log.error("google_auth.refresh_token_expired", oauth_error=error)
            raise TokenExpired(f"Refresh token rejected ({error}). {RECONSENT_HINT}")
        raise RuntimeError(f"Token refresh failed with HTTP {status} ({error or 'no error code'})")

    payload: dict[str, Any] = json.loads(body)
    token: str = payload["access_token"]
    log.info("google_auth.access_token_refreshed", expires_in=payload.get("expires_in"))
    return token

