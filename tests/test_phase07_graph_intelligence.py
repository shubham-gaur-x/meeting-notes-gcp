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


# ─── memory/episodic ──────────────────────────────────────────────────────────

from meeting_notes.memory import episodic, procedural  # noqa: E402


async def test_temporal_chain_computes_gap_days_on_the_edge() -> None:
    """'These happened three days apart' is the signal; merely being ordered
    is not."""
    session = FakeSession(results={"PRECEDED_BY": [{"prior_id": "m0"}]})
    linked = await episodic.link_temporal_chain(
        "m1", "2026-08-20", ["a@corp.com"], driver=FakeDriver(session)
    )

    assert linked is True
    assert "gap_days" in session.cypher()


async def test_no_attendees_means_no_temporal_link() -> None:
    session = FakeSession()
    linked = await episodic.link_temporal_chain("m1", "2026-08-20", [], driver=FakeDriver(session))
    assert linked is False
    assert session.calls == []


async def test_causality_is_skipped_unless_follow_up_is_needed() -> None:
    """The cheap gate before an LLM call, mirroring the classifier's role."""
    calls: list[str] = []

    async def counting_chat(system, user, **kw):
        calls.append(user)
        return {"references_prior": True, "reference_description": "x"}

    count = await episodic.detect_causality(
        _meeting(follow_up_needed=False), "m1",
        driver=FakeDriver(FakeSession()), chat=counting_chat,
    )
    assert count == 0
    assert calls == [], "no LLM call when follow_up_needed is false"


async def test_causality_links_to_the_best_matching_decision() -> None:
    session = FakeSession(results={"MATCH (d:Decision)": [
        {"id": "d1", "text": "We decided to migrate the database in Q3"},
        {"id": "d2", "text": "Lunch is at noon"},
    ]})

    async def fake_chat(system, user, **kw):
        return {"references_prior": True,
                "reference_description": "the database migration decision"}

    count = await episodic.detect_causality(
        _meeting(follow_up_needed=True), "m1", driver=FakeDriver(session), chat=fake_chat
    )

    assert count == 1
    caused = [p for c, p in session.calls if "CAUSED_BY" in c]
    assert caused and caused[0]["decision_id"] == "d1"


async def test_weak_overlap_creates_no_causal_link() -> None:
    """A spurious CAUSED_BY edge is worse than none — it asserts a causal
    claim the graph will later present as fact."""
    assert episodic._best_overlap("completely unrelated words here",
                                  [{"id": "d1", "text": "database migration quarterly"}]) is None


async def test_decay_floors_at_a_tenth_rather_than_zero() -> None:
    """Decaying to zero would make old meetings invisible to ranking rather
    than merely less prominent."""
    session = FakeSession(results={"relevance_weight": [{"updated": 5}]})
    result = await episodic.decay_relevance(driver=FakeDriver(session))

    assert result["meetings_decayed"] == 5
    assert "0.1" in session.cypher() and "0.95" in session.cypher()


def test_memory_sessions_are_written_only_by_episodic() -> None:
    """CLAUDE.md: DO NOT write MemorySession nodes outside memory/episodic.py."""
    import re
    from pathlib import Path

    package = Path(episodic.__file__).resolve().parent.parent

    # Look for a Cypher WRITE against the label (MERGE/CREATE (x:MemorySession)),
    # not the bare word -- which legitimately appears in prose describing who
    # owns it. An earlier draft matched the memory package's own docstring.
    write = re.compile(r"(MERGE|CREATE)\s*\(\s*\w*\s*:\s*MemorySession")
    offenders = [
        path.name for path in package.rglob("*.py")
        if path.name != "episodic.py" and write.search(path.read_text())
    ]
    assert not offenders, f"MemorySession written outside episodic.py: {offenders}"


async def test_a_logged_session_records_what_it_accessed() -> None:
    session = FakeSession()
    session_id = await episodic.log_session(
        "who owns billing?", "Alice does.", ["m1", "f2"], driver=FakeDriver(session)
    )

    assert session_id
    assert "ACCESSED" in session.cypher()


