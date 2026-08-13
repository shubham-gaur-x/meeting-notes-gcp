#!/usr/bin/env python3
"""Phase 0.5 auth spike — prove the Workspace OAuth path works end to end.

Runs a local loopback consent flow, stores the refresh token, and makes one real
call against Gmail, Calendar and Meet. See docs/GOOGLE_AUTH.md.

Two deliberate choices:

* The OAuth flow is hand-rolled over httpx rather than using
  google_auth_oauthlib. CLAUDE.md mandates httpx for all HTTP and the Google
  client libraries are synchronous httplib2; the exchange and refresh helpers
  here are reused by jobs/refresh_tokens.py in Phase 5.
* The callback server binds an ephemeral port, so there is no fixed-port
  collision to work around as there is in v5's refresh_gcal_token.py.

This script imports nothing from meeting_notes/ — that package does not exist
until Phase 2, and Phase 0.5 gates every other phase.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import cast

import httpx
import structlog

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
CALENDAR_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MEET_URL = "https://meet.googleapis.com/v2/conferenceRecords"

# Exactly four. Every extra scope makes an admin allowlist request harder to
# approve — docs/GOOGLE_AUTH.md §4.
SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/meetings.space.readonly",
    "https://www.googleapis.com/auth/pubsub",
)

# External + Testing OAuth apps issue refresh tokens that die after exactly
# 7 days. docs/GOOGLE_AUTH.md §3.
REFRESH_TOKEN_LIFETIME_DAYS = 7

DEFAULT_TOKEN_PATH = Path(__file__).resolve().parent.parent / "token.json"

log = structlog.get_logger(source="auth_spike")


# ─── PKCE and the consent URL ─────────────────────────────────────────────────


def pkce_pair() -> tuple[str, str]:
    """Return a (code_verifier, code_challenge) pair using S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_auth_url(*, client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    """Build the Google consent URL.

    access_type=offline and prompt=consent are both required: without them Google
    may omit the refresh token on a repeat authorisation.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


# ─── token store ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StoredToken:
    """A refresh token plus the metadata needed to reason about its expiry."""

    refresh_token: str
    issued_at: datetime
    scopes: tuple[str, ...]

    @property
    def age_days(self) -> float:
        return (datetime.now(UTC) - self.issued_at).total_seconds() / 86400.0

    @property
    def days_until_expiry(self) -> float:
        return REFRESH_TOKEN_LIFETIME_DAYS - self.age_days

    @property
    def is_expired(self) -> bool:
        return self.days_until_expiry <= 0


def save_token(path: Path, token: StoredToken) -> None:
    """Write the token 0600.

    The mode is set at open time. A write-then-chmod would leave a window in
    which the token is world-readable.
    """
    payload = {
        "refresh_token": token.refresh_token,
        "issued_at": token.issued_at.isoformat(),
        "scopes": list(token.scopes),
    }
    handle_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def load_token(path: Path) -> StoredToken | None:
    """Load a stored token, or None if there isn't one."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return StoredToken(
        refresh_token=payload["refresh_token"],
        issued_at=datetime.fromisoformat(payload["issued_at"]),
        scopes=tuple(payload["scopes"]),
    )


# ─── loopback callback server ─────────────────────────────────────────────────

_SUCCESS_PAGE = (
    b"<html><body style='font-family:system-ui;padding:40px'>"
    b"<h2>Authorisation complete</h2>"
    b"<p>You can close this tab and return to the terminal.</p>"
    b"</body></html>"
)


@dataclass(frozen=True)
class CallbackResult:
    code: str | None
    error: str | None
    state: str | None


class CallbackServer(HTTPServer):
    """An HTTPServer that captures a single OAuth callback."""

    result: CallbackResult | None = None

    def __init__(
        self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler]
    ) -> None:
        super().__init__(server_address, handler_class)
        self.done = threading.Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/favicon"):
            self.send_response(204)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        server = cast(CallbackServer, self.server)
        server.result = CallbackResult(
            code=params.get("code", [None])[0],
            error=params.get("error", [None])[0],
            state=params.get("state", [None])[0],
        )

        self.send_response(200 if server.result.code else 400)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_SUCCESS_PAGE if server.result.code else b"Authorisation failed.")
        server.done.set()

    def log_message(self, format: str, *args: object) -> None:
        """Silence the default stderr access log.

        It would echo the query string, which carries the authorization code.
        """


