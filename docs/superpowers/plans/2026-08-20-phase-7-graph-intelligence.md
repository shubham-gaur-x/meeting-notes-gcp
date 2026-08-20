# Phase 7 Graph Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The graph stops storing and starts knowing — PageRank and communities, four memory layers, 768-dim semantic search, and natural-language questions answered from real graph data.

**Architecture:** `graph_algorithms.py` is the only module with MAGE `CALL` procedures. Each memory module owns a slice of the schema and may issue Cypher **only** for the node/edge types it owns — the one documented exception to the "all Cypher in `graph_client.py`" rule. `pipeline.py` gains the enrichment step it has been missing; `jobs/nightly.py` runs the expensive passes on a schedule.

**Tech Stack:** Python 3.11+ · Memgraph MAGE 3.11.0 · `llm_client` (Vertex/fake) · `pytest`

## Global Constraints

From `CLAUDE.md`.

- **DO NOT put MAGE `CALL` procedures anywhere except `graph_algorithms.py`.** Every other module goes through its helpers (`vector_search`, `get_jaccard_similarity`).
- **Memory modules may issue Cypher ONLY for the node/edge types they own** (listed per task below). Anything else goes through `graph_client.py`.
- **DO NOT write `MemorySession` nodes outside `memory/episodic.py`.**
- **DO NOT call `memory/retrieval.py` from `pipeline.py`.** Retrieval is query-time only.
- **Embeddings are 768-dimensional** — both vector indexes are built for it (confirmed live in Phase 4).
- `Person.tracked` gates per-person analytics. Aggregates are the default; naming individuals is opt-in.
- `@with_retry` on every external call; never pass `event=` as a structlog kwarg.
- One test file for the phase: `tests/test_phase07_graph_intelligence.py`.

---

## Two findings that must carry across, checked before writing anything

**1. The Leiden fix (v5 commit `51bad50`), which `PHASE_PLAN` told me to look for.**
`igraphalg.community_leiden()` at MAGE's default `objective_function="CPM"` and
`resolution_parameter=1` over-fragments a graph this sparse into **all-singleton
communities** — confirmed live in v5 at **308/308 communities of size 1**. It silently
corrupted every insight endpoint (bridges, communities, PageRank all key off
`community_id`) until the next per-meeting fast run happened to overwrite it. v6 must call
`community_leiden("modularity")` explicitly. This is exactly the exit criterion "community
detection does not collapse to singletons".

The same commit added a **retry around each individual algorithm CALL** — real Memgraph
`Cannot resolve conflicting transactions` errors hit `betweenness_centrality` live when a
per-meeting fast run collided with the nightly full run writing the same properties.

**2. MAGE procedure availability — verified, not assumed.** All eight procedures v6 needs
are present on `memgraph-mage:3.11.0` (307 procedures total), the same tag
`terraform/envs/*.tfvars` pins for the deployed VM: `pagerank.get`,
`community_detection.get`, `betweenness_centrality.get`, `degree_centrality.get`,
`weakly_connected_components.get`, `igraphalg.community_leiden`,
`node_similarity.jaccard_pairwise`, `vector_search.search`.

---

## File Structure

| File | Owns (may write Cypher for) |
|---|---|
| `meeting_notes/graph_algorithms.py` | The ONLY MAGE `CALL` procedures |
| `meeting_notes/memory/vector.py` | `embedding` properties; vector search via `graph_algorithms` |
| `meeting_notes/memory/semantic.py` | `Fact`, `Preference`, `HAS_FACT`, `PREFERS`, `KNOWS`, `INTERESTED_IN` |
| `meeting_notes/memory/episodic.py` | `MemorySession`, `PRECEDED_BY`, `CAUSED_BY`, `ACCESSED` |
| `meeting_notes/memory/procedural.py` | `Procedure`, `ProcedureStep`, `FOLLOWS_PROCEDURE`, `HAS_STEP`, `NEXT_STEP` |
| `meeting_notes/memory/retrieval.py` | Query-time only — reads, never writes |
| `meeting_notes/pipeline.py` | Modify: add the enrichment step |
| `jobs/nightly.py` | Thin entrypoint, `--step` per stage |

---

### Task 1: `graph_algorithms.py`

**Files:** Create `meeting_notes/graph_algorithms.py`

- [ ] **Step 1: Write the failing tests** — the Leiden call passes `"modularity"` explicitly
  (a regression test for `51bad50`); fast uses Louvain and full uses Leiden; one failing
  algorithm does not abort the others; every result is consumed before the next call (the
  async driver otherwise misattributes a failure to the *next* algorithm).
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 2: `memory/vector.py`

