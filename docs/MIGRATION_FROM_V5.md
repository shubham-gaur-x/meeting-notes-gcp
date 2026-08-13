# Migration map — v5 → v6

Source of truth for what gets ported, what changes, and what does not come across.

**v5 repo:** `~/Desktop/airbyte-lm-studio-memgraph` — read-only. Never write to it.

Read the "Bugs that must not be reintroduced" section before porting anything. Every entry
there cost real live debugging time in v5 and none of them were caught by unit tests.

---

## 1. Port map

Legend: **Lift** = copy near-verbatim · **Adapt** = port with known changes ·
**Rewrite** = same intent, new implementation · **Drop** = does not come across

### Core

| v5 | v6 | Action | Notes |
|---|---|---|---|
| `transform_service/models.py` | `meeting_notes/models.py` | **Adapt** | Keep `ExtractedMeeting`, `Attendee`, `ActionItem`, `Decision`, and the `_coerce_decisions` validator. Replace `AirbyteWebhookPayload`. Generalise the `Raw*` models — see §3. |
| `transform_service/utils.py` | `meeting_notes/utils.py` | **Lift** | `uuid5_id`, `with_retry`, `strip_json_fences`, `extract_ticket_keys`, `priority_from_due`, `configure_logging`. Almost unchanged. |
| — | `meeting_notes/config.py` | **New** | ADR-011. Typed settings; the only reader of `os.environ`. |
| `transform_service/db.py` | `meeting_notes/db.py` | **Adapt** | Cloud SQL connector instead of a plain DSN. Delete all Airbyte-table-discovery logic (§4). Add `SKIP LOCKED` claiming (ADR-006). |
| `transform_service/memgraph_client.py` | `meeting_notes/graph_client.py` | **Lift** | The 1181-line crown jewel. Cypher is portable as-is. Renamed for clarity; contents barely change. |
| `transform_service/classifier.py` | `meeting_notes/classifier.py` | **Lift** | Pure rules, no I/O. Zero changes expected. |
| `transform_service/meeting_type_router.py` | `meeting_notes/meeting_type_router.py` | **Lift** | Pure. |
| `transform_service/person_resolver.py` | `meeting_notes/person_resolver.py` | **Lift** | Pure, no Cypher. |
| `transform_service/dedup.py` | `meeting_notes/dedup.py` | **Lift** | Pure, no I/O. |
| `transform_service/meeting_quality.py` | `meeting_notes/meeting_quality.py` | **Lift** | Mostly pure scoring. |
| `transform_service/access_control.py` | `meeting_notes/access_control.py` | **Lift** | Pure policy. |

### LLM

| v5 | v6 | Action | Notes |
|---|---|---|---|
| `extractor._get_client()` | `meeting_notes/llm_client.py` | **Rewrite** | ADR-002. Two backends behind `chat_json()` / `embed()`. |
| `transform_service/extractor.py` | `meeting_notes/extractor.py` | **Adapt** | Keep the system prompt verbatim — it is tuned. Swap the client for `llm_client`. Keep `_is_null_like` and `_loads_lenient` unchanged. |

### Pipeline

| v5 | v6 | Action | Notes |
|---|---|---|---|
| `graph_builder.process_email` / `process_calendar_event` / `process_transcript` | `meeting_notes/pipeline.py` — one `process()` | **Rewrite** | ADR-010. Three ~90%-identical functions collapse into one plus per-source adapters. |
| `graph_builder.process_new_*` batch functions | `jobs/pipeline_drain.py` | **Rewrite** | Becomes a Cloud Run Job entrypoint. |
| `_GRAPH_SEM = asyncio.Semaphore(3)` | keep | **Lift** | Still protects Memgraph from concurrent write pressure within one execution. Cross-execution safety is ADR-006's job. |

### Ingestion

| v5 | v6 | Action | Notes |
|---|---|---|---|
| Airbyte Cloud (Gmail, Calendar, Jira) | `meeting_notes/sources/{gmail,calendar,jira}.py` + `jobs/ingest_*.py` | **Rewrite** | ADR-007. The single biggest new build. |
| `transform_service/meet_ingest.py` | `meeting_notes/sources/meet.py` | **Adapt** | Already a hand-written connector. Reshape to the `Source` protocol. |
| `transform_service/transcript_source.py` | `meeting_notes/sources/base.py` | **Adapt** | Generalise `TranscriptSource` into a `Source` protocol covering all four sources. |
| `scripts/setup_airbyte.py`, `scripts/update_bore_port.py`, `ngrok.yml`, `dockerfiles/bore.Dockerfile` | — | **Drop** | Airbyte and tunnel plumbing. Gone. |

### Graph intelligence