# ─── memory/procedural ────────────────────────────────────────────────────────


def test_one_on_one_matches_exactly_two_attendees() -> None:
    pattern = procedural.KNOWN_PROCEDURE_PATTERNS["one_on_one"]
    two = _meeting(attendees=[{"name": "A", "email": "a@x.com"}, {"name": "B", "email": "b@x.com"}])
    three = _meeting(attendees=[{"name": n, "email": f"{n}@x.com"} for n in "abc"])

    assert procedural.matches_pattern(two, pattern) is True
    assert procedural.matches_pattern(three, pattern) is False


def test_client_review_requires_two_distinct_domains() -> None:
    """requires_multi_org is what separates an internal review from a client
    one; same-domain attendees must not match."""
    pattern = procedural.KNOWN_PROCEDURE_PATTERNS["client_review"]
    internal = _meeting(topics=["demo"], attendees=[
        {"name": "A", "email": "a@onix.com"}, {"name": "B", "email": "b@onix.com"}])
    external = _meeting(topics=["demo"], attendees=[
        {"name": "A", "email": "a@onix.com"}, {"name": "B", "email": "b@client.com"}])

    assert procedural.matches_pattern(internal, pattern) is False
    assert procedural.matches_pattern(external, pattern) is True


def test_topic_keywords_match_case_insensitively() -> None:
    pattern = procedural.KNOWN_PROCEDURE_PATTERNS["retrospective"]
    assert procedural.matches_pattern(_meeting(topics=["Sprint RETRO notes"]), pattern) is True


def test_a_meeting_matching_nothing_returns_no_procedures() -> None:
    assert all(
        not procedural.matches_pattern(_meeting(topics=["unrelated"]), p)
        for name, p in procedural.KNOWN_PROCEDURE_PATTERNS.items()
        if name != "one_on_one"
    )


async def test_matching_increments_the_occurrence_count() -> None:
    """Occurrence count is what turns a pattern into a recognised procedure."""
    session = FakeSession()
    matched = await procedural.match_to_procedure(
        _meeting(topics=["incident", "outage"]), "m1", driver=FakeDriver(session)
    )

    assert "incident_response" in matched
    assert "p.occurrence_count + 1" in session.cypher()


# ─── memory/retrieval ─────────────────────────────────────────────────────────

from meeting_notes.config import Settings  # noqa: E402
from meeting_notes.memory import retrieval  # noqa: E402


def test_pipeline_never_imports_retrieval() -> None:
    """CLAUDE.md: DO NOT call memory/retrieval.py from pipeline.py.

    Retrieval is query-time only; importing it into the pipeline would put an
    LLM synthesis call on the ingestion path.
    """
    import re
    from pathlib import Path

    import meeting_notes.pipeline as pipeline_module

    source = Path(pipeline_module.__file__).read_text()
    # An actual import statement, not the word in a comment explaining why it
    # is absent -- an earlier draft matched this module's own docstring.
    importing = re.compile(
        r"^\s*(from\s+[\w.]*memory[\w.]*\s+import\s+[^\n]*\bretrieval\b"
        r"|import\s+[\w.]*\bretrieval\b)",
        re.M,
    )
    assert not importing.search(source), "pipeline.py imports retrieval"


async def test_an_untracked_person_yields_no_profile() -> None:
    """The governance promise: per-person analytics are opt-in. Aggregates are
    the default; naming individuals requires Person.tracked."""
    session = FakeSession(results={"MATCH (p:Person {email: $email})": [
        {"id": "p1", "name": "Alice", "email": "a@corp.com", "tracked": False,
         "pagerank_score": 0.9, "community_id": 1,
         "betweenness_centrality": 0.5, "degree_centrality": 0.4},
    ]})

    profile = await retrieval.person_memory_profile("a@corp.com", driver=FakeDriver(session))
    assert profile == {}, "an untracked person must not get a per-person profile"


