"""Phase 0.5 — the auth spike.

Everything here runs with no live GCP, no Google credentials, and no network
egress. Google API calls are mocked with httpx.MockTransport; the callback-server
tests bind 127.0.0.1 on an ephemeral port, which is the only honest way to test
an HTTP handler and is not an external dependency.
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
import sys
import threading
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from scripts.auth_spike import (
    REFRESH_TOKEN_LIFETIME_DAYS,
    SCOPES,
    ProbeResult,
    StoredToken,
    build_auth_url,
    build_parser,
    exchange_code,
    load_client_credentials,
    load_env_file,
    load_token,
    pkce_pair,
    probe_calendar,
    probe_gmail,
    probe_meet,
    refresh_access_token,
    render_report,
    run_probes,
    save_token,
    start_callback_server,
    wait_for_code,
)

# ─── helpers ──────────────────────────────────────────────────────────────────


def _token(age_days: float = 0.0, refresh_token: str = "rt-secret-value") -> StoredToken:
    return StoredToken(
        refresh_token=refresh_token,
        issued_at=datetime.now(UTC) - timedelta(days=age_days),
        scopes=SCOPES,
    )


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ─── PKCE and the consent URL ─────────────────────────────────────────────────


def test_pkce_verifier_length_is_rfc7636_compliant() -> None:
    verifier, _ = pkce_pair()
    assert 43 <= len(verifier) <= 128


def test_pkce_challenge_is_s256_of_verifier() -> None:
    verifier, challenge = pkce_pair()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_pkce_pair_is_random_each_call() -> None:
    assert pkce_pair()[0] != pkce_pair()[0]


def test_auth_url_carries_offline_and_consent() -> None:
    url = build_auth_url(
        client_id="cid",
        redirect_uri="http://127.0.0.1:9/callback",
        challenge="chal",
        state="st",
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == ["chal"]
    assert query["state"] == ["st"]
    assert query["response_type"] == ["code"]


def test_auth_url_requests_exactly_the_four_scopes() -> None:
    url = build_auth_url(
        client_id="cid",
        redirect_uri="http://127.0.0.1:9/callback",
        challenge="chal",
        state="st",
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["scope"][0].split(" ") == list(SCOPES)
    assert len(SCOPES) == 4


# ─── token store ──────────────────────────────────────────────────────────────


def test_save_then_load_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "token.json"
    original = _token()
    save_token(path, original)
    loaded = load_token(path)
    assert loaded is not None
    assert loaded.refresh_token == original.refresh_token
    assert loaded.scopes == original.scopes


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX permission bits: chmod is a no-op on Windows, so this can only "
    "ever fail there. It is a real requirement on the Linux runner and in Cloud "
    "Run, which is where the token file actually lives.",
)
def test_saved_file_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "token.json"
    save_token(path, _token())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_load_returns_none_when_absent(tmp_path: Path) -> None:
    assert load_token(tmp_path / "nope.json") is None


def test_age_and_expiry_math() -> None:
    fresh = _token(age_days=0.0)
    assert fresh.age_days < 0.01
    assert not fresh.is_expired
    assert abs(fresh.days_until_expiry - REFRESH_TOKEN_LIFETIME_DAYS) < 0.01

    old = _token(age_days=8.0)
    assert old.is_expired
    assert old.days_until_expiry < 0


# ─── loopback callback server ─────────────────────────────────────────────────


def test_server_returns_loopback_redirect_uri() -> None:
    server, redirect_uri = start_callback_server()
    try:
        assert redirect_uri.startswith("http://127.0.0.1:")
        assert redirect_uri.endswith("/callback")
        assert f":{server.server_address[1]}/" in redirect_uri
    finally:
        server.server_close()


def test_wait_for_code_returns_the_code() -> None:
    server, redirect_uri = start_callback_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        httpx.get(redirect_uri, params={"code": "abc123", "state": "st"}, timeout=5)
        assert wait_for_code(server, expected_state="st", timeout=5) == "abc123"
    finally:
        server.shutdown()
        server.server_close()


def test_wait_for_code_rejects_state_mismatch() -> None:
    server, redirect_uri = start_callback_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        httpx.get(redirect_uri, params={"code": "abc", "state": "WRONG"}, timeout=5)
        with pytest.raises(RuntimeError, match="state mismatch"):
            wait_for_code(server, expected_state="st", timeout=5)
    finally:
        server.shutdown()
        server.server_close()


def test_wait_for_code_surfaces_denial() -> None:
    server, redirect_uri = start_callback_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        httpx.get(redirect_uri, params={"error": "access_denied", "state": "st"}, timeout=5)
        with pytest.raises(RuntimeError, match="access_denied"):
            wait_for_code(server, expected_state="st", timeout=5)
    finally:
        server.shutdown()
        server.server_close()


# ─── token exchange and refresh ───────────────────────────────────────────────


async def test_exchange_code_posts_verifier_and_returns_payload() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(urllib.parse.parse_qsl(request.content.decode())))
        return httpx.Response(200, json={"refresh_token": "rt", "access_token": "at"})

    async with _mock_client(handler) as client:
        payload = await exchange_code(
            client,
            code="c",
            verifier="v",
            client_id="cid",
            client_secret="csec",
            redirect_uri="http://127.0.0.1:1/callback",
        )

    assert payload["refresh_token"] == "rt"
    assert seen["code_verifier"] == "v"
    assert seen["grant_type"] == "authorization_code"


async def test_exchange_code_raises_without_refresh_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "at"})

    async with _mock_client(handler) as client:
        with pytest.raises(RuntimeError, match="no refresh_token"):
            await exchange_code(
                client,
                code="c",
                verifier="v",
                client_id="cid",
                client_secret="csec",
                redirect_uri="http://127.0.0.1:1/callback",
            )


async def test_refresh_access_token_returns_access_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "fresh-at"})

    async with _mock_client(handler) as client:
        token = await refresh_access_token(
            client, refresh_token="rt", client_id="cid", client_secret="csec"
        )
    assert token == "fresh-at"


async def test_refresh_raises_clearly_when_token_is_dead() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with _mock_client(handler) as client:
        with pytest.raises(RuntimeError, match="invalid_grant"):
            await refresh_access_token(
                client, refresh_token="rt", client_id="cid", client_secret="csec"
            )


# ─── API probes ───────────────────────────────────────────────────────────────


async def test_gmail_probe_passes_and_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer at"
        assert request.url.params["maxResults"] == "1"
        return httpx.Response(200, json={"messages": [{"id": "m1"}]})

    async with _mock_client(handler) as client:
        result = await probe_gmail(client, "at")
    assert result.ok
    assert result.records == 1


async def test_calendar_probe_passes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["maxResults"] == "1"
        return httpx.Response(200, json={"items": [{"id": "e1"}]})

    async with _mock_client(handler) as client:
        result = await probe_calendar(client, "at")
    assert result.ok
    assert result.records == 1


async def test_meet_probe_passes_with_zero_records() -> None:
    """Reachable but empty is a PASS.

    Transcription availability is reported separately — conflating them would
    misreport a Phase 0.5 exit criterion.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["pageSize"] == "1"
        return httpx.Response(200, json={})

    async with _mock_client(handler) as client:
        result = await probe_meet(client, "at")
    assert result.ok
    assert result.records == 0