| v5 | v6 | Action | Notes |
|---|---|---|---|
| `graph_algorithms.py` | `meeting_notes/graph_algorithms.py` | **Lift** | MAGE is MAGE. Confirm procedure availability on the deployed Memgraph image version. |
| `semantic_memory.py` | `meeting_notes/memory/semantic.py` | **Adapt** | LLM calls route through `llm_client`. |
| `episodic_memory.py` | `meeting_notes/memory/episodic.py` | **Adapt** | Same. |
| `procedural_memory.py` | `meeting_notes/memory/procedural.py` | **Lift** | Mostly pattern matching. |
| `vector_memory.py` | `meeting_notes/memory/vector.py` | **Adapt** | Embeddings via `llm_client.embed()`. Still 768-dim. |
| `memory_retrieval.py` | `meeting_notes/memory/retrieval.py` | **Adapt** | LLM calls route through `llm_client`. |

### Jira

| v5 | v6 | Action | Notes |
|---|---|---|---|
| `jira_client.py` | `meeting_notes/jira_client.py` | **Lift** | Still the only file with Jira REST. |
| `jira_pusher.py` | `meeting_notes/jira_pusher.py` | **Lift** | Confidence gating and dedup logic carry over intact. |
| `jira_agent.py` | `meeting_notes/jira_sync.py` | **Adapt** | Renamed — it is a status sync, not an agent, and the old name caused confusion. Reads from the Jira connector rather than an Airbyte table. |

### API

| v5 | v6 | Action | Notes |
|---|---|---|---|
| `transform_service/main.py` | `api/main.py` + `api/routers/` | **Rewrite** | Strip all APScheduler wiring (ADR-005). Keep every endpoint. Split 440 lines into routers by concern. |
| `transform_service/static/dashboard.html` | `api/static/dashboard.html` | **Lift** | Self-contained vanilla JS, no build step. Keep it that way. |
| `github_webhook.py` | `meeting_notes/github_webhook.py` | **Lift** | Parsing only, no Cypher, no REST. Ships in v1 even though writers are v2. |
| `digest.py` | `meeting_notes/digest.py` | **Lift** | |
| Endpoints defined inline in `main.py` with raw Cypher (`/graph/procedures`, `/graph/memory/sessions`) | move Cypher to `graph_client.py` | **Adapt** | v5 leaked six Cypher queries into `main.py`, violating its own boundary rule. Fix during the port. |

### Deferred (v2)

| v5 | Action |
|---|---|
| `dev_agent/` (all 12 modules) | **Defer.** ADR-008. |
| `transform_service/action_agent.py` | **Defer, and re-evaluate.** Built on the Airbyte Agents SDK — the dependency v6 removes. |
| `litellm/config.yaml` | **Defer.** Only used by the deferred dev-agent hosted backends. |

### Infrastructure

| v5 | v6 | Action |
|---|---|---|
| `docker-compose.yml` | `terraform/` + a compose file for the Memgraph VM only | **Rewrite** |
| `Makefile` | `Makefile` | **Adapt** — `gcloud` / `terraform` targets replace `docker compose` |
| `transform_service/Dockerfile` | `Dockerfile` (api) + `Dockerfile.jobs` | **Adapt** |
| `.env` / `.env.example` | Secret Manager + `.env.example` | **Adapt** |
| `scripts/setup_memgraph.py` | keep | **Lift** — add the v1 provenance constraints (ADR-008) |
| `scripts/migrate_schema_v5.py` | fold into `setup_memgraph.py` | **Adapt** — v6 has no v5 legacy to migrate |
| `scripts/backfill.py`, `seed_*.py`, `test_pipeline.py` | keep | **Adapt** |
| `scripts/refresh_gcal_token.py`, `refresh_meet_token.py` | `jobs/refresh_tokens.py` | **Rewrite** — promoted from manual script to scheduled job |

### Tests

Port test-by-test alongside each module. v5 has 363 tests, all mocked, and that property is
worth more than the individual assertions — **do not regress it**. A test that needs live
credentials is a broken test.

Keep `tests/conftest.py`'s `_REAL_HTTPX` pattern. v5 discovered that several test files stubbed
optional-looking dependencies behind `if mod_name not in sys.modules`, so whichever test ran
first "won" for the entire session. The generalised fix in `conftest.py` is load-bearing.

---

## 2. Bugs that must not be reintroduced

Every one of these was found by live testing, not by the unit suite.

