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
    assert "/graph/actions/open" in html, "open action items are never fetched"
    assert "/graph/meeting/" in html, "no per-meeting drill-down"


def test_the_dashboard_offers_example_questions() -> None:
    """A bare text box gives a first-time user nothing to start from."""
    from pathlib import Path

    import api

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "EXAMPLES" in html and "prompt-card" in html


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
    assert paths == {"/webhook/github", "/webhook/jira", "/webhook/jira/sync"}, (
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
