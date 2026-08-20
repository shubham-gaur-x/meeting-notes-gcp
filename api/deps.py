"""Shared dependencies for the API layer.

Auth reuses `access_control` from Phase 2 rather than inventing a second
model. Query endpoints resolve a principal; webhooks do not — they cannot
carry a bearer token and are HMAC-verified instead.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from meeting_notes import access_control
from meeting_notes.access_control import Principal
from meeting_notes.config import Settings, get_settings

# Tier 0 has no policy file, so a local caller is unrestricted. That keeps a
# fresh clone runnable with no setup while leaving a configured policy fully
# enforced.
LOCAL_PRINCIPAL = Principal(name="local", role="admin", allowed_scopes=("all",))


def settings_dep() -> Settings:
    return get_settings()


async def principal(authorization: str | None = Header(default=None)) -> Principal:
    """Resolve the caller from a bearer token, or 401/403."""
    settings = get_settings()
    if not settings.access_policy_file.strip():
        return LOCAL_PRINCIPAL

    name = (authorization or "").removeprefix("Bearer ").strip()
    if not name:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return access_control.resolve_principal(name)
    except access_control.AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=403, detail="unknown principal") from exc