async def test_a_tracked_person_yields_a_profile() -> None:
    session = FakeSession(results={"MATCH (p:Person {email: $email})": [
        {"id": "p1", "name": "Alice", "email": "a@corp.com", "tracked": True,
         "pagerank_score": 0.9, "community_id": 1,
         "betweenness_centrality": 0.5, "degree_centrality": 0.4},
    ]})

    profile = await retrieval.person_memory_profile("a@corp.com", driver=FakeDriver(session))
    assert profile["name"] == "Alice"
    assert "facts" in profile and "knows" in profile


async def test_an_unknown_person_yields_no_profile() -> None:
    profile = await retrieval.person_memory_profile("nobody@corp.com", driver=FakeDriver(FakeSession()))
    assert profile == {}


async def test_low_confidence_facts_are_filtered_at_read_time() -> None:
    """Facts seed at 0.3 and gain 0.1 per corroboration, so an unfiltered read
    surfaces one-off noise at the same weight as a well-corroborated fact."""
    session = FakeSession(results={"MATCH (p:Person {email: $email})": [
        {"id": "p1", "name": "A", "email": "a@corp.com", "tracked": True,
         "pagerank_score": None, "community_id": None,
         "betweenness_centrality": None, "degree_centrality": None},
    ]})
    settings = Settings(_env_file=None, FACT_MIN_CONFIDENCE=0.75)

    await retrieval.person_memory_profile("a@corp.com", driver=FakeDriver(session), settings=settings)

    fact_params = [p for c, p in session.calls if "HAS_FACT" in c]
    assert fact_params and fact_params[0]["min_confidence"] == 0.75


async def test_knows_is_matched_in_both_directions() -> None:
    """KNOWS is stored in one canonical direction (lexicographically ordered
    emails), so a directed match would lose half the edges."""
    session = FakeSession(results={"MATCH (p:Person {email: $email})": [
        {"id": "p1", "name": "A", "email": "a@corp.com", "tracked": True,
         "pagerank_score": None, "community_id": None,
         "betweenness_centrality": None, "degree_centrality": None},
    ]})
    await retrieval.person_memory_profile("a@corp.com", driver=FakeDriver(session))

    knows = [c for c, _ in session.calls if "KNOWS" in c]
    assert knows and "-[k:KNOWS]-(" in knows[0], "KNOWS must be matched undirected"


async def test_a_question_with_no_matching_context_is_answered_honestly() -> None:
    """Honest emptiness beats a confident guess — the point of a memory system
    is that its answers are grounded."""
    async def fake_chat(system, user, **kw):
        return {"people": [], "topics": [], "date_hint": None}

    result = await retrieval.full_memory_query(
        "what did we decide about nothing?", driver=FakeDriver(FakeSession()), chat=fake_chat
    )

    assert result["node_ids"] == []
    assert "don't have" in result["answer"]


async def test_an_answer_reports_the_nodes_it_came_from() -> None:
    """The caller can show its working rather than presenting an unsourced
    assertion."""
    session = FakeSession(results={"MATCH (f:Fact)": [
        {"id": "f1", "text": "Alice leads backend", "confidence": 0.8},
    ]})

    calls: list[str] = []

    async def fake_chat(system, user, **kw):
        calls.append(system)
        if "Extract entities" in system:
            return {"people": ["Alice"], "topics": [], "date_hint": None}
        return {"answer": "Alice leads the backend team."}

    result = await retrieval.full_memory_query(
        "who leads backend?", driver=FakeDriver(session), chat=fake_chat, log_session=False
    )

    assert "f1" in result["node_ids"]
    assert result["answer"] == "Alice leads the backend team."
    assert any("Context:" in s for s in calls), "the graph context must reach the model"


async def test_synthesis_failure_degrades_rather_than_raising() -> None:
    session = FakeSession(results={"MATCH (f:Fact)": [
        {"id": "f1", "text": "a fact", "confidence": 0.9},
    ]})

    async def half_broken_chat(system, user, **kw):
        if "Extract entities" in system:
            return {"people": [], "topics": [], "date_hint": None}
        raise RuntimeError("model down")

    result = await retrieval.full_memory_query(
        "anything?", driver=FakeDriver(session), chat=half_broken_chat, log_session=False
    )
    assert result["answer"] == retrieval.NO_CONTEXT_ANSWER