**Files:** Create `meeting_notes/memory/__init__.py`, `meeting_notes/memory/vector.py`

Embeds meetings, facts and action items; searches via `graph_algorithms.vector_search`.
**Never calls a MAGE procedure directly.**

- [ ] **Step 1: Write the failing tests** — an embedding is stored at the configured
  dimension; a `None` embedding is skipped rather than written as null; search returns
  results ordered by similarity; backfill only touches nodes with no embedding.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 3: `memory/semantic.py`

**Files:** Create `meeting_notes/memory/semantic.py`

`Fact` and `Preference` extraction via `llm_client`, plus `KNOWS` / `INTERESTED_IN` weights.
`FACT_MIN_CONFIDENCE` gates what is written.

- [ ] **Step 1: Write the failing tests** — below-threshold facts are dropped; `KNOWS` weight
  strengthens on repeat co-attendance rather than duplicating the edge; a fixture-miss/`None`
  LLM response degrades to "no facts" rather than raising, since enrichment is best-effort.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 4: `memory/episodic.py` and `memory/procedural.py`

**Files:** Create both

Temporal chains (`PRECEDED_BY{gap_days}`), causality (`CAUSED_BY{confidence}`), relevance
decay, `MemorySession` logging; procedure matching and discovery via
`graph_algorithms.get_jaccard_similarity`.

- [ ] **Step 1: Write the failing tests** — `gap_days` is computed correctly; decay lowers
  `relevance_weight` for old meetings and leaves recent ones alone; a procedure match
  requires the configured confidence; `MemorySession` is only ever written here.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 5: `memory/retrieval.py`

**Files:** Create `meeting_notes/memory/retrieval.py`

Entity extraction → context assembly → synthesis. Reads only. `FACT_MIN_CONFIDENCE` applies at
read time in `person_memory_profile`, and `Person.tracked` gates per-person analytics.

- [ ] **Step 1: Write the failing tests** — an untracked person is excluded from per-person
  analytics (the governance promise); low-confidence facts are filtered at read time; a query
  with no matching entities returns an honest "nothing found" rather than a hallucinated answer.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 6: Pipeline enrichment and `jobs/nightly.py`

**Files:** Modify `meeting_notes/pipeline.py`; create `jobs/nightly.py`

`pipeline.process` gains the enrichment step v5 ran after each graph write — fast algorithms,
facts, preferences, relationships, temporal chain, causality, procedure match, embeddings.

**Enrichment is best-effort and must never fail the record.** The graph write has already
committed by then; a failing embedding call must not roll back a correctly-stored meeting.
v5 wrapped the whole block in `try/except` for exactly this reason.

- [ ] **Step 1: Write the failing tests** — a raising enrichment step still leaves the record
  processed and the pipeline result `processed`; enrichment is skipped entirely for a
  low-score record; `retrieval` is never imported by `pipeline` (the CLAUDE.md boundary).
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 7: Live verification

The 95 real Meeting / 29 real ActionItem nodes from Phase 6 are still in local Memgraph —
real data to run algorithms against, no new ingestion needed.

- [ ] **Step 1: `make demo-up`**, run fast + full algorithms against the real graph.
- [ ] **Step 2: Community detection does not collapse to singletons** — count community sizes
  after the **Leiden** (full) run and confirm real multi-member communities, the direct
  regression check for v5's `308/308` failure.
- [ ] **Step 3: Semantic search with zero keyword overlap** — embed the real meetings, then
  query with wording that shares no words with the target and confirm a sensible hit.
- [ ] **Step 4: A natural-language question answered from real graph data** via
  `retrieval.full_memory_query`. The `POST /graph/memory/query` **endpoint** is Phase 8; this
  proves the function behind it.
- [ ] **Step 5: `make demo-down`**, mark the phase done, `graphify . --update`.

---

## Self-review notes

- **Both v5 findings are carried with their reasons**, not silently: the Leiden
  `"modularity"` argument and the per-CALL retry, each with a regression test.
- **MAGE availability was verified against the real image** rather than assumed, and the tag
  matches what Terraform pins for the deployed VM.
- **The data-skew warning is respected:** `PHASE_PLAN` notes v5's graph is 73% standups and
  its algorithm output is distorted accordingly. v6's graph is real Onix email and calendar
  data across many meeting types, so PageRank output here is not inheriting that skew — worth
  stating when reading any result.
- **Exit criterion 3 is honestly split:** the retrieval *function* lands here, the
  `POST /graph/memory/query` *endpoint* is Phase 8's work.
