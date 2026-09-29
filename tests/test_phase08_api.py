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
_REAL_COMMUNITIES = graph_client.get_all_communities
_REAL_ALL_ACTIONS = graph_client.get_all_actions
_REAL_OPEN_ACTIONS = graph_client.get_open_actions


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


async def _delete(app: Any, path: str, **kw: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.delete(path, **kw)


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
        ("get_open_actions", empty), ("get_all_actions", empty),
        ("get_actions_needing_review", empty),
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
        "/graph/actions",
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
    from meeting_notes.config import Settings

    monkeypatch.setattr(
        "api.routers.webhooks.get_settings",
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


async def _github_post(app: Any, monkeypatch: Any, payload: dict) -> httpx.Response:
    import json as _json

    import api.routers.webhooks as wh

    body = _json.dumps(payload).encode()
    monkeypatch.setattr(
        wh, "get_settings",
        lambda: Settings(_env_file=None, GITHUB_WEBHOOK_SECRET="s3cret", GCP_PROJECT_ID="p"),
    )
    return await _post(
        app, "/webhook/github", content=body,
        headers={"X-Hub-Signature-256": github_webhook.sign(body, "s3cret"),
                 "X-GitHub-Event": "pull_request"},
    )


async def test_a_merged_pr_closes_its_agent_run(app: Any, monkeypatch: Any) -> None:
    """ADR-020: this is the ONE place dev_agent's CLOSED state is written."""
    import api.routers.webhooks as wh

    seen: dict[str, Any] = {}

    async def fake_close(pr_url: str, driver: Any = None) -> dict | None:
        seen["pr_url"] = pr_url
        return {"ticket_key": "SCRUM-1"}

    monkeypatch.setattr(wh, "close_agent_run_on_merge", fake_close)
    response = await _github_post(app, monkeypatch, {
        "action": "closed",
        "pull_request": {"merged": True, "html_url": "https://github.com/o/r/pull/9"},
    })

    assert response.status_code == 200
    assert seen["pr_url"] == "https://github.com/o/r/pull/9"


async def test_a_closed_but_unmerged_pr_does_not_close_any_agent_run(app: Any, monkeypatch: Any) -> None:
    import api.routers.webhooks as wh

    called = []
    monkeypatch.setattr(wh, "close_agent_run_on_merge", lambda *a, **k: called.append(1))
    response = await _github_post(app, monkeypatch, {
        "action": "closed",
        "pull_request": {"merged": False, "html_url": "https://github.com/o/r/pull/9"},
    })

    assert response.status_code == 200
    assert called == []


async def test_a_failed_agent_run_close_does_not_break_the_webhook_response(
    app: Any, monkeypatch: Any
) -> None:
    """Most merged PRs aren't the agent's, and a graph hiccup on the ones that
    are must never turn GitHub's webhook into a retry storm."""
    import api.routers.webhooks as wh

    async def boom(pr_url: str, driver: Any = None) -> dict | None:
        raise RuntimeError("memgraph unavailable")

    monkeypatch.setattr(wh, "close_agent_run_on_merge", boom)
    response = await _github_post(app, monkeypatch, {
        "action": "closed",
        "pull_request": {"merged": True, "html_url": "https://github.com/o/r/pull/9"},
    })

    assert response.status_code == 200


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
        if uses.search(path.read_text(encoding="utf-8"))
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
        if bad.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"structlog event= kwarg in: {offenders}"


# ─── digest ───────────────────────────────────────────────────────────────────

from meeting_notes import digest  # noqa: E402


def test_digest_splits_actions_by_state() -> None:
    """Open vs closed vs high-priority is the whole point of the rollup."""
    result = digest.shape({
        "meetings": [{"id": "m1"}],
        "decisions": [{"id": "d1"}],
        "action_items": [
            {"id": "a1", "done": False, "priority": "high"},
            {"id": "a2", "done": False, "priority": "low"},
            {"id": "a3", "done": True, "priority": "high"},
        ],
    })
    s = result["summary"]
    assert s["total_meetings"] == 1
    assert s["total_action_items"] == 3
    assert s["open_action_items"] == 2
    assert s["closed_action_items"] == 1
    assert s["high_priority_open"] == 1, "a DONE high-priority item is not outstanding work"


def test_digest_handles_an_empty_period() -> None:
    """A quiet week must render zeros, not crash the dashboard's first tab."""
    result = digest.shape({})
    assert result["summary"]["total_meetings"] == 0
    assert result["action_items"]["open"] == []


async def test_digest_endpoint_responds(app: Any) -> None:
    async def fake_activity(
        days: int = 7, driver: Any = None, start: str | None = None, end: str | None = None
    ) -> dict:
        return {"meetings": [], "decisions": [], "action_items": []}

    import meeting_notes.graph_client as gc

    original = gc.get_period_activity
    gc.get_period_activity = fake_activity  # type: ignore[assignment]
    try:
        response = await _get(app, "/graph/digest/weekly")
    finally:
        gc.get_period_activity = original  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.json()["period"] == "last_7_days"


# ─── dashboard ────────────────────────────────────────────────────────────────


def test_the_dashboard_is_a_single_file_with_no_build_step() -> None:
    """CLAUDE.md: keep it single-file, no build step. No bundler, no CDN."""
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "<script" in html and "</script>" in html
    assert "src=" not in html.split("<script")[1][:200], "no external script tags"
    assert "cdn." not in html and "unpkg" not in html


def test_the_dashboard_calls_only_routes_that_exist(app: Any) -> None:
    """A dashboard fetching a route that 404s renders an empty tab, which
    looks like a data problem rather than the wiring problem it is.

    Uses the OpenAPI schema as the route list: FastAPI keeps included routers
    nested rather than flattening them into app.routes, so walking .routes
    finds only the six top-level ones.
    """
    import re
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    called = {m for m in re.findall(r'(?:get|fetch)\("(/[a-z0-9/_-]+)', html)}
    known = set(app.openapi()["paths"])

    assert called, "no fetches found in the dashboard -- the regex is wrong"

    # A path the dashboard builds by concatenation ("/graph/meeting/" + id)
    # is a prefix of a parameterised route ("/graph/meeting/{meeting_id}").
    prefixes = {p.split("{")[0] for p in known if "{" in p}

    for path in sorted(called):
        ok = path in known or path in prefixes or any(
            path.startswith(pre) for pre in prefixes
        )
        assert ok, f"dashboard calls {path}, which no route serves"


def test_every_tab_has_a_panel_and_a_loader() -> None:
    """Reorganised during the UX audit around what a user actually asks:
    what happened (overview), what was decided and by whom (meetings),
    what do I owe (action items), what is this project (workstreams),
    anything else (ask), and what needs me (review)."""
    import re
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    tabs = set(re.findall(r'data-panel="([a-z]+)"', html))

    assert tabs == {"overview", "meetings", "actions", "workstreams", "graph", "ask", "review"}
    for panel in tabs:
        assert f'id="{panel}"' in html, f"tab {panel} has no panel"
        assert f"{panel}:" in html, f"tab {panel} has no entry in LOADERS"


async def test_the_service_root_redirects_to_the_dashboard(app: Any) -> None:
    """Found by reading the browser console, not the tests: nothing requested
    `/`, so the deployed service's front door 404'd."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/dashboard"


# ─── insight readability (from the live audit) ────────────────────────────────

def _fake_driver_returning(rows: list[dict]) -> Any:
    """Minimal async driver returning fixed rows, for exercising the REAL
    graph_client functions rather than the autouse stubs."""
    class _Result:
        def __init__(self) -> None:
            self._rows = list(rows)

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> dict:
            if not self._rows:
                raise StopAsyncIteration
            return self._rows.pop(0)

    class _Session:
        async def run(self, cypher: str, **kw: Any) -> Any:
            return _Result()

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    class _Driver:
        def session(self) -> Any:
            return _Session()

    return _Driver()




async def test_communities_are_named_not_just_numbered() -> None:
    """"Community 1, size 63" tells a reader nothing. Named by its top topics
    it reads as a recognisable workstream, which is the difference between an
    insight and a number."""
    rows_out = [{"community_id": 1, "size": 63,
                 "top_topics": ["verizon ge enablement", "sow review"]}]
    driver = _fake_driver_returning(rows_out)

    rows = await _REAL_COMMUNITIES(driver=driver)
    assert rows[0]["name"] == "verizon ge enablement · sow review"
    assert rows[0]["community_id"] == 1, "the id is kept for drill-down"


async def test_a_community_with_no_topics_still_gets_a_label() -> None:
    """Never render a blank cell."""
    driver = _fake_driver_returning([{"community_id": 7, "size": 3, "top_topics": []}])

    rows = await _REAL_COMMUNITIES(driver=driver)
    assert rows[0]["name"] == "community 7"


def test_bookkeeping_nodes_are_excluded_from_insights() -> None:
    """PersonReview and MemorySession are records of how the system worked,
    not things anyone discussed. On the real graph they were forming their own
    junk communities and appearing beside real topics."""
    # Read the module source rather than the live attributes: the autouse
    # fixture replaces those with stubs, so inspecting them checks nothing.
    from pathlib import Path

    source = Path(graph_client.__file__).read_text(encoding="utf-8")
    for name in ("get_all_communities", "get_bridge_nodes", "get_community_members"):
        start = source.index(f"async def {name}(")
        body = source[start : start + 1400]
        assert "bookkeeping" in body, f"{name} does not exclude bookkeeping nodes"


def test_the_empty_leaderboard_explains_itself() -> None:
    """"Most connected Person (0)" with a bare "Nothing here yet" reads as
    broken, when it is actually the governance gate working. The empty state
    must say WHY it is empty."""
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "opt-in by design" in html
    assert "tracked" in html


# ─── UX audit: does the dashboard answer a user's questions? ──────────────────


async def test_meeting_detail_does_not_cartesian_product(app: Any) -> None:
    """Regression test for a real corruption. Collecting six unrelated
    one-to-many relationships in ONE MATCH cross-products them: measured on a
    real meeting, 3 attendees x 6 topics x 3 decisions x 9 reviews x 4 facts
    reported 29,160 action items instead of 15."""
    calls: list[str] = []

    class _Result:
        def __init__(self, rows): self._rows = list(rows)
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._rows:
                raise StopAsyncIteration
            return self._rows.pop(0)

    class _Session:
        async def run(self, cypher: str, **kw: Any) -> Any:
            calls.append(cypher)
            if "RETURN m.id AS id" in cypher:
                return _Result([{"id": "m1", "title": "T", "date": "2026-08-20",
                                 "kind": "meeting", "platform": "email",
                                 "summary": "s", "duration_minutes": 30}])
            if "FOLLOWS_UP" in cypher:
                return _Result([{"id": "a1", "task": "do it", "owner": "A", "due": None,
                                 "done": False, "priority": "high", "jira_key": None,
                                 "owner_email": None}])
            return _Result([])
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _Driver:
        def session(self): return _Session()

    detail = await graph_client.get_meeting_detail("m1", driver=_Driver())

    assert len(detail["action_items"]) == 1
    assert len(calls) >= 6, "each collection must be its own query, not one joined MATCH"


async def test_meeting_detail_returns_empty_for_an_unknown_meeting() -> None:
    class _Empty:
        def session(self): return self
        async def run(self, *a, **k):
            class _R:
                def __aiter__(self): return self
                async def __anext__(self): raise StopAsyncIteration
            return _R()
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    assert await graph_client.get_meeting_detail("nope", driver=_Empty()) == {}


def test_the_dashboard_surfaces_decisions_and_action_items() -> None:
    """The UX failure this audit found: 6 decisions and 28 open actions were
    extracted and stored, and the dashboard showed neither. It listed meeting
    titles, an admin review queue, graph clusters and a chat box -- none of
    which answer "what was decided" or "what do I need to do"."""
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "/graph/decisions" in html, "decisions are never fetched"
    assert "/graph/actions" in html, "action items are never fetched"
    assert "/graph/meeting/" in html, "no per-meeting drill-down"


def test_the_dashboard_offers_example_questions() -> None:
    """A bare text box gives a first-time user nothing to start from."""
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert ("EXAMPLES" in html or "DEFAULT_COMMON_QUERIES" in html) and "prompt-card" in html


# ─── dev agent ─────────────────────────────────────────────────────────────


async def test_dev_agent_preflight_reports_ok(app: Any, monkeypatch: Any) -> None:
    import api.routers.dev_agent as da

    async def ok_preflight(backend: str, settings: Any = None) -> str:
        return "gemini project=p location=global model=gemini-3-pro-preview"

    monkeypatch.setattr(da.backend, "select_backend", lambda settings: "gemini")
    monkeypatch.setattr(da.backend, "preflight", ok_preflight)

    response = await _get(app, "/dev-agent/preflight")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "backend": "gemini",
        "ok": True,
        "detail": "gemini project=p location=global model=gemini-3-pro-preview",
    }


async def test_dev_agent_preflight_reports_failure_without_raising(app: Any, monkeypatch: Any) -> None:
    """A down backend is data for the dashboard, not a 500."""
    import api.routers.dev_agent as da

    async def bad_preflight(backend: str, settings: Any = None) -> str:
        raise da.backend.PreflightError("GCP_PROJECT_ID is not set")

    monkeypatch.setattr(da.backend, "select_backend", lambda settings: "gemini")
    monkeypatch.setattr(da.backend, "preflight", bad_preflight)

    response = await _get(app, "/dev-agent/preflight")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "GCP_PROJECT_ID" in body["detail"]


async def test_dev_agent_runs_lists_recent_runs(app: Any, monkeypatch: Any) -> None:
    import api.routers.dev_agent as da
    from meeting_notes.dev_agent.models import DevAgentRun

    async def fake_list(limit: int = 50, pool: Any = None) -> list[DevAgentRun]:
        return [DevAgentRun(ticket_key="SCRUM-1", state="SHIPPED", attempt_count=1)]

    monkeypatch.setattr(da.db, "list_recent_dev_agent_runs", fake_list)

    response = await _get(app, "/dev-agent/runs")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["runs"][0]["ticket_key"] == "SCRUM-1"
    assert body["runs"][0]["state"] == "SHIPPED"


async def test_dev_agent_trigger_kicks_off_a_poll_cycle(app: Any, monkeypatch: Any) -> None:
    """As a BackgroundTasks entry, not an awaited call -- a coding run can take
    far longer than an HTTP request should wait on a real deployed server."""
    import inspect

    import api.routers.dev_agent as da

    called = []

    async def fake_poll(*a: Any, **k: Any) -> dict[str, Any]:
        called.append(1)
        return {"attempted": 0}

    monkeypatch.setattr(da, "poll_and_process", fake_poll)

    response = await _post(app, "/dev-agent/trigger")

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert called == [1]

    source = inspect.getsource(da.trigger)
    assert "background_tasks.add_task" in source, "must not await poll_and_process inline"


async def test_quality_ranked_endpoint_returns_scored_meetings(app: Any, monkeypatch: Any) -> None:
    """The nightly step writes `quality_score`; without a read path the scores
    are computed and invisible -- the same shape as decisions being extracted
    with nowhere to see them."""
    import api.routers.graph as g

    async def fake_ranked(limit=20, driver=None):
        return [{"id": "m1", "title": "Kickoff", "date": "2026-05-13", "quality_score": 0.75}]

    monkeypatch.setattr(g.graph_client, "get_meetings_quality_ranked", fake_ranked)
    response = await _get(app, "/graph/meetings/quality")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["meetings"][0]["quality_score"] == 0.75


def test_the_overview_does_not_claim_a_period_it_does_not_filter_on() -> None:
    """The counters come from /graph/digest/weekly (7-day scoped); the decisions
    list comes from /graph/decisions (latest N, any date).

    Both sat under one "Everything from the last 7 days" banner, so the panel
    read "3 DECISIONS" with six decisions listed directly beneath it, two of
    them older than the window. The empty state said "in this period" for a
    list that was never filtered by period.
    """
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "Everything from the last 7 days" not in html, (
        "a blanket period label over unscoped content"
    )
    assert "Counters below cover ${range.label}" in html, (
        "the counter label must name the range actually queried"
    )
    assert "regardless of the range above" in html, (
        "the decisions list must say it is not scoped to the selected range"
    )
    assert "not limited to the 7 days above" not in html, (
        "a fixed window in the copy contradicts a selectable range"
    )
    assert "in this period" not in html, "the empty state claimed a filter that is not applied"


# ─── selectable time range on the overview ────────────────────────────────────


async def test_digest_accepts_an_explicit_date_range(app: Any, monkeypatch: Any) -> None:
    """A preset in days cannot express "that quarter" or "since the kickoff",
    so the endpoint takes an explicit start/end as well."""
    import api.routers.graph as g

    seen: dict = {}

    async def fake_activity(days=7, start=None, end=None, driver=None):
        seen.update({"days": days, "start": start, "end": end})
        return {"meetings": [], "decisions": [], "action_items": []}

    monkeypatch.setattr(g.graph_client, "get_period_activity", fake_activity)
    response = await _get(app, "/graph/digest/weekly?start=2026-01-01&end=2026-03-31")

    assert response.status_code == 200
    assert seen["start"] == "2026-01-01" and seen["end"] == "2026-03-31"
    assert response.json()["period"] == "2026-01-01..2026-03-31"


async def test_digest_rejects_a_backwards_range(app: Any) -> None:
    """An end before the start returns nothing at all, which reads as "quiet
    period" rather than "you typed it backwards"."""
    response = await _get(app, "/graph/digest/weekly?start=2026-03-31&end=2026-01-01")
    assert response.status_code == 422


async def test_a_year_long_window_is_allowed(app: Any, monkeypatch: Any) -> None:
    """The old cap was 90 days, so "past year" could not be asked for."""
    import api.routers.graph as g

    async def fake_activity(days=7, start=None, end=None, driver=None):
        return {"meetings": [], "decisions": [], "action_items": []}

    monkeypatch.setattr(g.graph_client, "get_period_activity", fake_activity)
    assert (await _get(app, "/graph/digest/weekly?days=365")).status_code == 200


def test_the_overview_offers_a_range_selector() -> None:
    """The counters are period-scoped and the corpus spans years, so a quiet
    week made a 96-meeting graph read as "2 MEETINGS"."""
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="range"' in html, "no range selector"
    for label in ("Past week", "Past month", "Past year", "All time", "Custom"):
        assert label in html, f"missing range option: {label}"


def test_switching_to_a_custom_range_does_not_leave_a_stale_label() -> None:
    """Choosing "Custom" waits for both dates before querying, so the previous
    range's label would otherwise sit above numbers it no longer describes."""
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    start = html.index("function onRangeChange()")
    body = html[start : start + 700]
    assert "Pick both dates." in body, (
        "switching to custom must replace the label immediately"
    )


# ─── the graph itself, visible ────────────────────────────────────────────────


async def test_graph_snapshot_endpoint_returns_nodes_and_edges(app: Any, monkeypatch: Any) -> None:
    import api.routers.graph as g

    async def fake_snapshot(limit=150, labels=None, driver=None):
        return {
            "nodes": [{"id": "m1", "label": "Kickoff", "type": "Meeting", "score": 0.4},
                      {"id": "t1", "label": "sow review", "type": "Topic", "score": 0.2}],
            "edges": [{"source": "m1", "target": "t1", "type": "DISCUSSED"}],
        }

    monkeypatch.setattr(g.graph_client, "get_graph_snapshot", fake_snapshot)
    response = await _get(app, "/graph/visualize")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["nodes"][0]["type"] == "Meeting"
    assert body["edges"][0]["type"] == "DISCUSSED"


def test_the_graph_view_honours_the_tracked_gate() -> None:
    """A graph view names individuals by construction -- it draws them as
    nodes. Same rule as PageRank and centrality: naming a person is opt-in."""
    from pathlib import Path

    source = Path("meeting_notes/graph_client.py").read_text(encoding="utf-8")
    start = source.index("async def get_graph_snapshot(")
    assert "_UNTRACKED_PERSON_EXCLUDED" in source[start : start + 1800], (
        "the graph view must reuse the same tracked predicate as the other "
        "per-person surfaces"
    )


async def test_the_snapshot_is_bounded(app: Any, monkeypatch: Any) -> None:
    """597 nodes and thousands of edges is neither readable nor fast. The
    endpoint caps what it will draw."""
    import api.routers.graph as g

    seen: dict = {}

    async def fake_snapshot(limit=150, labels=None, driver=None):
        seen["limit"] = limit
        return {"nodes": [], "edges": []}

    monkeypatch.setattr(g.graph_client, "get_graph_snapshot", fake_snapshot)
    await _get(app, "/graph/visualize")
    assert seen["limit"] <= 400, "an unbounded snapshot would hang the browser"
    assert (await _get(app, "/graph/visualize?limit=99999")).status_code == 422


def test_the_dashboard_has_a_graph_tab() -> None:
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert 'data-panel="graph"' in html
    assert "loadGraph" in html
    # No CDN: the renderer has to be inline, like everything else here.
    assert "cdn." not in html and "unpkg" not in html


async def test_suggested_questions_endpoint(app: Any, monkeypatch: Any) -> None:
    from meeting_notes.memory import retrieval

    async def fake_suggested(*args, **kwargs):
        return [
            {"category": "🎯 Project Action", "question": "What is the status of the PSA skill update?"},
            {"category": "⏰ Upcoming Deadline", "question": "What deliverables are due this week?"},
        ]

    monkeypatch.setattr(retrieval, "generate_suggested_questions", fake_suggested)
    response = await _get(app, "/graph/memory/suggested-questions")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert len(body["questions"]) == 2
    assert body["questions"][0]["category"] == "🎯 Project Action"


async def test_jira_webhook_accepts_issue_update(app: Any, monkeypatch: Any) -> None:
    import api.routers.webhooks as wh

    seen: list[str] = []

    async def fake_refresh(key: str) -> None:
        seen.append(key)

    monkeypatch.setattr(wh, "_refresh_issue_from_jira", fake_refresh)
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {"key": "MDP-25", "fields": {"status": {"name": "Done"}}},
    }
    response = await _post(app, "/webhook/jira", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["key"] == "MDP-25"
    assert seen == ["MDP-25"], "the webhook must schedule an authenticated re-read"


def _sync_settings(app: Any, *, token: str, project: str) -> None:
    """Override the route's settings dependency, keyed on `settings_dep` itself.

    No module attribute is rebound, so this cannot be defeated by how the route
    happens to import its settings. The `app` fixture builds a fresh app per
    test, so the override dies with it.
    """
    from api.deps import settings_dep
    from meeting_notes.config import get_settings

    real = get_settings()
    fake = real.model_copy(
        update={"jira_sync_trigger_token": token, "gcp_project_id": project}
    )
    app.dependency_overrides[settings_dep] = lambda: fake


async def test_jira_sync_endpoint(app: Any, monkeypatch: Any) -> None:
    from meeting_notes import jira_sync

    async def fake_sync(*args, **kwargs):
        return {"total": 5, "synced": 5, "completed": 2}

    monkeypatch.setattr(jira_sync, "sync_open_jira_tickets", fake_sync)
    _sync_settings(app, token="s3cret", project="proj")
    response = await _post(
        app, "/webhook/jira/sync", json={}, headers={"X-Sync-Token": "s3cret"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["total"] == 5
    assert body["completed"] == 2


async def test_jira_sync_rejects_a_bad_token(app: Any, monkeypatch: Any) -> None:
    from meeting_notes import jira_sync

    async def boom(*args, **kwargs):
        raise AssertionError("a rejected sync must not reach Jira")

    monkeypatch.setattr(jira_sync, "sync_open_jira_tickets", boom)
    _sync_settings(app, token="s3cret", project="proj")
    response = await _post(
        app, "/webhook/jira/sync", json={}, headers={"X-Sync-Token": "wrong"}
    )
    assert response.status_code == 401


async def test_jira_sync_refuses_when_deployed_without_a_token(
    app: Any, monkeypatch: Any
) -> None:
    """An unconfigured token in a deployed project fails loudly, never openly."""
    from meeting_notes import jira_sync

    async def boom(*args, **kwargs):
        raise AssertionError("an unguarded sync must not reach Jira")

    monkeypatch.setattr(jira_sync, "sync_open_jira_tickets", boom)
    _sync_settings(app, token="", project="proj")
    response = await _post(app, "/webhook/jira/sync", json={})
    assert response.status_code == 503


# ─── Jira write operations ────────────────────────────────────────────────────
# These are the routes the mega-PR hung off `/webhook/jira/*`, where nothing
# resolves a principal. On that surface the body IS the instruction, so anyone
# able to reach the service could close any ticket or open an issue in any
# project. They live under `/jira/*` behind `principal` instead.


def test_no_jira_write_route_is_mounted_on_the_public_webhook_surface() -> None:
    """The webhook prefix is the unauthenticated one; keep writes off it.

    Read off the OpenAPI schema rather than `app.routes`, which FastAPI wraps
    per `include_router` call and is not a flat list of routes.
    """
    paths = {p for p in create_app().openapi()["paths"] if p.startswith("/webhook")}
    assert paths == {"/webhook/github", "/webhook/jira", "/webhook/jira/sync", "/webhook/linear"}, (
        f"unexpected route on the unauthenticated webhook surface: {paths}"
    )


def test_every_jira_write_route_resolves_a_principal() -> None:
    """A route added later without the dependency is the failure this catches.

    Asserted against the router itself, which is the thing a contributor edits.
    """
    from api.deps import principal as principal_dep
    from api.routers import jira_ops

    assert len(jira_ops.router.routes) == 4
    for route in jira_ops.router.routes:
        deps = [d.call for d in route.dependant.dependencies]  # type: ignore[attr-defined]
        assert principal_dep in deps, f"{route.path} is an unauthenticated Jira write"  # type: ignore[attr-defined]


async def test_a_transition_writes_the_new_status_into_the_graph(
    app: Any, monkeypatch: Any
) -> None:
    from meeting_notes import graph_client as gc
    from meeting_notes import jira_client

    written: list[tuple] = []

    async def fake_transition(key: str, status_name: str, **kw: Any) -> bool:
        return True

    async def fake_update(key: str, status: str, done: bool, **kw: Any) -> bool:
        written.append((key, status, done))
        return True

    monkeypatch.setattr(jira_client, "transition_issue", fake_transition)
    monkeypatch.setattr(gc, "update_action_jira_status", fake_update)

    response = await _post(app, "/jira/transition", json={"key": "MDP-25", "status": "Done"})
    assert response.status_code == 200
    assert response.json()["transitioned"] is True
    assert written == [("MDP-25", "Done", True)]


async def test_a_refused_transition_leaves_the_graph_alone(
    app: Any, monkeypatch: Any
) -> None:
    """Writing optimistically shows a done item that is still open in Jira,
    and the next sync silently undoes it."""
    from meeting_notes import graph_client as gc
    from meeting_notes import jira_client

    async def fake_transition(key: str, status_name: str, **kw: Any) -> bool:
        return False

    async def boom(*a: Any, **k: Any) -> bool:
        raise AssertionError("a refused transition must not reach the graph")

    monkeypatch.setattr(jira_client, "transition_issue", fake_transition)
    monkeypatch.setattr(gc, "update_action_jira_status", boom)

    response = await _post(app, "/jira/transition", json={"key": "MDP-25", "status": "Done"})
    assert response.status_code == 200
    assert response.json()["transitioned"] is False


async def test_a_transition_needs_both_a_key_and_a_status(app: Any) -> None:
    assert (await _post(app, "/jira/transition", json={"key": "MDP-1"})).status_code == 422
    assert (await _post(app, "/jira/transition", json={"key": "", "status": "Done"})).status_code == 422


async def test_a_subtask_mirrors_the_parent_edge_in_the_graph(
    app: Any, monkeypatch: Any
) -> None:
    """Without this the Jira hierarchy exists and the graph one does not, so
    the PARENT_OF read is permanently empty."""
    from meeting_notes import graph_client as gc
    from meeting_notes import jira_client

    keyed: list[tuple] = []
    linked: list[tuple] = []

    async def fake_subtask(parent_key: str, summary: str, description: str = "", **kw: Any) -> str:
        return "MDP-31"

    async def fake_key(action_id: str, jira_key: str, **kw: Any) -> None:
        keyed.append((action_id, jira_key))

    async def fake_link(parent_jira_key: str, child_action_id: str, **kw: Any) -> bool:
        linked.append((parent_jira_key, child_action_id))
        return True

    monkeypatch.setattr(jira_client, "create_subtask", fake_subtask)
    monkeypatch.setattr(gc, "update_action_jira_key", fake_key)
    monkeypatch.setattr(gc, "link_action_parent", fake_link)

    response = await _post(
        app, "/jira/subtask",
        json={"parent_key": "MDP-3", "summary": "write the runbook", "child_action_id": "a-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subtask_key"] == "MDP-31"
    assert body["graph_linked"] is True
    assert keyed == [("a-1", "MDP-31")]
    assert linked == [("MDP-3", "a-1")]


async def test_a_subtask_without_a_child_action_touches_no_graph_node(
    app: Any, monkeypatch: Any
) -> None:
    from meeting_notes import graph_client as gc
    from meeting_notes import jira_client

    async def fake_subtask(parent_key: str, summary: str, description: str = "", **kw: Any) -> str:
        return "MDP-31"

    async def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("no ActionItem was named, so nothing should be written")

    monkeypatch.setattr(jira_client, "create_subtask", fake_subtask)
    monkeypatch.setattr(gc, "update_action_jira_key", boom)
    monkeypatch.setattr(gc, "link_action_parent", boom)

    response = await _post(
        app, "/jira/subtask", json={"parent_key": "MDP-3", "summary": "write the runbook"}
    )
    assert response.status_code == 200
    assert response.json()["graph_linked"] is False


async def test_linking_two_issues_reports_a_refusal(app: Any, monkeypatch: Any) -> None:
    from meeting_notes import jira_client

    async def fake_link(inward: str, outward: str, **kw: Any) -> bool:
        return False

    monkeypatch.setattr(jira_client, "link_issues", fake_link)
    response = await _post(
        app, "/jira/link", json={"inward_key": "MDP-1", "outward_key": "SCRUM-2"}
    )
    assert response.status_code == 200
    assert response.json()["linked"] is False


async def test_a_comment_reports_the_created_comment_id(app: Any, monkeypatch: Any) -> None:
    from meeting_notes import jira_client

    async def fake_comment(key: str, text: str, **kw: Any) -> dict[str, Any]:
        return {"id": "10101"}

    monkeypatch.setattr(jira_client, "add_comment", fake_comment)
    response = await _post(app, "/jira/comment", json={"key": "MDP-1", "comment": "hi"})
    assert response.status_code == 200
    assert response.json()["comment_id"] == "10101"


# ─── the action item hierarchy read ───────────────────────────────────────────


async def test_the_actions_route_publishes_the_jira_domain_from_settings(
    app: Any,
) -> None:
    """The dashboard links tickets with this. A literal Atlassian domain in the
    page is what stops this repo moving to the Onix project (CLAUDE.md)."""
    from api.deps import settings_dep
    from meeting_notes.config import get_settings

    app.dependency_overrides[settings_dep] = lambda: get_settings().model_copy(
        update={"jira_domain": "tenant.atlassian.net"}
    )
    body = (await _get(app, "/graph/actions")).json()
    assert body["jira_browse_base"] == "https://tenant.atlassian.net/browse/"


async def test_the_actions_route_publishes_no_base_without_a_domain(app: Any) -> None:
    """Blank rather than a broken `https:///browse/` the page would still link."""
    from api.deps import settings_dep
    from meeting_notes.config import get_settings

    app.dependency_overrides[settings_dep] = lambda: get_settings().model_copy(
        update={"jira_domain": ""}
    )
    assert (await _get(app, "/graph/actions")).json()["jira_browse_base"] == ""


def test_the_dashboard_hardcodes_no_tenant() -> None:
    """A project id, region or account email in source is a portability defect
    (CLAUDE.md), and the dashboard is source like anything else."""
    from pathlib import Path

    import api.main as api_main

    page = (Path(api_main.__file__).parent / "static" / "dashboard.html").read_text(
        encoding="utf-8"
    )
    assert "atlassian.net" not in page, "the Jira tenant must come from the API"


async def test_the_actions_route_rejects_an_unknown_status(app: Any) -> None:
    """`status` reaches a spliced Cypher clause, so the pattern is the gate."""
    response = await _get(app, "/graph/actions?status=; MATCH (n) DETACH DELETE n")
    assert response.status_code == 422


class _CapturingDriver:
    """Records the Cypher a real graph_client function generates."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.cypher: list[str] = []
        self._rows = rows or []

    def session(self) -> Any:
        outer = self

        class _Result:
            def __init__(self) -> None:
                self._it = iter(outer._rows)

            def __aiter__(self) -> Any:
                return self

            async def __anext__(self) -> Any:
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration from None

        class _Session:
            async def run(self, cypher: str, **kw: Any) -> Any:
                outer.cypher.append(cypher)
                return _Result()

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *e: Any) -> bool:
                return False

        return _Session()


@pytest.mark.parametrize(
    ("status_filter", "expected"),
    [("all", None), ("open", "= false"), ("done", "= true")],
)
async def test_get_all_actions_filters_on_done(status_filter: str, expected: str | None) -> None:
    driver = _CapturingDriver()
    await _REAL_ALL_ACTIONS(status_filter=status_filter, driver=driver)
    cypher = driver.cypher[0]
    assert "PARENT_OF" in cypher, "the hierarchy read is the point of this function"
    if expected is None:
        assert "coalesce(a.done, false) =" not in cypher
    else:
        assert f"coalesce(a.done, false) {expected}" in cypher


async def test_get_all_actions_rejects_an_unknown_filter() -> None:
    """The second, independent check: the clause is spliced, not parameterised."""
    with pytest.raises(ValueError, match="unknown action status filter"):
        await _REAL_ALL_ACTIONS(status_filter="; DETACH DELETE n")


async def test_get_open_actions_is_the_undone_slice_of_get_all_actions(
    monkeypatch: Any,
) -> None:
    """One Cypher query for both, so the two cannot drift apart."""
    monkeypatch.setattr(graph_client, "get_all_actions", _REAL_ALL_ACTIONS)
    driver = _CapturingDriver()
    await _REAL_OPEN_ACTIONS(limit=7, driver=driver)
    assert "coalesce(a.done, false) = false" in driver.cypher[0]


# ─── the auth dependency fails closed when deployed (issue #39) ───────────────
#
# `principal()` returned LOCAL_PRINCIPAL -- role="admin", every scope -- whenever
# ACCESS_POLICY_FILE was unset. That keeps tier 0 runnable, and it did the same
# thing in a deployed service, where the surface includes POST /jira/* (mutates a
# real Jira project) and POST /dev_agent/trigger (starts a coding agent).
# ACCESS_POLICY_FILE appears nowhere in .env.example or terraform, so unset was
# the deployed default.


def _cloud_run(**kw: Any) -> Settings:
    """Settings as Cloud Run injects them: K_SERVICE set, no policy file."""
    return Settings(_env_file=None, K_SERVICE="meeting-notes-api", **kw)


async def test_principal_fails_closed_when_deployed_without_a_policy_file(
    app: Any, monkeypatch: Any
) -> None:
    """503, not an admin principal. Loud and unusable beats quietly open."""
    monkeypatch.setattr("api.deps.get_settings", _cloud_run)
    response = await _get(app, "/graph/meetings/recent")
    assert response.status_code == 503
    assert "ACCESS_POLICY_FILE" in response.json()["detail"]


async def test_principal_stays_open_locally_without_a_policy_file(
    app: Any, monkeypatch: Any
) -> None:
    """Tier 0 and local development are unaffected -- that is the whole point of
    keying on K_SERVICE rather than on gcp_project_id, which a tier-2 local run
    legitimately sets so Vertex works."""
    monkeypatch.setattr(
        "api.deps.get_settings",
        lambda: Settings(_env_file=None, GCP_PROJECT_ID="a-real-project"),
    )
    response = await _get(app, "/graph/meetings/recent")
    assert response.status_code == 200


async def test_a_configured_policy_file_is_still_enforced(
    app: Any, monkeypatch: Any
) -> None:
    """The existing behaviour must not regress: with a policy file, a caller
    without a bearer token is rejected rather than allowed."""
    monkeypatch.setattr(
        "api.deps.get_settings",
        lambda: _cloud_run(ACCESS_POLICY_FILE="/tmp/policy.yaml"),
    )
    response = await _get(app, "/graph/meetings/recent")
    assert response.status_code == 401


async def test_resolve_person_review_endpoint(app: Any, monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    async def mock_resolve(
        review_id: str, name: str, email: str | None = None, driver: Any = None
    ) -> dict[str, Any]:
        captured.update({"review_id": review_id, "name": name, "email": email})
        return {"name": name, "email": email or "", "meeting_id": "m1"}

    monkeypatch.setattr(graph_client, "resolve_person_review", mock_resolve)
    resp = await _post(
        app,
        "/review/people/rev-123/resolve",
        json={"name": "Alice Smith", "email": "alice@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["person"]["name"] == "Alice Smith"
    assert captured["review_id"] == "rev-123"
    assert captured["name"] == "Alice Smith"
    assert captured["email"] == "alice@example.com"


async def test_delete_person_review_endpoint(app: Any, monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    async def mock_delete(review_id: str, delete_actions: bool = True, driver: Any = None) -> bool:
        captured.update({"review_id": review_id, "delete_actions": delete_actions})
        return True

    monkeypatch.setattr(graph_client, "delete_person_review", mock_delete)
    resp = await _delete(app, "/review/people/rev-123?delete_actions=true")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "deleted": True}
    assert captured["review_id"] == "rev-123"
    assert captured["delete_actions"] is True


async def test_add_meeting_attendee_endpoint(app: Any, monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    async def mock_add(meeting_id: str, name: str, email: str, driver: Any = None) -> dict[str, Any]:
        captured.update({"meeting_id": meeting_id, "name": name, "email": email})
        return {"name": name, "email": email, "meeting_id": meeting_id}

    monkeypatch.setattr(graph_client, "add_meeting_attendee", mock_add)
    resp = await _post(
        app,
        "/review/meeting/meet-456/attendee",
        json={"name": "Bob Builder", "email": "bob@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["attendee"]["email"] == "bob@example.com"
    assert captured["meeting_id"] == "meet-456"
    assert captured["name"] == "Bob Builder"
    assert captured["email"] == "bob@example.com"


async def test_contacts_directory_endpoint(app: Any, monkeypatch: Any) -> None:
    from meeting_notes import person_resolver

    monkeypatch.setattr(
        person_resolver,
        "get_contact_directory_list",
        lambda: [{"name": "Alice Smith", "email": "alice@example.com"}],
    )
    resp = await _get(app, "/graph/contacts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    contact = data["contacts"][0]
    assert contact["name"] == "Alice Smith"
    assert contact["email"] == "alice@example.com"
    assert "organization" in contact
    assert "role" in contact


@pytest.mark.asyncio
async def test_resolve_person_review_no_email_synthesis() -> None:
    """Invariant: resolve_person_review must NEVER synthesize email, keying by name."""
    from unittest.mock import AsyncMock, MagicMock

    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    class FakeResult:
        def __init__(self, items: list[dict[str, Any]]) -> None:
            self.items = items

        def __aiter__(self):
            async def gen():
                for item in self.items:
                    yield item
            return gen()

    expected_person_id = uuid5_id("person", "name:carol danvers")
    executed_queries: list[str] = []
    query_params: list[dict[str, Any]] = []

    def record_run(query: str, **kwargs: Any) -> Any:
        executed_queries.append(query)
        query_params.append(kwargs)
        if "MERGE (p:Person" in query:
            return FakeResult([{
                "person_id": expected_person_id,
                "name": "Carol Danvers",
                "email": None,
                "meeting_id": "meet-1",
            }])
        else:
            return FakeResult([{
                "review_id": "rev-999",
                "old_name": "Carol Danvers",
                "meeting_id": "meet-1",
                "title": "Review",
            }])

    mock_session.run = AsyncMock(side_effect=record_run)

    result = await graph_client.resolve_person_review(
        review_id="rev-999",
        name="Carol Danvers",
        email=None,
        driver=mock_driver,
    )

    assert result["person_id"] == expected_person_id
    assert result["email"] is None

    # Assert exactly two queries: find meeting review and MERGE person
    assert len(executed_queries) == 2
    for q in executed_queries:
        assert "toLower(p.name)" not in q, "Must never attempt to guess/borrow email from same-named Person"

    merge_params = [p for p in query_params if "person_id" in p][0]
    assert merge_params["email"] is None
    assert merge_params["person_id"] == expected_person_id


@pytest.mark.asyncio
async def test_resolve_person_review_does_not_borrow_existing_person_email() -> None:
    """Verify that resolving a person review without email never borrows an existing Person node's email."""
    from unittest.mock import AsyncMock, MagicMock

    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    class FakeResult:
        def __init__(self, items: list[dict[str, Any]]) -> None:
            self.items = items

        def __aiter__(self):
            async def gen():
                for item in self.items:
                    yield item
            return gen()

    expected_person_id = uuid5_id("person", "name:alex mercer")
    executed_queries: list[str] = []
    query_params: list[dict[str, Any]] = []

    def record_run(query: str, **kwargs: Any) -> Any:
        executed_queries.append(query)
        query_params.append(kwargs)
        if "MERGE (p:Person" in query:
            return FakeResult([{
                "person_id": expected_person_id,
                "name": "Alex Mercer",
                "email": None,
                "meeting_id": "meet-2",
            }])
        return FakeResult([{
            "review_id": "rev-100",
            "old_name": "Alex Mercer",
            "meeting_id": "meet-2",
            "title": "Review 2",
        }])

    mock_session.run = AsyncMock(side_effect=record_run)

    result = await graph_client.resolve_person_review(
        review_id="rev-100",
        name="Alex Mercer",
        email=None,
        driver=mock_driver,
    )

    assert result["person_id"] == expected_person_id
    assert result["email"] is None
    # No query should search for existing persons to copy their email
    for q in executed_queries:
        assert "p.email IS NOT NULL" not in q
        assert "coalesce($email, p.email)" not in q


@pytest.mark.asyncio
async def test_add_meeting_attendee_no_email_synthesis() -> None:
    """Invariant: add_meeting_attendee must NEVER synthesize email, keying by name."""
    from unittest.mock import AsyncMock, MagicMock

    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    class FakeResult:
        def __init__(self, items: list[dict[str, Any]]) -> None:
            self.items = items

        def __aiter__(self):
            async def gen():
                for item in self.items:
                    yield item
            return gen()

    expected_person_id = uuid5_id("person", "name:alex mercer")
    executed_queries: list[str] = []
    query_params: list[dict[str, Any]] = []

    def record_run(query: str, **kwargs: Any) -> Any:
        executed_queries.append(query)
        query_params.append(kwargs)
        return FakeResult([{
            "person_id": expected_person_id,
            "name": "Alex Mercer",
            "email": None,
            "meeting_id": "meet-123",
        }])

    mock_session.run = AsyncMock(side_effect=record_run)

    result = await graph_client.add_meeting_attendee(
        meeting_id="meet-123",
        name="Alex Mercer",
        email=None,
        driver=mock_driver,
    )

    assert result["person_id"] == expected_person_id
    assert result["email"] is None

    # Verify query semantics: CASE WHEN guard preserves verified emails without borrowing
    assert len(executed_queries) == 1
    q = executed_queries[0]
    assert "CASE WHEN $email IS NOT NULL THEN $email ELSE p.email END" in q
    assert "coalesce($email, p.email)" not in q

    params = query_params[0]
    assert params["email"] is None
    assert params["person_id"] == expected_person_id


@pytest.mark.asyncio
async def test_add_meeting_attendee_with_verified_email() -> None:
    """Verify add_meeting_attendee when explicit verified email is provided."""
    from unittest.mock import AsyncMock, MagicMock

    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    class FakeResult:
        def __init__(self, items: list[dict[str, Any]]) -> None:
            self.items = items

        def __aiter__(self):
            async def gen():
                for item in self.items:
                    yield item
            return gen()

    expected_person_id = uuid5_id("person", "alex.mercer@example.com")
    query_params: list[dict[str, Any]] = []

    def record_run(query: str, **kwargs: Any) -> Any:
        query_params.append(kwargs)
        return FakeResult([{
            "person_id": expected_person_id,
            "name": "Alex Mercer",
            "email": "alex.mercer@example.com",
            "meeting_id": "meet-123",
        }])

    mock_session.run = AsyncMock(side_effect=record_run)

    result = await graph_client.add_meeting_attendee(
        meeting_id="meet-123",
        name="Alex Mercer",
        email="alex.mercer@example.com",
        driver=mock_driver,
    )

    assert result["person_id"] == expected_person_id
    assert result["email"] == "alex.mercer@example.com"
    assert query_params[0]["email"] == "alex.mercer@example.com"
    assert query_params[0]["person_id"] == expected_person_id


async def test_add_attendee_endpoint_without_email(app: Any, monkeypatch: Any) -> None:
    """Verify POST /review/meeting/{meeting_id}/attendee succeeds when email is omitted."""
    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    captured: dict[str, Any] = {}

    async def mock_add(
        meeting_id: str, name: str, email: str | None = None, driver: Any = None
    ) -> dict[str, Any]:
        captured.update({"meeting_id": meeting_id, "name": name, "email": email})
        return {
            "person_id": uuid5_id("person", f"name:{name.lower()}"),
            "name": name,
            "email": email,
            "meeting_id": meeting_id,
        }

    monkeypatch.setattr(graph_client, "add_meeting_attendee", mock_add)
    resp = await _post(
        app,
        "/review/meeting/meet-789/attendee",
        json={"name": "Alex Mercer"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["attendee"]["email"] is None
    assert captured["meeting_id"] == "meet-789"
    assert captured["name"] == "Alex Mercer"
    assert captured["email"] is None


@pytest.mark.asyncio
async def test_resolve_person_review_second_call_preserves_verified_email() -> None:
    """Verify that a second resolve call with email=None preserves a previously verified email."""
    from unittest.mock import AsyncMock, MagicMock

    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    class FakeResult:
        def __init__(self, items: list[dict[str, Any]]) -> None:
            self.items = items

        def __aiter__(self):
            async def gen():
                for item in self.items:
                    yield item
            return gen()

    person_state: dict[str, Any] = {
        "id": uuid5_id("person", "alex.mercer@example.com"),
        "name": "Alex Mercer",
        "email": "alex.mercer@example.com",
    }

    def record_run(query: str, **kwargs: Any) -> Any:
        if "MERGE (p:Person" in query:
            # Emulate Cypher ON MATCH: CASE WHEN $email IS NOT NULL THEN $email ELSE p.email END
            if kwargs.get("email") is not None:
                person_state["email"] = kwargs["email"]
            return FakeResult([{
                "person_id": person_state["id"],
                "name": person_state["name"],
                "email": person_state["email"],
                "meeting_id": kwargs.get("meeting_id", "m-1"),
            }])
        return FakeResult([{
            "review_id": kwargs.get("review_id", "rev-1"),
            "old_name": "Alex Mercer",
            "meeting_id": "m-1",
            "title": "Planning",
        }])

    mock_session.run = AsyncMock(side_effect=record_run)

    # First call: resolved with verified email
    res1 = await graph_client.resolve_person_review(
        review_id="rev-1",
        name="Alex Mercer",
        email="alex.mercer@example.com",
        driver=mock_driver,
    )
    assert res1["email"] == "alex.mercer@example.com"

    # Second call for the same person, but caller provides email=None
    res2 = await graph_client.resolve_person_review(
        review_id="rev-2",
        name="Alex Mercer",
        email=None,
        driver=mock_driver,
    )
    assert (
        res2["email"] == "alex.mercer@example.com"
    ), "Must NOT null out or clobber verified email on re-resolution"


@pytest.mark.asyncio
async def test_add_meeting_attendee_second_call_preserves_verified_email() -> None:
    """Verify that a second add call with email=None preserves a previously verified email."""
    from unittest.mock import AsyncMock, MagicMock

    from meeting_notes import graph_client
    from meeting_notes.utils import uuid5_id

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    class FakeResult:
        def __init__(self, items: list[dict[str, Any]]) -> None:
            self.items = items

        def __aiter__(self):
            async def gen():
                for item in self.items:
                    yield item
            return gen()

    person_state: dict[str, Any] = {
        "id": uuid5_id("person", "alex.mercer@example.com"),
        "name": "Alex Mercer",
        "email": "alex.mercer@example.com",
    }

    def record_run(query: str, **kwargs: Any) -> Any:
        if kwargs.get("email") is not None:
            person_state["email"] = kwargs["email"]
        return FakeResult([{
            "person_id": person_state["id"],
            "name": person_state["name"],
            "email": person_state["email"],
            "meeting_id": kwargs.get("meeting_id", "m-1"),
        }])

    mock_session.run = AsyncMock(side_effect=record_run)

    res = await graph_client.add_meeting_attendee(
        meeting_id="m-2",
        name="Alex Mercer",
        email=None,
        driver=mock_driver,
    )
    assert (
        res["email"] == "alex.mercer@example.com"
    ), "Must NOT null out verified email when added without email"


def test_extractor_repair_date_fallback_preservation() -> None:
    """Verify that repair() preserves date fallback when ctx date is empty or None."""
    from datetime import UTC, datetime

    from meeting_notes.extractor import repair

    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Empty string in context date
    data1 = {"title": "Sprint Planning", "date": None}
    repaired1 = repair(data1, context={"date": ""})
    assert repaired1["date"] == today

    # None in context date
    data2 = {"title": "Architecture Review", "date": "null"}
    repaired2 = repair(data2, context={"date": None})
    assert repaired2["date"] == today


def test_initials_matching_single_and_ambiguous() -> None:
    """Verify that unique initials resolve, while ambiguous multi-person initials route to review."""
    from meeting_notes.person_resolver import Roster, resolve

    known_single = [
        {"name": "Alex Mercer", "email": "alex@example.com", "tracked": False},
        {"name": "Diana Prince", "email": "diana@example.com", "tracked": False},
    ]

    # Single match resolves
    r_single = resolve({"name": "AM", "email": None}, roster=Roster([]), known_people=known_single)
    assert r_single.status == "resolved"
    assert r_single.name == "Alex Mercer"
    assert r_single.email == "alex@example.com"
    assert r_single.reason == "person-initials"

    # Ambiguous initials (Alex Mercer and Alice Miller both have initials "AM") route to review
    known_ambiguous = [
        {"name": "Alex Mercer", "email": "alex@example.com", "tracked": False},
        {"name": "Alice Miller", "email": "alice@example.com", "tracked": False},
    ]
    r_ambiguous = resolve({"name": "AM", "email": None}, roster=Roster([]), known_people=known_ambiguous)
    assert r_ambiguous.status == "review"
    assert r_ambiguous.reason == "ambiguous-initials"


def test_person_resolver_roster_load_failure_logs_warning(monkeypatch: Any) -> None:
    """Verify that an invalid roster path logs structured warning instead of silent swallow."""
    from meeting_notes import person_resolver

    person_resolver.reset_roster_cache()
    warnings: list[str] = []

    def mock_warning(event: str, **kwargs: Any) -> None:
        warnings.append(event)

    monkeypatch.setattr(person_resolver.log, "warning", mock_warning)
    monkeypatch.setattr(person_resolver, "CONTACT_PROFILES", {})

    def bad_load(path: Any) -> Any:
        raise OSError("Permission denied on roster file")

    monkeypatch.setattr(person_resolver, "load_roster", bad_load)

    class FakeSettings:
        person_roster_path = "/bad/roster.json"

    monkeypatch.setattr("meeting_notes.config.get_settings", lambda: FakeSettings())

    res = person_resolver.resolve_to_full_name("Unknown Colleague")
    assert res == "Unknown Colleague"
    assert "person_resolver.roster_load_failed" in warnings
    person_resolver.reset_roster_cache()


def test_roster_loaded_flag_prevents_redundant_load_retries(monkeypatch: Any) -> None:
    """Verify that _ROSTER_LOADED flag prevents repeated filesystem/config loads on empty roster."""
    from meeting_notes import person_resolver

    load_calls = 0

    def mock_load(path: Any) -> Any:
        nonlocal load_calls
        load_calls += 1
        return person_resolver.Roster([])

    person_resolver.reset_roster_cache()
    monkeypatch.setattr(person_resolver, "load_roster", mock_load)

    class FakeSettings:
        person_roster_path = "/valid/empty_roster.json"

    monkeypatch.setattr("meeting_notes.config.get_settings", lambda: FakeSettings())

    # First call loads once
    person_resolver._ensure_roster_loaded()
    assert load_calls == 1

    # Second and third calls must NOT re-attempt load even though CONTACT_PROFILES is empty
    person_resolver._ensure_roster_loaded()
    person_resolver._ensure_roster_loaded()
    assert load_calls == 1
    person_resolver.reset_roster_cache()


def test_resolve_to_full_name_ambiguity_gating() -> None:
    """Verify resolve_to_full_name preserves raw mention when nickname collides across contacts."""
    from meeting_notes import person_resolver
    from meeting_notes.person_resolver import ContactProfile

    person_resolver.reset_roster_cache()
    p1 = ContactProfile(full_name="Alex Mercer", email="alex@example.com", nicknames=["Al"])
    p2 = ContactProfile(full_name="Alice Miller", email="alice@example.com", nicknames=["Al"])
    person_resolver.CONTACT_PROFILES["alex@example.com"] = p1
    person_resolver.CONTACT_PROFILES["alice@example.com"] = p2

    # Colliding nickname "Al" must NOT guess; it must return the raw mention "Al"
    res = person_resolver.resolve_to_full_name("Al")
    assert res == "Al", "Ambiguous nickname collision must return raw mention, not guess first"

    # Unique mention resolves cleanly
    res_unique = person_resolver.resolve_to_full_name("Alex Mercer")
    assert res_unique == "Alex Mercer"
    person_resolver.reset_roster_cache()


def test_initials_matching_preempts_fuzzy_sequence_matching() -> None:
    """Verify that 2-3 letter initials route to ambiguous-initials before fuzzy name matching."""
    from meeting_notes.person_resolver import Roster, resolve

    # Known people where fuzzy sequence matcher might yield partial ratio on short token
    known = [
        {"name": "Adam Miller", "email": "adam@example.com", "tracked": False},
        {"name": "Alex Mercer", "email": "alex@example.com", "tracked": False},
    ]

    # "AM" matches initials for both Adam Miller and Alex Mercer -> routes to ambiguous-initials
    res = resolve({"name": "AM", "email": None}, roster=Roster([]), known_people=known)
    assert res.status == "review"
    assert res.reason == "ambiguous-initials", "Initials check must run before fuzzy matching on short tokens"


def test_expand_contact_mentions() -> None:
    """Verify expand_contact_mentions expands full names, emails, and aliases."""
    from meeting_notes import person_resolver
    from meeting_notes.person_resolver import ContactProfile

    person_resolver.reset_roster_cache()
    p = ContactProfile(
        full_name="Alex Mercer",
        email="alex@example.com",
        nicknames=["Lex"],
        initials=["AM"],
    )
    person_resolver.CONTACT_PROFILES["alex@example.com"] = p

    expanded = person_resolver.expand_contact_mentions(["Lex"])
    assert "Alex Mercer" in expanded
    assert "alex@example.com" in expanded
    assert "Lex" in expanded
    assert "AM" in expanded
    person_resolver.reset_roster_cache()


def test_expand_contact_mentions_ambiguity_gating() -> None:
    """Verify expand_contact_mentions does NOT expand ambiguous mentions across multiple contacts."""
    from meeting_notes import person_resolver
    from meeting_notes.person_resolver import ContactProfile

    person_resolver.reset_roster_cache()
    p1 = ContactProfile(
        full_name="Alex Mercer",
        email="alex@example.com",
        nicknames=["Al"],
        initials=["AM"],
    )
    p2 = ContactProfile(
        full_name="Alice Miller",
        email="alice@example.com",
        nicknames=["Al"],
        initials=["AM"],
    )
    person_resolver.CONTACT_PROFILES["alex@example.com"] = p1
    person_resolver.CONTACT_PROFILES["alice@example.com"] = p2

    # "Al" is ambiguous across both Alex and Alice -> must NOT expand aliases of either
    expanded = person_resolver.expand_contact_mentions(["Al"])
    assert expanded == ["Al"]
    assert "alex@example.com" not in expanded
    assert "alice@example.com" not in expanded
    person_resolver.reset_roster_cache()


def test_register_roster_contact_duplicate_email_ignored() -> None:
    """Verify that registering a second contact with an existing email logs warning and does not clobber."""
    from meeting_notes import person_resolver
    from meeting_notes.person_resolver import _register_roster_contact

    person_resolver.reset_roster_cache()
    _register_roster_contact("Primary Person", "test@example.com", [], {})
    assert person_resolver.CONTACT_PROFILES["test@example.com"].full_name == "Primary Person"

    # Attempt to register duplicate with differing name
    _register_roster_contact("Imposter Person", "test@example.com", [], {})
    assert person_resolver.CONTACT_PROFILES["test@example.com"].full_name == "Primary Person"
    person_resolver.reset_roster_cache()


def test_gitignore_protects_roster_secrets() -> None:
    """Verify that .gitignore excludes roster json files while preserving example templates."""
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    check_ignored = subprocess.run(
        ["git", "check-ignore", "roster.json", "company_roster.json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert "roster.json" in check_ignored.stdout
    assert "company_roster.json" in check_ignored.stdout

    # Verify negation rule: *roster*.example.json is NOT ignored
    check_example = subprocess.run(
        ["git", "check-ignore", "roster.example.json", "company_roster.example.json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert check_example.returncode != 0
    assert "roster.example.json" not in check_example.stdout


def test_resolve_attendees_drops_junk_speakers_from_both_queues() -> None:
    """Verify that resolve_attendees excludes junk placeholder speakers from both resolved and reviews."""
    from meeting_notes.models import Attendee
    from meeting_notes.person_resolver import Roster, resolve_attendees

    attendees = [
        Attendee(name="Speaker 1", role="attendee", email=None),
        Attendee(name="Unknown", role="attendee", email=None),
        Attendee(name="Alex Mercer", role="attendee", email="alex@example.com"),
    ]
    resolved, reviews = resolve_attendees(attendees, roster=Roster([]))
    resolved_names = [r.name for r in resolved]
    review_names = [r.name for r in reviews]

    assert "Alex Mercer" in resolved_names
    assert "Speaker 1" not in resolved_names
    assert "Speaker 1" not in review_names
    assert "Unknown" not in resolved_names
    assert "Unknown" not in review_names


@pytest.mark.asyncio
async def test_add_meeting_attendee_coalesce_preserves_existing_name() -> None:
    """Verify that add_meeting_attendee preserves existing Person name via coalesce(p.name, $name)."""
    from unittest.mock import AsyncMock, MagicMock

    from meeting_notes import graph_client

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    executed_queries: list[str] = []

    def record_run(query: str, **kwargs: Any) -> Any:
        executed_queries.append(query)

        class FakeResult:
            def __aiter__(self):
                async def gen():
                    yield {"person_id": "p-1", "name": "Alex Mercer", "email": None, "meeting_id": "m-1"}
                return gen()

        return FakeResult()

    mock_session.run = AsyncMock(side_effect=record_run)
    await graph_client.add_meeting_attendee("m-1", "Al Mercer", None, driver=mock_driver)
    merge_query = executed_queries[0]
    assert "ON MATCH SET p.name = coalesce(p.name, $name)" in merge_query







