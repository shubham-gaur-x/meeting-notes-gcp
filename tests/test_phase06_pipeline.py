"""Phase 6 — the pipeline. No live services; every dependency is injected.

The live checks (real Onix data, real Vertex, real local Memgraph) are Task 5
of the plan and run by hand.
"""

from __future__ import annotations

from meeting_notes.graph_client import get_open_actions_for_owner, update_action_jira_status

# ─── graph_client fixes (Task 1) ───────────────────────────────────────────────


class _FakeResult:
    def __init__(self, records: list[dict], *, updates: int = 0) -> None:
        self._records = records
        self._updates = updates

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._records:
            raise StopAsyncIteration
        return self._records.pop(0)

    async def consume(self):
        class _Summary:
            def __init__(self, n: int) -> None:
                class _Counters:
                    def __init__(self, n: int) -> None:
                        self.properties_set = n

                self.counters = _Counters(n)

        return _Summary(self._updates)


class _FakeSession:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result
        self.calls: list[tuple[str, dict]] = []

    async def run(self, cypher: str, **params) -> _FakeResult:
        self.calls.append((cypher, params))
        return self._result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeDriver:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result
        self.session_obj: _FakeSession | None = None

    def session(self) -> _FakeSession:
        self.session_obj = _FakeSession(self._result)
        return self.session_obj


async def test_get_open_actions_for_owner_excludes_the_given_id() -> None:
    """Without exclude_id, an item can match itself at similarity 1.0 — by the
    time jira_pusher runs, upsert_meeting_graph already wrote every action
    item in the meeting, including the one currently being deduped."""
    driver = _FakeDriver(_FakeResult([]))
    await get_open_actions_for_owner("alice@corp.com", exclude_id="action-42", driver=driver)

    cypher, params = driver.session_obj.calls[0]
    assert params.get("exclude_id") == "action-42"
    assert "<>" in cypher or "exclude_id" in cypher


async def test_update_action_jira_status_reports_whether_it_matched() -> None:
    """jira_sync's matched/unmatched counters must mean something — a silent
    no-op must not be reported as a match."""
    driver = _FakeDriver(_FakeResult([], updates=1))
    matched = await update_action_jira_status("SCRUM-1", "Done", True, driver=driver)
    assert matched is True


async def test_update_action_jira_status_reports_false_for_an_unknown_key() -> None:
    """A Jira ticket created outside this pipeline is real signal, not a bug —
    the caller needs to know it found nothing to update."""
    driver = _FakeDriver(_FakeResult([], updates=0))
    matched = await update_action_jira_status("SCRUM-999", "Done", True, driver=driver)
    assert matched is False
