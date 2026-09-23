"""Shared dependencies for the API layer.

Auth reuses `access_control` from Phase 2 rather than inventing a second
model. Query endpoints resolve a principal; webhooks do not — they cannot
carry a bearer token and are HMAC-verified instead.
"""

from __future__ import annotations

import structlog
from fastapi import Header, HTTPException

from meeting_notes import access_control
from meeting_notes.access_control import Principal
from meeting_notes.config import Settings, get_settings

# Tier 0 has no policy file, so a local caller is unrestricted. That keeps a
# fresh clone runnable with no setup while leaving a configured policy fully
# enforced.
LOCAL_PRINCIPAL = Principal(name="local", role="admin", allowed_scopes=("all",))

log = structlog.get_logger()


def settings_dep() -> Settings:
    return get_settings()


async def principal(authorization: str | None = Header(default=None)) -> Principal:
    """Resolve the caller from a bearer token, or 401/403/503.

    Three cases, deliberately the same shape as the webhook guards in
    `api/routers/webhooks.py`:

    * policy file configured -> enforce it
    * no policy file, but running on Cloud Run -> 503, fail closed
    * neither -> local development, unrestricted

    The middle case is why this function is not a one-liner. Returning
    `LOCAL_PRINCIPAL` whenever the policy file is unset keeps a fresh clone
    runnable, which is what tier 0 needs -- but it did the same thing in a
    deployed service, handing every caller `role="admin"`. That surface includes
    `POST /jira/*`, which mutates a real Jira project, and
    `POST /dev_agent/trigger`, which starts an autonomous coding agent. An
    unconfigured deployment was indistinguishable from a working one until
    somebody posted to a write route.

    The deployed signal is `K_SERVICE`, which Cloud Run injects, not
    `gcp_project_id`. The webhook guards use the project id, and that is fine
    there because they gate one expensive route -- but this dependency gates
    every read route including the dashboard, and a tier-2 local run sets a
    project id so Vertex works. Keying on it made 39 tests fail locally while
    passing in CI, which is exactly the shape of a developer being locked out of
    their own machine. `K_SERVICE` cannot be set accidentally outside Cloud Run.
    """
    settings = get_settings()
    if not settings.access_policy_file.strip():
        if settings.k_service.strip():
            log.error("api.auth.no_policy_file_configured", service=settings.k_service)
            raise HTTPException(
                status_code=503, detail="ACCESS_POLICY_FILE not configured"
            )
        log.warning("api.auth.unauthenticated_local")
        return LOCAL_PRINCIPAL

    name = (authorization or "").removeprefix("Bearer ").strip()
    if not name:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return access_control.resolve_principal(name)
    except access_control.AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=403, detail="unknown principal") from exc