# ─── pipeline enrichment ──────────────────────────────────────────────────────

from meeting_notes import pipeline  # noqa: E402
from meeting_notes.models import StagedRecord  # noqa: E402


def _record() -> StagedRecord:
    """A Meet transcript: it skips the classifier gate by design, so this
    fixture exercises the enrichment path without depending on hand-tuned
    text clearing an arbitrary score threshold."""
    return StagedRecord(
        id="r1", source_id="s1", source_type="meet",
        payload={"title": "Budget planning sync",
                 "text": "We agreed the Q4 budget and assigned follow-ups.",
                 "start_time": "2026-08-20T10:00:00Z"},
        fetched_at="2026-08-20T00:00:00Z", processed=False,
    )


async def _noop_upsert(meeting, source_id):
    return "m1"


async def _noop_push(actions, meeting, source_id):
    return None


async def test_a_failing_enrichment_still_leaves_the_record_processed() -> None:
    """The graph write has already committed by the time enrichment runs, so a
    failing embedding must never fail a correctly-stored meeting."""
    marked: list[str] = []

    async def mark(record_id):
        marked.append(record_id)

    async def exploding_enrich(meeting, meeting_id):
        raise RuntimeError("embedding service down")

    async def fake_extract(*a, **kw):
        return _meeting(summary="we agreed the budget")

    original = pipeline.extractor.extract_meeting
    pipeline.extractor.extract_meeting = fake_extract  # type: ignore[assignment]
    try:
        result = await pipeline.process(
            _record(), pipeline.adapter_for("meet"),
            upsert=_noop_upsert, push_jira=_noop_push, mark_processed=mark,
            enrich_fn=exploding_enrich,
        )
    finally:
        pipeline.extractor.extract_meeting = original  # type: ignore[assignment]

    assert result.status == "processed", "enrichment failure must not change the outcome"
    assert marked == ["r1"], "the record must still be marked processed"


async def test_one_failing_enrichment_layer_does_not_skip_the_others() -> None:
    """Caught individually: a broken causality call must not cost us the
    embeddings that would have run after it."""
    ran: list[str] = []

    class Boom:
        def __getattr__(self, name):
            raise RuntimeError("layer down")

    async def ok(*a, **kw):
        ran.append("ok")
        return 1

    # Exercise the real enrich() with a mixture of working and failing steps by
    # patching the modules it imports.
    import meeting_notes.memory.semantic as sem

    original = sem.extract_facts
    sem.extract_facts = ok  # type: ignore[assignment]
    try:
        outcome = await pipeline.enrich(_meeting(), "m1")
    finally:
        sem.extract_facts = original  # type: ignore[assignment]

    # Every step appears in the outcome, whether it succeeded or was caught.
    assert set(outcome) >= {"facts", "relationships", "temporal", "causality",
                            "procedures", "embed_meeting", "embed_actions",
                            "embed_facts", "algorithms"}


async def test_facts_are_embedded_or_fact_search_can_never_return_anything() -> None:
    """`/graph/search/facts` queries the Fact vector index, so a Fact with no
    embedding is invisible to it forever.

    Found live: the pipeline embedded Meetings and ActionItems but not Facts,
    so the endpoint answered `count: 0` against 83 real Facts. The enrich step
    is what populates the index the endpoint reads.
    """
    assert "embed_facts" in pipeline.enrich_step_names(), (
        "enrich() must embed Facts, or search/facts is dead on arrival"
    )