def start_callback_server() -> tuple[CallbackServer, str]:
    """Bind an ephemeral loopback port and return the server and its redirect URI.

    Port 0 lets the OS choose. Desktop OAuth clients accept any loopback port,
    which is what removes v5's fixed-port collision.
    """
    server = CallbackServer(("127.0.0.1", 0), _CallbackHandler)
    port = int(server.server_address[1])
    return server, f"http://127.0.0.1:{port}/callback"


def wait_for_code(server: CallbackServer, *, expected_state: str, timeout: float) -> str:
    """Block until the callback arrives, then validate it and return the code."""
    if not server.done.wait(timeout=timeout):
        raise RuntimeError(f"timed out after {timeout:.0f}s waiting for authorisation")

    result = server.result
    if result is None:
        raise RuntimeError("callback fired with no result")
    if result.error:
        raise RuntimeError(f"authorisation failed: {result.error}")
    if result.state != expected_state:
        raise RuntimeError("state mismatch — possible CSRF, discarding response")
    if not result.code:
        raise RuntimeError("callback carried no authorization code")
    return result.code


# ─── token exchange and refresh ───────────────────────────────────────────────


def _error_of(response: httpx.Response) -> str:
    """Pull Google's error string out of a response body.

    Only the error/message fields are read. The body is never echoed wholesale,
    and the request — which carries the client secret — is never logged.
    """
    try:
        body = response.json()
    except ValueError:
        return "unparseable response body"
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message", error))
        if error:
            return str(error)
    return "unknown error"


async def exchange_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict[str, object]:
    """Exchange an authorization code for tokens."""
    response = await client.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "code_verifier": verifier,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        raise RuntimeError(f"token exchange failed ({response.status_code}): {_error_of(response)}")

    payload: dict[str, object] = response.json()
    if not payload.get("refresh_token"):
        raise RuntimeError(
            "token response carried no refresh_token — re-run with --reconsent so "
            "prompt=consent forces Google to issue one"
        )
    return payload


async def refresh_access_token(
    client: httpx.AsyncClient, *, refresh_token: str, client_id: str, client_secret: str
) -> str:
    """Mint a fresh access token from a stored refresh token."""
    response = await client.post(
        GOOGLE_TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"refresh failed ({response.status_code}): {_error_of(response)} — "
            "the 7-day refresh token has probably expired. Re-run with --reconsent."
        )
    return str(response.json()["access_token"])


# ─── API probes ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProbeResult:
    api: str
    ok: bool
    detail: str
    records: int | None = None


async def _probe(
    client: httpx.AsyncClient,
    access_token: str,
    *,
    api: str,
    url: str,
    params: dict[str, str],
    results_key: str,
) -> ProbeResult:
    try:
        response = await client.get(
            url, params=params, headers={"Authorization": f"Bearer {access_token}"}
        )
    except httpx.HTTPError as exc:
        return ProbeResult(api=api, ok=False, detail=f"transport error: {type(exc).__name__}")

    if response.status_code != 200:
        return ProbeResult(
            api=api, ok=False, detail=f"HTTP {response.status_code}: {_error_of(response)}"
        )

    records = 0
    body = response.json()
    if isinstance(body, dict):
        items = body.get(results_key, [])
        if isinstance(items, list):
            records = len(items)
    return ProbeResult(api=api, ok=True, detail="reachable", records=records)


async def probe_gmail(client: httpx.AsyncClient, access_token: str) -> ProbeResult:
    return await _probe(
        client,
        access_token,
        api="Gmail",
        url=GMAIL_URL,
        params={"maxResults": "1"},
        results_key="messages",
    )


async def probe_calendar(client: httpx.AsyncClient, access_token: str) -> ProbeResult:
    return await _probe(
        client,
        access_token,
        api="Calendar",
        url=CALENDAR_URL,
        params={"maxResults": "1"},
        results_key="items",
    )


async def probe_meet(client: httpx.AsyncClient, access_token: str) -> ProbeResult:
    return await _probe(
        client,
        access_token,
        api="Meet",
        url=MEET_URL,
        params={"pageSize": "1"},
        results_key="conferenceRecords",
    )


async def run_probes(client: httpx.AsyncClient, access_token: str) -> list[ProbeResult]:
    return [
        await probe_gmail(client, access_token),
        await probe_calendar(client, access_token),
        await probe_meet(client, access_token),
    ]