| # | Bug | Fix |
|---|---|---|
| 1 | **`ASSIGNED_TO` never forms.** The Cypher does `OPTIONAL MATCH (p:Person {email: $owner_email})` where `owner_email` is only non-null when `"@" in action.owner`. The extractor emits display names, so the edge count in the live graph is **zero**. | Resolve `action.owner` through `person_resolver` before the write, exactly as attendees are resolved. |
| 2 | **`get_active_run()` resume loop.** It treats any state not in `('CLOSED','FAILED','NEEDS_HUMAN')` as resumable, but a successful run parks at `SHIPPED`. Every poll re-resumed it *before* `should_attempt()` was consulted, and `start_run()` incremented the attempt each time — producing **61 `AgentRun` nodes for one ticket** in the live graph. | v2 concern, but fix it when porting: include `SHIPPED` in the terminal set, and consult `should_attempt()` before resuming. |
| 3 | **structlog reserved kwarg.** `log.info("...", event=event)` collides with structlog's own message field and raises `TypeError` at call time — a real HTTP 500 on `/webhook/github`. Every test called the handler directly, so the route function was never exercised. | Never use `event=`. Add an `httpx.ASGITransport` test that drives the real ASGI app for every route. |
| 4 | **Literal `"null"` strings from the LLM.** Gemma emits the string `"null"` rather than a JSON null; `if not data.get(...)` doesn't catch it because a non-empty string is truthy. | Keep `_is_null_like` and apply it to every extractor fallback. Verify Gemini's behaviour too — do not assume it's immune. |
| 5 | **Topic case fragmentation.** The `Topic` MERGE key used raw case, so "Migration" and "migration" became two nodes with a colliding `uuid5` id — fragmenting topics and understating every insight query. | MERGE on `lower().strip()`. Already fixed in v5; carry the fix, not the bug. |
| 6 | **Provenance id drift.** Node ids derived in one place and re-derived differently in another meant reads never found what writes created. Bit the project twice. | Derive each provenance id in exactly one helper. Never inline `uuid5_id` for a provenance node. |
| 7 | **`get_ticket_provenance` missing `c.message`.** The forward traversal returned commit messages; the reverse one silently didn't. | When a query has forward and reverse forms, test that their `RETURN` shapes match. |
| 8 | **`jira_agent.sync_jira_issue` always returned `True`**, even when zero nodes matched, so the counters were meaningless. | Return the real match result. |
| 9 | **Leiden over-fragmentation.** Community detection collapsed to all-singletons. | Check v5's git history for the fix before re-running community detection. |
| 10 | **Test-stub pollution.** See §1 Tests. | Keep the `conftest.py` fix. |

---

## 3. Data-model changes

### Raw record models

v5 has `RawEmail`, `RawCalendarEvent`, `RawMeetTranscript`, `RawJiraIssue` with overlapping
shapes and a `source_table` field carried on each. Since v6 owns every connector, normalise:

```
StagedRecord:
    id, source_id, source_type, payload (JSONB), fetched_at, processed
```

with a per-source adapter producing the extraction text and context. Keep the typed models as
the adapter's parse target so validation stays strict — this is a storage change, not a
loss of typing.

**Decide this explicitly in Phase 2 and record it as an ADR.** It affects `db.py`, `models.py`,
and every connector, and it is much cheaper to decide before writing them than after.

### What the live v5 graph actually contains

Inspected 2026-08-13. More accurate than v5's own docs.

**Node counts:** Meeting 84 · Fact 84 · Topic 72 · AgentRun 61 · ProcedureStep 26 ·
Preference 23 · ActionItem 18 · PersonReview 14 · Person 14 · Decision 10 · MemorySession 7 ·
Procedure 6 · Organization 4 · FileChange 3 · Ticket 1 · PullRequest 1 · Commit 1 · Checkpoint 1

**Declared but with zero instances:** `ASSIGNED_TO` (bug #1), `CAUSED_BY`, `RESOLVED_BY`,
`RAISES_BLOCKER`, `MENTIONS`. Also the `Blocker` and `Repository` node types.

Zero instances doesn't automatically mean broken — `RESOLVED_BY` needs a merge event that never
happened live — but each is worth a moment's thought during the port.

**Data skew to be aware of:** 61 of 84 meetings are `kind = standup`, and `AgentRun` is
inflated by bug #2. Any PageRank or community-detection result from the v5 graph is distorted
by both. Seed a realistic mix in v6 before drawing conclusions from graph algorithms.

**One-off node:** `Checkpoint` — a hand-written node from a July backend-quota investigation
(`docs/CHECKPOINT-live-run-backend.md`). Not part of the schema. Don't port it.

---

## 4. Airbyte residue to delete

v5's `db.py` carries scar tissue from Airbyte writing tables with unpredictable names. All of
it goes:

- `_jira_airbyte_table()` — discovers hash-suffixed `publicraw_jira_issues%` tables
- The Airbyte-preferred-with-fallback branching in `get_unprocessed_emails` / `get_unprocessed_events`
- `sync_airbyte_jira_to_staging()` — already a no-op stub
- The `DO $$ ... IF EXISTS raw_gcal_events` conditional `ALTER TABLE` blocks
- `create_staging_tables` running every 5 minutes as an APScheduler job — becomes a deploy-time migration
- `AirbyteWebhookPayload` and the `/webhook/airbyte` endpoint
- `AIRBYTE_WEBHOOK_SECRET`, `AIRBYTE_CLIENT_ID`, `AIRBYTE_CLIENT_SECRET`,
  `AIRBYTE_AGENTS_*`, `NGROK_AUTHTOKEN`

`processed_gmail_ids` **stays** — a separate processed-id tracker is still the right way to
survive a full re-sync, independent of Airbyte.

---

## 5. Order of porting

Follow `docs/PHASE_PLAN.md`. Summary: pure modules with no I/O first (they port almost
unchanged and give you a green test suite early), then the I/O layer, then the LLM seam, then
connectors, then the pipeline that ties them together, then intelligence, then the API.

Do not start with the connectors, however tempting. They are the only genuinely new code in the
project and they depend on Phase 0.5's auth outcome.