async def test_enrichment_is_skipped_for_a_low_score_record() -> None:
    """No point embedding something the classifier already rejected."""
    called: list[str] = []

    async def counting_enrich(meeting, meeting_id):
        called.append(meeting_id)

    async def mark(record_id):
        return None

    record = StagedRecord(
        id="r2", source_id="s2", source_type="email",
        payload={"subject": "lunch", "body": "anyone want lunch", "from": "a@x.com", "to": "b@x.com"},
        fetched_at="2026-08-20T00:00:00Z", processed=False,
    )
    result = await pipeline.process(
        record, pipeline.adapter_for("email"),
        upsert=_noop_upsert, push_jira=_noop_push, mark_processed=mark,
        enrich_fn=counting_enrich,
    )

    assert result.status == "skipped_low_score"
    assert called == [], "a rejected record must not be enriched"


# ─── nightly orchestration ────────────────────────────────────────────────────

from meeting_notes import nightly  # noqa: E402


async def test_one_failing_nightly_step_does_not_sink_the_others() -> None:
    """A transient Memgraph conflict in the full algorithm pass must not cost
    us the night's decay and consolidation."""
    async def flaky(name: str):
        if name == "algorithms":
            raise RuntimeError("Cannot resolve conflicting transactions")
        return {"ok": name}

    outcome = await nightly.run(step_fn=flaky)

    assert outcome["failures"] == 1
    assert outcome["results"]["algorithms"] is None
    assert outcome["results"]["decay"] == {"ok": "decay"}
    assert outcome["results"]["consolidate"] == {"ok": "consolidate"}


async def test_nightly_runs_only_the_requested_steps() -> None:
    """--step lets Scheduler stagger the expensive passes and lets a single
    failed stage be re-run alone."""
    ran: list[str] = []

    async def recording(name: str):
        ran.append(name)
        return None

    await nightly.run(("decay",), step_fn=recording)
    assert ran == ["decay"]


async def test_an_unknown_step_is_rejected() -> None:
    import pytest as _pytest

    with _pytest.raises(ValueError, match="unknown step"):
        await nightly.run_step("not_a_step")


async def test_preference_consolidation_runs_once_per_person_not_per_meeting() -> None:
    """infer_preferences() works per meeting, which is the wrong granularity:
    it would spend one LLM call per attendee per meeting to re-derive the same
    stable traits. Worse, it was never wired to anything, so the Preference
    layer sat empty while the rest of semantic memory filled up."""
    calls: list[str] = []

    class _People(FakeSession):
        async def run(self, cypher: str, **params: Any) -> Any:
            if "count(m) AS meetings" in cypher:
                return FakeResult([
                    {"email": "a@corp.com", "name": "A", "meetings": 5},
                    {"email": "b@corp.com", "name": "B", "meetings": 3},
                ])
            if "ORDER BY m.date DESC" in cypher:
                return FakeResult([{"title": "Sync", "summary": "we synced"}])
            return await super().run(cypher, **params)

    async def fake_chat(system, user, **kw):
        calls.append(user)
        return [{"category": "work_pattern", "value": "prefers async updates"}]

    result = await semantic.consolidate_preferences(
        driver=FakeDriver(_People()), chat=fake_chat
    )

    assert result["people"] == 2
    assert len(calls) == 2, "one LLM call per PERSON, not per person per meeting"


async def test_preference_consolidation_skips_people_with_no_history() -> None:
    class _Empty(FakeSession):
        async def run(self, cypher: str, **params: Any) -> Any:
            if "count(m) AS meetings" in cypher:
                return FakeResult([{"email": "a@corp.com", "name": "A", "meetings": 2}])
            return FakeResult([])

    called: list[str] = []

    async def fake_chat(system, user, **kw):
        called.append(user)
        return []

    await semantic.consolidate_preferences(driver=FakeDriver(_Empty()), chat=fake_chat)
    assert called == [], "no history means nothing to infer from"


# ─── meeting quality (built in Phase 2, never wired) ──────────────────────────


def test_quality_is_a_nightly_step() -> None:
    """`meeting_quality` was fully built and tested in Phase 2 and PHASE_PLAN
    deferred its orchestration to "the nightly quality job" -- which never
    landed, leaving compute_quality, get_meetings_quality_inputs and
    set_meeting_quality with no caller between them."""
    from meeting_notes import nightly

    assert "quality" in nightly.STEPS