# ─── report ───────────────────────────────────────────────────────────────────


def render_report(results: list[ProbeResult], token: StoredToken) -> str:
    """Render the human-readable outcome.

    Carries every fact the Phase 0.5 outcome ADR needs. Never renders the token
    itself — only its issue date and remaining lifetime.
    """
    lines: list[str] = ["", "Phase 0.5 auth spike — results", "=" * 46]

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        line = f"  [{status}] {result.api:<9} {result.detail}"
        if result.ok and result.records is not None:
            line += f" ({result.records} record(s))"
        lines.append(line)
        if result.api == "Meet" and result.ok and result.records == 0:
            lines.append(
                "         note: reachable, but no conference records returned. "
                "Meet transcription may be off for this tenant."
            )

    lines += [
        "",
        "Refresh token",
        "-" * 46,
        f"  issued          {token.issued_at.date().isoformat()}",
        f"  days remaining  {token.days_until_expiry:.1f} of {REFRESH_TOKEN_LIFETIME_DAYS}",
        f"  scopes          {len(token.scopes)} granted",
        "",
        "  Token value is never printed. Stored 0600 in token.json (gitignored).",
        "  Re-run with --reconsent when it expires.",
        "",
    ]
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def load_client_credentials(env: Mapping[str, str]) -> tuple[str, str]:
    """Read the OAuth client id and secret, or explain exactly what's missing."""
    client_id = env.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = env.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    missing = [
        name
        for name, value in (
            ("GOOGLE_OAUTH_CLIENT_ID", client_id),
            ("GOOGLE_OAUTH_CLIENT_SECRET", client_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"{' and '.join(missing)} not set. Create a Desktop OAuth client and put "
            "the values in .env — see docs/GOOGLE_AUTH.md §5.3."
        )
    return client_id, client_secret


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auth_spike",
        description="Phase 0.5 — prove the Workspace OAuth path works end to end.",
    )
    parser.add_argument(
        "--reconsent",
        action="store_true",
        help="force a fresh consent flow, discarding any stored token",
    )
    parser.add_argument(
        "--token-path", type=Path, default=DEFAULT_TOKEN_PATH, help="where token.json lives"
    )
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="seconds to wait for browser consent"
    )
    return parser


async def _consent(
    client: httpx.AsyncClient, *, client_id: str, client_secret: str, consent_timeout: float
) -> StoredToken:
    """Run the interactive loopback consent flow.

    wait_for_code blocks on a threading.Event, so it runs via asyncio.to_thread
    rather than stalling the event loop. asyncio.timeout would not help here —
    it cannot interrupt a blocking synchronous call.
    """
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    server, redirect_uri = start_callback_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        auth_url = build_auth_url(
            client_id=client_id, redirect_uri=redirect_uri, challenge=challenge, state=state
        )
        print(f"\nOpening your browser to authorise.\nIf it doesn't open:\n\n  {auth_url}\n")
        webbrowser.open(auth_url)
        log.info("awaiting_consent", step="consent", redirect_uri=redirect_uri)
        code = await asyncio.to_thread(
            wait_for_code, server, expected_state=state, timeout=consent_timeout
        )
    finally:
        server.shutdown()
        server.server_close()

    payload = await exchange_code(
        client,
        code=code,
        verifier=verifier,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )
    return StoredToken(
        refresh_token=str(payload["refresh_token"]),
        issued_at=datetime.now(UTC),
        scopes=SCOPES,
    )


async def _run(args: argparse.Namespace) -> int:
    client_id, client_secret = load_client_credentials(os.environ)
    token = None if args.reconsent else load_token(args.token_path)

    async with httpx.AsyncClient(timeout=30.0) as client:
        if token is None or token.is_expired:
            reason = "reconsent requested" if args.reconsent else "no valid stored token"
            log.info("starting_consent", step="consent", reason=reason)
            token = await _consent(
                client,
                client_id=client_id,
                client_secret=client_secret,
                consent_timeout=args.timeout,
            )
            save_token(args.token_path, token)
            log.info("token_stored", step="consent", path=str(args.token_path))

        access_token = await refresh_access_token(
            client,
            refresh_token=token.refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
        results = await run_probes(client, access_token)

    print(render_report(results, token))
    return 0 if all(result.ok for result in results) else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except RuntimeError as exc:
        print(f"\nERROR: {exc}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
