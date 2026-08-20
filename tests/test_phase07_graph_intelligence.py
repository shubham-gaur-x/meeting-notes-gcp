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


# ─── memory/vector ────────────────────────────────────────────────────────────

from meeting_notes.config import Settings  # noqa: E402
from meeting_notes.memory import vector  # noqa: E402


def _vec(seed: float = 0.1) -> list[float]:
    return [seed] * 768


async def test_an_embedding_is_written_at_the_configured_dimension() -> None:
    session = FakeSession()

    async def fake_embed(text, **kw):
        return _vec()

    ok = await vector.embed_meeting(
        "m1", "a budget discussion", driver=FakeDriver(session), embed=fake_embed
    )

    assert ok is True
    _, params = session.calls[0]
    assert len(params["embedding"]) == 768


async def test_a_none_embedding_is_skipped_rather_than_written_as_null() -> None:
    """A null embedding in the index is worse than none: vector search would
    return it as a spurious neighbour."""
    session = FakeSession()

    async def failing_embed(text, **kw):
        return None

    ok = await vector.embed_meeting(
        "m1", "text", driver=FakeDriver(session), embed=failing_embed
    )

    assert ok is False
    assert session.calls == [], "nothing should have been written"


async def test_embed_text_returns_none_rather_than_raising() -> None:
    """Enrichment must never block or roll back a meeting already committed."""
    async def exploding_embed(text, **kw):
        raise RuntimeError("model unavailable")

    assert await vector.embed_text("hello", embed=exploding_embed) is None


async def test_empty_text_is_not_embedded() -> None:
    calls: list[str] = []

    async def counting_embed(text, **kw):
        calls.append(text)
        return _vec()

    assert await vector.embed_text("   ", embed=counting_embed) is None
    assert calls == [], "no API call for empty text"


async def test_only_unembedded_action_items_are_fetched() -> None:
    """Idempotent by construction: a MERGE-matched item from an earlier meeting
    must not be re-embedded on every ingestion."""
    session = FakeSession(results={"FOLLOWS_UP": [{"id": "a1", "task": "ship it"}]})

    async def fake_embed(text, **kw):
        return _vec()

    count = await vector.embed_action_items_for_meeting(
        "m1", driver=FakeDriver(session), embed=fake_embed
    )

    assert count == 1
    assert "a.embedding IS NULL" in session.cypher()


async def test_search_returns_hits_ordered_by_similarity() -> None:
    session = FakeSession(results={"UNWIND": [
        {"id": "m2", "title": "Budget", "date": "2026-08-20", "summary": "s", "kind": "meeting"},
        {"id": "m1", "title": "Planning", "date": "2026-08-19", "summary": "s", "kind": "meeting"},
    ]})

    async def fake_embed(text, **kw):
        return _vec()

    async def fake_search(index, vec, limit, driver=None):
        return [{"node_id": "m1", "similarity": 0.95}, {"node_id": "m2", "similarity": 0.80}]

    hits = await vector.search_similar_meetings(
        "anything", driver=FakeDriver(session), embed=fake_embed, search=fake_search
    )

    assert [h["id"] for h in hits] == ["m1", "m2"], "search order must win over fetch order"
    assert hits[0]["similarity"] == 0.95


async def test_a_hit_whose_node_vanished_is_dropped_not_half_empty() -> None:
    session = FakeSession(results={"UNWIND": [
        {"id": "m1", "title": "Planning", "date": "d", "summary": "s", "kind": "meeting"},
    ]})

    async def fake_embed(text, **kw):
        return _vec()

    async def fake_search(index, vec, limit, driver=None):
        return [{"node_id": "m1", "similarity": 0.9}, {"node_id": "deleted", "similarity": 0.8}]

    hits = await vector.search_similar_meetings(
        "q", driver=FakeDriver(session), embed=fake_embed, search=fake_search
    )
    assert [h["id"] for h in hits] == ["m1"]


async def test_search_returns_empty_when_the_query_cannot_be_embedded() -> None:
    async def failing_embed(text, **kw):
        return None

    hits = await vector.search_similar_meetings(
        "q", driver=FakeDriver(FakeSession()), embed=failing_embed
    )
    assert hits == []


def test_only_graph_algorithms_issues_mage_calls() -> None:
    """CLAUDE.md: MAGE CALL procedures appear in graph_algorithms.py and
    nowhere else. Checks for the actual call SYNTAX (`CALL module.proc(`)
    rather than the word "CALL", which legitimately appears in prose.
    """
    import re
    from pathlib import Path

    pattern = re.compile(r"CALL\s+[a-z_]+\.[a-z_]+\s*\(")
    package = Path(vector.__file__).resolve().parent.parent

    offenders = []
    for path in package.rglob("*.py"):
        if path.name == "graph_algorithms.py":
            continue
        if pattern.search(path.read_text()):
            offenders.append(path.name)

    assert not offenders, f"MAGE CALL syntax outside graph_algorithms.py: {offenders}"


