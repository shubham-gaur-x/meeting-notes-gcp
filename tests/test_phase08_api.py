"""Phase 8 — the API. Every route is driven through the real ASGI app.

`MIGRATION_FROM_V5.md` #3 exists because v5's tests called handler functions
directly. A structlog `event=` collision inside a route was therefore never
exercised and reached production as a 500. Everything here goes through
`httpx.ASGITransport`.
"""

from __future__ import annotations

from meeting_notes import github_webhook
from meeting_notes.config import Settings

# ─── webhook signature ────────────────────────────────────────────────────────


def _local() -> Settings:
    return Settings(_env_file=None, GCP_PROJECT_ID="")


def _deployed() -> Settings:
    return Settings(_env_file=None, GCP_PROJECT_ID="some-project")


def test_a_valid_signature_verifies() -> None:
    body = b'{"action": "closed"}'
    assert github_webhook.verify_signature(
        body, github_webhook.sign(body, "s3cret"), "s3cret", settings=_local()
    )


def test_a_tampered_body_fails() -> None:
    header = github_webhook.sign(b'{"action": "closed"}', "s3cret")
    assert not github_webhook.verify_signature(
        b'{"action": "opened"}', header, "s3cret", settings=_local()
    )


def test_the_wrong_secret_fails() -> None:
    body = b"{}"
    assert not github_webhook.verify_signature(
        body, github_webhook.sign(body, "attacker"), "s3cret", settings=_local()
    )


def test_a_missing_header_fails_when_a_secret_is_configured() -> None:
    assert not github_webhook.verify_signature(b"{}", None, "s3cret", settings=_local())


def test_an_unset_secret_accepts_locally() -> None:
    """Convenience for local development, where there is nothing to forge."""
    assert github_webhook.verify_signature(b"{}", None, "", settings=_local())


def test_an_unset_secret_REJECTS_when_deployed() -> None:
    """v5 accepted any payload with no secret set. Deployed, that turns the
    endpoint into an unauthenticated write path into the graph."""
    assert not github_webhook.verify_signature(b"{}", None, "", settings=_deployed())


# ─── every route, through the real ASGI app ───────────────────────────────────

from typing import Any  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from api.main import create_app  # noqa: E402
from meeting_notes import graph_client  # noqa: E402

# Captured at import time, before the autouse stub fixture can replace it --
# the governance test below must exercise the REAL function, not the stub.
_REAL_INFLUENTIAL = graph_client.get_influential_nodes


@pytest.fixture
def app() -> Any:
    return create_app()


async def _get(app: Any, path: str, **kw: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, **kw)


async def _post(app: Any, path: str, **kw: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, **kw)


@pytest.fixture(autouse=True)
def stub_graph(monkeypatch: Any) -> None:
    """Replace every graph read with a shaped stub, so routes are driven for
    real while nothing touches Memgraph."""
    async def people(*a: Any, **k: Any) -> list[dict]:
        return [{"id": "p1", "name": "Alice", "pagerank_score": 0.9, "community_id": 1}]

    async def meetings(*a: Any, **k: Any) -> list[dict]:
        return [{"id": "m1", "title": "Sync", "date": "2026-08-20", "kind": "meeting",
                 "summary": "s", "platform": "email", "relevance_weight": 1.0}]

    async def one(*a: Any, **k: Any) -> dict:
        return {"id": "x1", "name": "thing"}

    async def empty(*a: Any, **k: Any) -> list[dict]:
        return []

    for name, fn in [
        ("get_recent_meetings", meetings), ("get_timeline", meetings),
        ("get_person_graph", one), ("get_topic_graph", one),
        ("get_open_actions", empty), ("get_actions_needing_review", empty),
        ("get_person_reviews", empty), ("get_open_blockers", empty),
        ("get_influential_nodes", people), ("get_all_communities", empty),
        ("get_community_members", empty), ("get_bridge_nodes", empty),
        ("get_node_insights", one), ("get_meeting_provenance", one),
        ("get_ticket_provenance", one),
    ]:
        monkeypatch.setattr(graph_client, name, fn)


async def test_health_reports_degraded_rather_than_failing(app: Any) -> None:
    """Cloud Run should keep the instance while a dependency is down, so the
    cause stays visible instead of the service disappearing."""
    response = await _get(app, "/health")
    assert response.status_code == 200
    assert response.json()["status"] in ("ok", "degraded")


@pytest.mark.parametrize(
    "path",
    [
        "/graph/meetings/recent",
        "/graph/timeline",
        "/graph/person/a@corp.com",
        "/graph/topic/budget",
        "/graph/actions/open",
        "/graph/provenance/m1",
        "/graph/provenance/by-ticket/SCRUM-1",
        "/review/actions",
        "/review/people",
        "/review/blockers",
        "/graph/insights/influential",
        "/graph/insights/communities",
        "/graph/insights/communities/1",
        "/graph/insights/bridges",
        "/graph/insights/node/x1",
    ],
)
async def test_every_read_route_responds(app: Any, path: str) -> None:
    """Drives the REAL ASGI app. v5's tests called handler functions directly,
    so a structlog `event=` collision inside a route was never exercised and
    reached production as a 500 (MIGRATION_FROM_V5.md #3)."""
    response = await _get(app, path)
    assert response.status_code == 200, f"{path} -> {response.status_code} {response.text[:200]}"