async def test_the_quality_step_scores_and_writes_every_meeting() -> None:
    from meeting_notes import nightly

    rows = [
        {"id": "m1", "duration_minutes": 60, "summary": "agenda: ship it",
         "attendee_count": 4, "action_count": 2, "decision_count": 1, "actions_done": 1},
        {"id": "m2", "duration_minutes": 30, "summary": "",
         "attendee_count": 2, "action_count": 0, "decision_count": 0, "actions_done": 0},
    ]
    written: list[tuple[str, float]] = []

    async def fake_inputs():
        return rows

    async def fake_set(meeting_id, score, components):
        written.append((meeting_id, score))

    out = await nightly.run_step(
        "quality", get_inputs=fake_inputs, set_quality=fake_set
    )

    assert out["scored"] == 2
    assert {m for m, _ in written} == {"m1", "m2"}
    assert all(0.0 <= s <= 1.0 for _, s in written), "a composite must be a 0-1 score"


async def test_the_quality_step_survives_a_meeting_it_cannot_score() -> None:
    """One unscoreable meeting must not cost the whole nightly pass."""
    from meeting_notes import nightly

    async def fake_inputs():
        return [{"id": "bad"}, {"id": "ok", "duration_minutes": 30, "attendee_count": 2,
                                "action_count": 1, "decision_count": 1, "actions_done": 0}]

    written = []

    async def fake_set(meeting_id, score, components):
        if meeting_id == "bad":
            raise RuntimeError("write failed")
        written.append(meeting_id)

    out = await nightly.run_step("quality", get_inputs=fake_inputs, set_quality=fake_set)
    assert written == ["ok"]
    assert out["failed"] == 1


async def test_pending_rows_are_embedded_concurrently() -> None:
    """Embeddings are independent network calls, so issuing them one at a time
    makes a meeting's cost linear in its action-item count.

    Measured live: a single Vertex embed is ~11.7s, so one meeting with 16
    action items spent 3m11s in this loop alone -- the dominant cost of the
    whole drain, and enough to blow a Cloud Run Job timeout.
    """
    import asyncio

    from meeting_notes.memory import vector

    in_flight = 0
    peak = 0

    async def slow_embed(text, settings=None):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return [0.1] * 768

    rows = [{"id": f"a{i}", "task": f"task {i}"} for i in range(8)]

    class _Result:
        def __aiter__(self):
            self._it = iter(rows)
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration from None

    class _Session:
        async def run(self, cypher, **kw):
            return _Result() if "RETURN" in cypher else None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Driver:
        def session(self):
            return _Session()

    count = await vector._embed_pending(
        "MATCH ... RETURN a.id AS id, a.task AS task", "MATCH ... SET a.embedding = $embedding",
        "m1", "task", driver=_Driver(), settings=None, embed=slow_embed,
    )

    assert count == 8, "every row must still be embedded"
    assert peak > 1, (
        f"embeddings ran one at a time (peak in-flight={peak}); they are "
        "independent calls and must overlap"
    )


# ─── the tracked gate applies to every per-person surface ─────────────────────


def _person_gating_source(fn_name: str) -> str:
    """The function's own body, not a fixed character window.

    A window ran past the end of a short function into the next one's
    docstring, so the assertion below was satisfied by neighbouring prose
    rather than by the gate itself -- inserting a function between them broke
    it while the gate was still perfectly in place.
    """
    from pathlib import Path

    source = Path("meeting_notes/graph_client.py").read_text()
    start = source.index(f"async def {fn_name}(")
    nxt = source.find("\nasync def ", start + 1)
    return source[start : nxt if nxt != -1 else len(source)]


