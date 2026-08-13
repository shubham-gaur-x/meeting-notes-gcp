# Architecture — meeting-notes-gcp (v6)

Companion to `CLAUDE.md`. This file explains *why* the architecture is shaped this way and
enumerates every GCP resource. `CLAUDE.md` is the rules; this is the reasoning.

Written 2026-08-13, before implementation. Update it when reality diverges.

---

## 1. The one-sentence version

Meeting content from a Google Workspace account flows through our own Cloud Run Job connectors
into Cloud SQL, gets classified and extracted by Vertex AI Gemini, lands in Memgraph as a
property graph in a single ACID transaction, is enriched by graph algorithms and four memory
layers, and is served by a scale-to-zero FastAPI service — with Jira closing the loop in both
directions.

---

## 2. What changed from v5, and why

v5 was excellent at what it was designed for: running entirely on one laptop for a reliable
demo. Three of its defining choices don't survive contact with a cloud target.

### 2.1 Airbyte is removed

v5 kept Airbyte Cloud as the ingestion backbone, tunnelling through `bore`/`ngrok` to reach a
Postgres running on the laptop. That tunnel was pure accidental complexity — it existed only
because the destination was local.

On GCP there's no tunnel to justify, and three low-volume sources (one mailbox, one calendar,
one Jira project) do not need a managed ELT platform. The v5 code already contains the proof:
`meet_ingest.py` is a hand-written connector, and it is the *simplest* ingestion path in the
whole repo.

Replacement: one Cloud Run Job per source behind a `Source` protocol, cron'd by Cloud Scheduler.

### 2.2 APScheduler is removed — this is the biggest structural change

v5's `transform_service` is a poller wearing an API's clothes. `main.py` registers ten
APScheduler jobs at startup: five 5-minute intervals and five nightly crons. The FastAPI
endpoints are almost incidental.

Deploy that to Cloud Run unchanged and you must set `min-instances=1`, so you pay for an
always-on container and get none of the platform's benefits. Worse, you keep APScheduler's
failure mode: a job that raises inside a scheduler tick is logged and forgotten, with no retry
and no alert.

**The refactor:** every scheduled unit becomes a Cloud Run Job triggered by Cloud Scheduler.
Cloud Run Jobs give per-execution logs, automatic retries, execution history, and alerting on
failure. What's left in the Cloud Run *service* is genuinely request-driven — queries, the
dashboard, webhooks — and that scales to zero honestly.

| v5 APScheduler job | v6 |
|---|---|
| `poll_emails`, `poll_events`, `poll_transcripts`, `poll_jira` (5 min) | `jobs/pipeline_drain.py`, Scheduler `*/5 * * * *` |
| `poll_meet_pull` (5 min) | folded into `jobs/ingest_meet.py` |
| `ensure_columns` (5 min) | deleted — schema is a migration, not a heartbeat |
| `nightly_algorithms` 02:00 | `jobs/nightly.py --step algorithms` |
| `nightly_consolidate_semantic` 02:15 | `jobs/nightly.py --step consolidate` |
| `nightly_decay` 02:30 | `jobs/nightly.py --step decay` |
| `nightly_discover_procedures` 02:45 | `jobs/nightly.py --step procedures` |
| `nightly_meeting_quality` 03:00 | `jobs/nightly.py --step quality` |
| `action_agent_poll` (5 min) | deferred to v2 |

`ensure_columns` deserves a note: v5 re-ran `create_staging_tables()` every five minutes
because Airbyte would recreate tables underneath it with hash-suffixed names. With Airbyte gone
the schema is stable, so this becomes a one-shot migration run at deploy time.

### 2.3 LM Studio becomes one of two backends

v5's hardest rule was that extraction is always local. That rule existed to support a specific
claim — meeting data never leaves the Mac — and a specific constraint: no cloud LLM budget.

On GCP, Vertex AI Gemini keeps the data inside the same tenancy as everything else, is far
cheaper than running a GPU node, and is materially better at structured JSON extraction than a
12B local model. The claim gets restated, not abandoned: *meeting data never leaves our GCP
tenancy.*

LM Studio stays as a `LLM_BACKEND=lmstudio` option so local development costs nothing and the
"fully local" story remains demonstrable. The seam is small: v5 already funnels every LLM call
through `extractor._get_client()`, so making that an explicit module is a contained change.

---

## 3. Decisions that were considered and rejected

### Spanner Graph instead of Memgraph — rejected

The genuinely GCP-native graph answer. Rejected because the migration cost is most of the
codebase:

- ~99 Cypher call sites in `memgraph_client.py` would need rewriting to GQL.
- No MAGE. PageRank, Louvain, Leiden, betweenness centrality, and WCC would all need
  reimplementing by hand. That's the entire "graph intelligence" differentiator.
- No vector index in the same engine, so semantic search needs a separate service.
- No Memgraph MCP server, which is one of the most compelling parts of the demo — natural
  language graph queries from Claude Desktop.

Memgraph is open source, already proven in this system, and runs fine on a small VM. Revisit
only if operational burden becomes real.

### GKE Autopilot from day one — deferred, not rejected

Memgraph needs persistent storage and always-on availability, so it can't live on Cloud Run.
The choice is GCE VM or GKE.

Starting on a **GCE VM** because the personal-account phase is cost-sensitive and a VM is
simply cheaper and simpler. This is a genuinely reversible decision: the application connects
via `bolt://host:7687` either way, and not one line of application code knows the difference.
Move to GKE when Onix is paying and the k8s story is worth telling.

### Dataflow / Datastream for ingestion — rejected

Overkill for three low-volume sources, and expensive. Cloud Run Jobs are the right size.

### BigQuery as the staging layer — rejected

The staging tables are a transactional work queue with a `processed` flag and row-level
updates. That's exactly what BigQuery is bad at and Postgres is good at. BigQuery may earn a
place later as an analytics sink; it does not replace Cloud SQL here.

---

## 4. GCP resource inventory

Everything below is created by Terraform. Nothing by hand.

### Compute

| Resource | Type | Notes |
|---|---|---|
| `api` | Cloud Run **service** | FastAPI. `min-instances=0`. Public for webhooks; auth on query endpoints. |
| `ingest-gmail` | Cloud Run **job** | Scheduler `*/15 * * * *` |
| `ingest-calendar` | Cloud Run **job** | Scheduler `*/15 * * * *` |
| `ingest-meet` | Cloud Run **job** | Scheduler `*/10 * * * *`, Pub/Sub pull |
| `ingest-jira` | Cloud Run **job** | Scheduler `*/15 * * * *` |
| `pipeline-drain` | Cloud Run **job** | Scheduler `*/5 * * * *`. The main workhorse. |
| `nightly` | Cloud Run **job** | Scheduler `0 2 * * *`, `--step` argument per stage |
| `refresh-tokens` | Cloud Run **job** | Scheduler `0 */6 * * *`. See `GOOGLE_AUTH.md`. |
| `memgraph` | GCE VM (`e2-medium` start) | Memgraph MAGE + Lab + MCP via Docker Compose, persistent disk |

Only one job runs the pipeline at a time. Cloud Run Jobs do not deduplicate executions by
default, so `pipeline_drain` must claim rows with `SELECT ... FOR UPDATE SKIP LOCKED` — see §6.

### Data

| Resource | Notes |
|---|---|
| Cloud SQL PostgreSQL 15 | Smallest viable tier while on personal billing. Private IP preferred; Cloud SQL connector from Cloud Run. |
| Persistent disk on the Memgraph VM | Snapshot schedule for backup |
| Artifact Registry (Docker) | One repo, images for api + jobs |

### Messaging and scheduling

| Resource | Notes |
|---|---|
| Pub/Sub topic `meet-transcripts` | Target for Google Workspace Events |
| Pub/Sub **pull** subscription | Pull, not push — no inbound endpoint needed, and it's the pattern v5 already proved |
| Cloud Scheduler jobs | One per Cloud Run Job above |

### Security and operations

| Resource | Notes |
|---|---|
| Secret Manager | All secrets. Injected into Cloud Run as env vars. |
| Service accounts | One per workload, least privilege. No shared default SA. |
| Cloud Logging + Monitoring | Log-based alert on job failure |
| Budget alert | **Set this in Phase 1.** Personal billing account. |

---

## 5. Data flow, end to end

1. **Capture.** A connector job authenticates with the stored refresh token, pulls records
   since its last watermark, and writes rows to the matching `raw_*` table with
   `processed = false`. Connectors do no interpretation — capture and stage only.
2. **Claim.** `pipeline_drain` claims a batch with `SELECT ... FOR UPDATE SKIP LOCKED`.
3. **Classify.** `classifier.classify()` scores the text on rules alone. Below 0.40, mark
   processed and stop. No LLM has been called yet — this is the cheap gate and it stays cheap.