async def test_influential_defaults_to_person_so_the_gate_applies(app: Any, monkeypatch: Any) -> None:
    """The endpoint must reach graph_client with label=Person, which is what
    triggers the tracked gate inside it."""
    seen: dict[str, Any] = {}

    async def capture(label: str = "Person", limit: int = 10, driver: Any = None) -> list[dict]:
        seen["label"] = label
        return []

    monkeypatch.setattr(graph_client, "get_influential_nodes", capture)
    response = await _get(app, "/graph/insights/influential")

    assert response.status_code == 200
    assert seen["label"] == "Person"


async def test_untracked_people_are_excluded_from_the_leaderboard() -> None:
    """The governance promise itself, against the real function with a fake
    driver -- not a stub, since the stub is what the endpoint test replaces.

    Asserts the generated Cypher carries the gate for Person and omits it for
    other labels, which have no privacy interest.
    """
    captured: list[str] = []

    class _Result:
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    class _Session:
        async def run(self, cypher: str, **kw: Any) -> Any:
            captured.append(cypher)
            return _Result()
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _Driver:
        def session(self) -> Any: return _Session()

    await _REAL_INFLUENTIAL(label="Person", driver=_Driver())
    assert "tracked" in captured[0], "the Person leaderboard is not tracked-gated"

    captured.clear()
    await _REAL_INFLUENTIAL(label="Topic", driver=_Driver())
    assert "tracked" not in captured[0], "non-Person labels should not be gated"


async def test_the_dashboard_is_served(app: Any) -> None:
    response = await _get(app, "/dashboard")
    assert response.status_code == 200
    assert "<html" in response.text.lower()


async def test_github_webhook_rejects_a_bad_signature(app: Any, monkeypatch: Any) -> None:
    from meeting_notes import config

    monkeypatch.setattr(
        config, "get_settings",
        lambda: Settings(_env_file=None, GITHUB_WEBHOOK_SECRET="s3cret", GCP_PROJECT_ID="p"),
    )
    response = await _post(app, "/webhook/github", content=b"{}",
                           headers={"X-Hub-Signature-256": "sha256=wrong"})
    assert response.status_code == 401


async def test_github_webhook_accepts_a_valid_signature(app: Any, monkeypatch: Any) -> None:
    """Also proves the route's own structlog call runs -- the exact thing v5
    never exercised."""
    import api.routers.webhooks as wh

    body = b'{"action": "closed"}'
    monkeypatch.setattr(
        wh, "get_settings",
        lambda: Settings(_env_file=None, GITHUB_WEBHOOK_SECRET="s3cret", GCP_PROJECT_ID="p"),
    )
    response = await _post(
        app, "/webhook/github", content=body,
        headers={"X-Hub-Signature-256": github_webhook.sign(body, "s3cret"),
                 "X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 200
    assert response.json()["event"] == "pull_request"


async def test_jira_webhook_acknowledges(app: Any) -> None:
    response = await _post(app, "/webhook/jira", json={"webhookEvent": "jira:issue_updated"})
    assert response.status_code == 200
    assert response.json()["event"] == "jira:issue_updated"


async def test_malformed_webhook_json_is_a_400_not_a_500(app: Any) -> None:
    response = await _post(app, "/webhook/jira", content=b"not json")
    assert response.status_code == 400


# ─── structural guarantees ────────────────────────────────────────────────────


def test_the_api_contains_no_scheduler() -> None:
    """CLAUDE.md: scheduling is Cloud Scheduler triggering Cloud Run Jobs.
    v5's main.py carried 17 scheduler references."""
    import re
    from pathlib import Path

    import api

    # Match an actual import or instantiation, not the word -- api/main.py's
    # own docstring says "Zero APScheduler", and a bare substring check flags
    # the very comment documenting the rule. (Third time this trap has come up
    # in this project: guards must assert syntax, not prose.)
    uses = re.compile(
        r"^\s*(from\s+apscheduler|import\s+apscheduler)|BackgroundScheduler\s*\(|AsyncIOScheduler\s*\(",
        re.M | re.I,
    )
    offenders = [
        path.name for path in Path(api.__file__).parent.rglob("*.py")
        if uses.search(path.read_text())
    ]
    assert not offenders, f"scheduler used in: {offenders}"


def test_no_route_passes_event_to_structlog() -> None:
    """`event=` collides with structlog's reserved message field and raises
    TypeError at call time -- a real production 500 in v5."""
    import re
    from pathlib import Path

    import api

    bad = re.compile(r"log\.\w+\([^)]*[^_\w]event\s*=")
    offenders = [
        path.name for path in Path(api.__file__).parent.rglob("*.py")
        if bad.search(path.read_text())
    ]
    assert not offenders, f"structlog event= kwarg in: {offenders}"