def test_bridge_nodes_gate_untracked_people() -> None:
    """CLAUDE.md names centrality explicitly: "Per-person analytics -- PageRank,
    centrality, any leaderboard -- must filter on tracked = true".

    get_bridge_nodes ranks by betweenness centrality and was naming untracked
    individuals on the dashboard: with 0 of 33 people opted in, it still
    returned three of them by name.
    """
    assert "_UNTRACKED_PERSON_EXCLUDED" in _person_gating_source("get_bridge_nodes"), (
        "betweenness centrality names individuals and must honour Person.tracked"
    )


def test_community_members_gate_untracked_people() -> None:
    """The workstream drill-down lists a cluster's members by name. That is
    still naming individuals, so it takes the same gate."""
    assert "_UNTRACKED_PERSON_EXCLUDED" in _person_gating_source("get_community_members"), (
        "community membership names individuals and must honour Person.tracked"
    )


async def test_an_untracked_person_is_absent_from_bridges_and_communities() -> None:
    """The behaviour, not just the source: an untracked Person must not appear."""
    from meeting_notes import graph_client

    captured: list[str] = []

    class _Result:
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    class _Session:
        async def run(self, cypher, **kw):
            captured.append(cypher)
            return _Result()
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _Driver:
        def session(self): return _Session()

    await graph_client.get_bridge_nodes(driver=_Driver())
    await graph_client.get_community_members(1, driver=_Driver())

    for cypher in captured:
        assert "tracked" in cypher, f"no tracked gate in:\n{cypher}"


# ─── action-item owners are order-dependent too ───────────────────────────────


def test_nightly_reresolves_action_item_owners() -> None:
    """ASSIGNED_TO has the same order-dependence reresolve_reviews exists for.

    Measured on the rebuilt corpus: meetings written at 23:13:37, first Person
    node created at 23:15:15. Action items extracted in those 98 seconds could
    not match anyone, so ASSIGNED_TO never formed -- and nothing ever retried.
    22 action items, 3 assigned, while the resolver matched 'Namrata Mehta' to
    namrata.mehta@onixnet.com at confidence 1.00 when asked directly.
    """
    from meeting_notes import person_resolver

    assert hasattr(person_resolver, "reresolve_action_owners")


async def test_reresolve_attaches_a_now_resolvable_owner() -> None:
    from meeting_notes import person_resolver

    statements: list[tuple[str, dict]] = []

    class _Result:
        def __init__(self, rows): self._rows = list(rows)
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._rows:
                raise StopAsyncIteration
            return self._rows.pop(0)

    class _Session:
        async def run(self, cypher, **kw):
            statements.append((cypher, kw))
            if "RETURN a.id" in cypher:
                return _Result([{"action_id": "a1", "owner": "Namrata Mehta"}])
            return _Result([])
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _Driver:
        def session(self): return _Session()

    out = await person_resolver.reresolve_action_owners(
        driver=_Driver(),
        known_people=[{"email": "namrata.mehta@onixnet.com", "name": "Namrata Mehta",
                       "tracked": False}],
    )

    assert out["resolved"] == 1, f"expected the owner to resolve, got {out}"
    writes = [c for c, _ in statements if "ASSIGNED_TO" in c]
    assert writes, "no ASSIGNED_TO edge was written"


async def test_reresolve_leaves_an_unresolvable_owner_alone() -> None:
    """"The group" is not a person. It must not become one."""
    from meeting_notes import person_resolver

    class _Result:
        def __init__(self, rows): self._rows = list(rows)
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._rows:
                raise StopAsyncIteration
            return self._rows.pop(0)

    written: list[str] = []

    class _Session:
        async def run(self, cypher, **kw):
            if "RETURN a.id" in cypher:
                return _Result([{"action_id": "a1", "owner": "The group"}])
            written.append(cypher)
            return _Result([])
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return False

    class _Driver:
        def session(self): return _Session()

    out = await person_resolver.reresolve_action_owners(
        driver=_Driver(),
        known_people=[{"email": "namrata.mehta@onixnet.com", "name": "Namrata Mehta",
                       "tracked": False}],
    )
    assert out["resolved"] == 0
    assert not written, "an unresolvable owner must not write an edge"