# ─── memory/semantic ──────────────────────────────────────────────────────────

from meeting_notes.memory import semantic  # noqa: E402
from meeting_notes.models import ExtractedMeeting  # noqa: E402


def _meeting(**over) -> ExtractedMeeting:
    base = {"title": "Sync", "kind": "meeting", "platform": "email",
            "date": "2026-08-20", "summary": "we discussed the budget"}
    base.update(over)
    return ExtractedMeeting.model_validate(base)


async def test_interested_in_matches_the_normalised_topic_name() -> None:
    """Regression test for a real v5 bug this port fixes.

    v5's strengthen_relationships matched Topic {name: $topic} with the
    RAW-cased topic straight off the extractor, but the write path stores
    names lowercased and stripped (v5 commit dcbb2d2 fixed the write side and
    get_topic_graph's read side — it never touched semantic_memory.py). Any
    topic with capitals matched zero rows and INTERESTED_IN silently never
    formed. Verified against real v6 data: all 61 stored Topic names are
    lowercase while the extractor emits "Budget Planning".
    """
    session = FakeSession()
    meeting = _meeting(
        topics=["  Budget Planning  "],
        attendees=[{"name": "A", "email": "a@corp.com"}, {"name": "B", "email": "b@corp.com"}],
    )

    await semantic.strengthen_relationships(meeting, "m1", driver=FakeDriver(session))

    topic_params = [p for c, p in session.calls if "INTERESTED_IN" in c]
    assert topic_params, "no INTERESTED_IN statement was issued"
    assert topic_params[0]["topic"] == "budget planning", (
        "the raw-cased topic would match zero Topic nodes and the edge would never form"
    )


def test_normalise_topic_matches_the_write_paths_key() -> None:
    """One named helper for the key, because writer/reader drift is a known
    v5 bug class (CLAUDE.md)."""
    assert semantic.normalise_topic("  Budget Planning  ") == "budget planning"
    assert semantic.normalise_topic("ALREADY") == "already"


async def test_knows_edges_are_created_once_per_pair() -> None:
    """email1 < email2 stops the double UNWIND emitting each pair twice."""
    session = FakeSession()
    meeting = _meeting(attendees=[
        {"name": "A", "email": "a@corp.com"}, {"name": "B", "email": "b@corp.com"}
    ])
    await semantic.strengthen_relationships(meeting, "m1", driver=FakeDriver(session))

    knows = [c for c, _ in session.calls if "KNOWS" in c]
    assert knows and "email1 < email2" in knows[0]


async def test_no_attendee_emails_means_no_relationship_work() -> None:
    session = FakeSession()
    await semantic.strengthen_relationships(_meeting(), "m1", driver=FakeDriver(session))
    assert session.calls == []


async def test_a_fact_gains_confidence_when_seen_again() -> None:
    """This is what makes it memory rather than a log: the same fact from a
    second meeting MERGEs onto one node and corroborates."""
    session = FakeSession()

    async def fake_chat(system, user, **kw):
        return ["Alice leads the backend team"]

    count = await semantic.extract_facts(
        _meeting(), "m1", driver=FakeDriver(session), chat=fake_chat
    )

    assert count == 1
    cypher = session.cypher()
    assert "ON CREATE SET f.text" in cypher and "f.confidence = 0.3" in cypher
    assert "f.source_count + 1" in cypher and "f.confidence + 0.1" in cypher


async def test_the_same_fact_text_derives_the_same_id() -> None:
    """Corroboration only works if the id is stable across case and spacing."""
    from meeting_notes.utils import uuid5_id

    a = uuid5_id("fact", "Alice leads the backend team".lower())
    b = uuid5_id("fact", "alice leads the backend team".lower())
    assert a == b


async def test_an_llm_failure_yields_no_facts_rather_than_raising() -> None:
    """Enrichment runs after the graph write has already committed; it must
    never fail the record."""
    async def exploding_chat(system, user, **kw):
        raise RuntimeError("model unavailable")

    count = await semantic.extract_facts(
        _meeting(), "m1", driver=FakeDriver(FakeSession()), chat=exploding_chat
    )
    assert count == 0


async def test_a_bare_json_array_response_is_accepted() -> None:
    """chat_json promises a dict, but these prompts ask for an array. Both
    shapes are accepted rather than discarding a well-formed answer."""
    assert semantic._parse_list(["a", "b"]) == ["a", "b"]
    assert semantic._parse_list({"facts": ["a"]}) == ["a"]
    assert semantic._parse_list('["a"]') == ["a"]
    assert semantic._parse_list(None) == []


async def test_blank_facts_are_skipped() -> None:
    session = FakeSession()

    async def fake_chat(system, user, **kw):
        return ["", "   ", None, 42, "a real fact"]

    count = await semantic.extract_facts(
        _meeting(), "m1", driver=FakeDriver(session), chat=fake_chat
    )
    assert count == 1