4. **Route.** `meeting_type_router.route()` picks a type (standup, planning, review, one_on_one,
   email_thread, general) and returns a type-specific prompt hint. Different meeting types
   should produce structurally different action items.
5. **Extract.** `extractor.extract_meeting()` calls `llm_client.chat_json()` at temperature 0
   and validates into `ExtractedMeeting`. A JSON parse failure is **not** retried — it is
   deterministic at temperature 0. A transport error **is** retried.
6. **Resolve.** `person_resolver` maps attendees to canonical people: email normalisation and
   roster lookup first (deterministic), fuzzy name match second (probabilistic). Anything
   unresolved becomes a `PersonReview` node. Attendees are never silently dropped.
7. **Write.** `pipeline` calls `graph_client.upsert_meeting_graph()`, which MERGEs the Meeting,
   People, Organizations, Topics, Decisions, and ActionItems in **one transaction**.
8. **Ticket.** `jira_pusher` checks confidence and dedup. Below `JIRA_CONFIDENCE_THRESHOLD` the
   ActionItem is marked `needs_review` and no ticket is created. Above `JIRA_DEDUP_THRESHOLD`
   similarity to an existing open item, it links `MENTIONED_IN` and comments on the existing
   ticket instead of opening a duplicate.
9. **Enrich.** Fast graph algorithms, fact and preference extraction, temporal and causal
   linking, procedure matching, embeddings. All best-effort — a failure here logs a warning and
   does not fail the record, because the graph write already committed.
10. **Mark.** `processed = true`.

Nightly: full algorithms, semantic consolidation, relevance decay, procedure discovery,
meeting-quality scoring.

Reverse direction: Jira status syncs back into `ActionItem.jira_status` via `jira_sync`, and
GitHub merge events land on `/webhook/github` (schema present in v1, writers in v2).

---

## 6. Concurrency, idempotency, exactly-once

v5 ran a single container, so `processed` as a plain boolean was sufficient. Cloud Run Jobs can
overlap — a slow execution can still be running when Scheduler fires the next one.

Three defences, all required:

1. **Claim rows, don't just read them.** `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n` inside a
   transaction. Two concurrent executions then take disjoint batches rather than duplicating
   work.
2. **Deterministic ids everywhere.** `uuid5_id(namespace, value)` means processing the same
   record twice MERGEs onto the same nodes instead of creating duplicates. This is the real
   safety net and the reason `MERGE` is mandatory.
3. **Jira creation is the one non-idempotent side effect.** It must be gated on
   `ActionItem.jira_key IS NULL`, checked inside the same transaction that sets it.

Set `max-retries` on the Cloud Run Jobs deliberately. With the above, a retry is safe.

---

## 7. Cost posture

Two always-on resources dominate: the Memgraph VM and the Cloud SQL instance. Everything else
is genuinely usage-priced, and inference on a handful of meetings a day is small.

Levers, in the order to pull them:

1. Smallest viable Cloud SQL tier while on personal billing.
2. `e2-small` or `e2-medium` for Memgraph; resize when the graph grows.
3. `min-instances=0` on the API service, always.
4. A Flash-tier Gemini model for extraction. A Pro-tier model is not needed to fill a JSON
   schema.
5. Scheduler frequencies are config, not architecture. 15-minute ingest is fine; 5-minute is a
   preference.

**Price this properly in Phase 1 against current rates and put a budget alert in Terraform
before the first `apply`.** Do not rely on estimates in this document — they were not verified
against live pricing.

---

## 8. Known risks

| Risk | Impact | Mitigation |
|---|---|---|
| Onix Workspace admin blocks unverified third-party apps | **Blocks everything.** No ingestion at all. | Phase 0.5 auth spike, before any other work |
| OAuth refresh token expires every 7 days on personal GCP | Pipeline silently stops weekly | `refresh-tokens` job + alert on failure; permanently fixed by the Onix project (Internal user type) |
| Meet transcription not enabled on the Workspace tenant | No transcript source | Verify in Phase 0.5. Gmail + Calendar still work without it. |
| Cloud Run Job overlap | Duplicate processing | `SKIP LOCKED` + deterministic ids (§6) |
| Onix data in a personal GCP project | Governance concern | Own-mailbox only, short retention, raise it proactively when asking for the Onix project |
| Memgraph VM is a single point of failure | Data loss | Persistent disk snapshots; graph is rebuildable from Cloud SQL raw tables |
| Vertex model names change | Build breaks | Model names are env vars, never literals. Confirm current names at build time. |