async def test_probe_reports_403_as_failure_with_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "insufficient scope"}})

    async with _mock_client(handler) as client:
        result = await probe_gmail(client, "at")
    assert not result.ok
    assert "insufficient scope" in result.detail


async def test_probe_survives_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    async with _mock_client(handler) as client:
        result = await probe_gmail(client, "at")
    assert not result.ok
    assert "ConnectError" in result.detail


async def test_run_probes_returns_all_three_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with _mock_client(handler) as client:
        results = await run_probes(client, "at")
    assert [r.api for r in results] == ["Gmail", "Calendar", "Meet"]


# ─── report rendering ─────────────────────────────────────────────────────────


def test_report_shows_pass_and_fail() -> None:
    report = render_report(
        [
            ProbeResult(api="Gmail", ok=True, detail="reachable", records=1),
            ProbeResult(api="Calendar", ok=False, detail="HTTP 403: denied"),
        ],
        _token(),
    )
    assert "PASS" in report
    assert "FAIL" in report
    assert "HTTP 403: denied" in report


def test_report_distinguishes_reachable_from_transcripts_present() -> None:
    report = render_report(
        [ProbeResult(api="Meet", ok=True, detail="reachable", records=0)], _token()
    )
    assert "PASS" in report
    assert "no conference records" in report.lower()


def test_report_states_issue_date_and_expiry() -> None:
    token = _token(age_days=2.0)
    report = render_report([], token)
    assert token.issued_at.date().isoformat() in report
    assert "5.0" in report  # 7 - 2 days remaining


def test_report_never_contains_the_token() -> None:
    """The single most important test in this file. docs/GOOGLE_AUTH.md §7."""
    token = _token(refresh_token="SUPER-SECRET-REFRESH-TOKEN")
    report = render_report(
        [ProbeResult(api="Gmail", ok=True, detail="reachable", records=1)], token
    )
    assert "SUPER-SECRET-REFRESH-TOKEN" not in report
    # Not even a fragment — no truncated prefixes either.
    assert "SUPER-SECRET" not in report
    assert "SUPER" not in report


# ─── CLI ──────────────────────────────────────────────────────────────────────


def test_credentials_come_from_env() -> None:
    credentials = load_client_credentials(
        {"GOOGLE_OAUTH_CLIENT_ID": "cid", "GOOGLE_OAUTH_CLIENT_SECRET": "csec"}
    )
    assert credentials == ("cid", "csec")


def test_missing_credentials_name_the_doc_section() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        load_client_credentials({})
    message = str(excinfo.value)
    assert "GOOGLE_OAUTH_CLIENT_ID" in message
    assert "GOOGLE_AUTH.md" in message


def test_blank_credentials_are_treated_as_missing() -> None:
    with pytest.raises(RuntimeError):
        load_client_credentials(
            {"GOOGLE_OAUTH_CLIENT_ID": "  ", "GOOGLE_OAUTH_CLIENT_SECRET": "csec"}
        )


def test_parser_supports_reconsent() -> None:
    assert build_parser().parse_args(["--reconsent"]).reconsent is True
    assert build_parser().parse_args([]).reconsent is False


# ─── .env loading ─────────────────────────────────────────────────────────────


def test_load_env_file_returns_false_when_absent(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "nope.env") is False


def test_load_env_file_populates_environ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_OAUTH_CLIENT_ID=from-file\n", encoding="utf-8")
    # setenv first so monkeypatch restores the pre-test state on teardown.
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "placeholder")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID")

    assert load_env_file(env_file) is True
    assert os.environ["GOOGLE_OAUTH_CLIENT_ID"] == "from-file"


def test_exported_env_beats_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """override=False, so `GOOGLE_OAUTH_CLIENT_ID=x make auth-spike` still wins."""
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_OAUTH_CLIENT_ID=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "from-shell")

    load_env_file(env_file)
    assert os.environ["GOOGLE_OAUTH_CLIENT_ID"] == "from-shell"
