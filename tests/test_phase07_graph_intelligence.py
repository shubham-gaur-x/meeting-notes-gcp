"""Phase 7 — graph intelligence. No live Memgraph, no LLM, no network.

Every driver and LLM call is injected. The live checks (real algorithms
against the real 95-meeting graph, semantic search, NL query) are Task 7 of
the plan and run by hand.
"""

from __future__ import annotations

from typing import Any

from meeting_notes import graph_algorithms

# ─── fakes ────────────────────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, records: list[dict] | None = None) -> None:
        self._records = list(records or [])
        self.consumed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._records:
            raise StopAsyncIteration
        return self._records.pop(0)

    async def consume(self) -> Any:
        self.consumed = True
        return None

    async def single(self):
        return self._records[0] if self._records else None


class FakeSession:
    """Records every Cypher statement; can be told to fail specific ones."""

    def __init__(
        self,
        results: dict[str, list[dict]] | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.results = results or {}
        self.fail_on = fail_on
        self.issued: list[FakeResult] = []

    async def run(self, cypher: str, **params: Any) -> FakeResult:
        self.calls.append((cypher, dict(params)))
        if self.fail_on and self.fail_on in cypher:
            raise RuntimeError("Cannot resolve conflicting transactions")
        for key, records in self.results.items():
            if key in cypher:
                result = FakeResult(records)
                self.issued.append(result)
                return result
        result = FakeResult()
        self.issued.append(result)
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def cypher(self) -> str:
        return "\n".join(c for c, _ in self.calls)


class FakeDriver:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def session(self) -> FakeSession:
        return self._session


# ─── the Leiden fix (regression test for v5 commit 51bad50) ───────────────────


def test_leiden_requests_modularity_explicitly() -> None:
    """The single most important test in this file.

    MAGE's default objective_function is "CPM" at resolution_parameter=1,
    which over-fragments a graph this sparse into ALL-SINGLETON communities —
    confirmed live in v5 at 308/308 communities of size 1. That silently
    corrupted every insight endpoint (bridges, communities, PageRank all key
    off community_id) until the next per-meeting fast run happened to
    overwrite it. Dropping the argument is a silent, data-destroying
    regression, so it is asserted rather than trusted.
    """
    leiden = [c for name, c in graph_algorithms.FULL_ALGORITHMS if "leiden" in name]
    assert leiden, "the full run must include Leiden community detection"
    assert '"modularity"' in leiden[0], (
        "community_leiden must be called with objective_function='modularity'; "
        "the CPM default at resolution 1 collapses this graph to singletons"
    )


def test_fast_uses_louvain_and_full_uses_leiden() -> None:
    """Fast runs per meeting and must stay cheap; Leiden is the more accurate
    but more expensive nightly pass."""
    fast = dict(graph_algorithms.FAST_ALGORITHMS)
    full = dict(graph_algorithms.FULL_ALGORITHMS)

    assert any("community_detection.get" in c for c in fast.values())
    assert not any("community_leiden" in c for c in fast.values())
    assert any("community_leiden" in c for c in full.values())


def test_both_runs_cover_the_same_score_properties() -> None:
    """A nightly run must not leave a property the fast run sets, or insight
    endpoints see stale values from whichever ran last."""
    fast_props = {"pagerank_score", "community_id", "betweenness_centrality",
                  "degree_centrality", "wcc_id"}
    full_cypher = " ".join(c for _, c in graph_algorithms.FULL_ALGORITHMS)
    for prop in fast_props:
        assert prop in full_cypher, f"the full run never sets {prop}"


# ─── running them ─────────────────────────────────────────────────────────────


async def test_one_failing_algorithm_does_not_abort_the_others() -> None:
    """v5 caught failures per algorithm for exactly this reason: a transient
    conflict on one CALL must not silently skip the remaining four."""
    session = FakeSession(fail_on="betweenness_centrality")
    results = await graph_algorithms.run_fast(driver=FakeDriver(session))

    assert results["betweenness_centrality"].startswith("failed")
    assert results["pagerank"] == "ok"
    assert results["wcc"] == "ok"


async def test_every_result_is_consumed_before_the_next_call() -> None:
    """Consuming is required: the async driver otherwise defers execution and
    surfaces a failing statement's error on the NEXT session.run(), which
    misattributes the failure to the wrong algorithm."""
    session = FakeSession()
    await graph_algorithms.run_fast(driver=FakeDriver(session))

    assert session.issued, "no statements were run"
    assert all(r.consumed for r in session.issued), "a result was left unconsumed"


async def test_a_transient_conflict_is_retried() -> None:
    """Memgraph raises 'Cannot resolve conflicting transactions' when a
    per-meeting fast run collides with the nightly full run writing the same
    properties — real and reproduced live in v5."""
    attempts: list[str] = []

    class FlakySession(FakeSession):
        async def run(self, cypher: str, **params: Any) -> FakeResult:
            if "pagerank" in cypher:
                attempts.append(cypher)
                if len(attempts) < 2:
                    raise RuntimeError("Cannot resolve conflicting transactions")
            return await super().run(cypher, **params)

    session = FlakySession()
    results = await graph_algorithms.run_fast(driver=FakeDriver(session))

    assert len(attempts) == 2, "the transient conflict was not retried"
    assert results["pagerank"] == "ok"


async def test_vector_search_is_the_only_route_to_the_mage_procedure() -> None:
    """CLAUDE.md: MAGE CALL procedures live only in this module."""
    session = FakeSession(results={"vector_search.search": [
        {"node_id": "m1", "similarity": 0.9, "distance": 0.1},
        {"node_id": "m2", "similarity": 0.7, "distance": 0.3},
    ]})
    hits = await graph_algorithms.vector_search(
        "meeting_embedding_idx", [0.1] * 768, limit=2, driver=FakeDriver(session)
    )

    assert [h["node_id"] for h in hits] == ["m1", "m2"]
    assert "vector_search.search" in session.cypher()


async def test_jaccard_returns_zero_when_there_is_no_similarity() -> None:
    session = FakeSession()
    score = await graph_algorithms.get_jaccard_similarity(
        "a", "b", driver=FakeDriver(session)
    )
    assert score == 0.0
