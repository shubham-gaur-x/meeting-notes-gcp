# CLAUDE.md — meeting-notes-gcp

Read this entire file before writing any code. Re-read it at the start of every session.
This is the authoritative source of truth for this project.

**Status: Phase 0 (documentation only). No implementation exists yet.**
Start at `docs/PHASE_PLAN.md` and work phases in order. Do not skip Phase 0.5.

---

## What This Project Is

A **GCP-native** meeting-memory pipeline. Meeting content from a Google Workspace account
(Gmail, Calendar, Meet transcripts) plus Jira is ingested, extracted by an LLM into structured
form, and stored as a property graph that computes influence, remembers durable facts, decays
stale context, recognises recurring workflows, and answers natural-language questions.

This is **v6**, a deliberate fresh-repo port of v5. Lineage:

| Version | Stack | Repo | Status |
|---|---|---|---|
| v1 | Python + Obsidian vault | — | historical |
| v2 | n8n + Confluence + Jira | — | historical |
| v3 | Airbyte Cloud + Render + Groq + Memgraph Cloud | `shubham-gaur-x/airbyte-meeting` | **DO NOT TOUCH** |
| v4/v5 | Fully local — Docker Compose + LM Studio + local Memgraph + Airbyte Cloud | `shubham-gaur-x/airbyte-lm-studio-memgraph` | **reference only, read-only** |
| **v6** | **GCP-native — Cloud Run + Cloud SQL + Vertex AI + Memgraph on GCE** | **this repo** | **being built** |

The v5 repo lives at `~/Desktop/airbyte-lm-studio-memgraph`. It is a working, live-validated
system with 363 passing tests. **Read from it freely. Never write to it.**

### Why v6 exists

1. **GCP-native.** The deployment target is Google Cloud, not a MacBook.
2. **Airbyte is removed.** Ingestion is our own connectors as Cloud Run Jobs. This is the single
   biggest scope change from v5.
3. **Managed inference.** Vertex AI Gemini replaces LM Studio entirely, behind a swappable
   seam. Local models are out of scope (ADR-021); `fake` covers offline work.
4. **Keep the open-source core.** Memgraph + MAGE, FastAPI, the extraction prompts, the Cypher,
   and the test suite are the assets worth carrying across. They are not rewritten without cause.

### What v6 is NOT

- Not a rewrite. Port deliberately; justify every file that does *not* come across.
- Not multi-tenant. One Workspace user (`shubham.gaur@onixnet.com`), one graph.
- Not v2-scope for `action_agent` — see "Deferred" below. `dev_agent` moved to v1 (ADR-020).

---

## Deployment Context

**Now:** Shubham's **personal** GCP project. Cost-sensitive.
**Later:** an Onix-owned GCP project, once approved.

Data source is the **Onix Workspace account** (`shubham.gaur@onixnet.com`) in both cases. The
GCP project hosting the infrastructure and the Google account whose data is read are
deliberately different — this is supported and normal, but it has consequences documented in
`docs/GOOGLE_AUTH.md`. Read that file before touching anything auth-related.

**Portability to the Onix project is a first-class design constraint, not a later concern:**

- Everything is Terraform. No resource is created by hand in the console.
- No project ID, region, or account email is hardcoded anywhere. All of it comes from
  `terraform/envs/*.tfvars` and, at runtime, from environment variables.
- All secrets live in Secret Manager. Cloud Run injects them as env vars.
- Moving to Onix must be: new `.tfvars`, `terraform apply`, re-consent OAuth, restore data.

---

## Target Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  SOURCES (Onix Google Workspace + Jira)                      │
│  Gmail · Google Calendar · Google Meet transcripts · Jira    │
└───────────────────────────┬──────────────────────────────────┘
                            │ OAuth2 (Workspace) / API token (Jira)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  CLOUD RUN JOBS — one connector per source                   │
│  jobs/ingest_gmail · ingest_calendar · ingest_meet           │
│  jobs/ingest_jira                                            │
│  Triggered by Cloud Scheduler.  ← replaces Airbyte entirely  │
└───────────────────────────┬──────────────────────────────────┘
                            │ staged rows
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  CLOUD SQL (PostgreSQL 15)                                   │
│  raw_emails · raw_calendar_events · raw_meet_transcripts     │
│  raw_jira_issues · processed flag for exactly-once           │
└───────────────────────────┬──────────────────────────────────┘
                            │ Cloud Scheduler, every 5 min
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  CLOUD RUN JOB — jobs/pipeline_drain                         │
│    classifier          rules-based scorer, no LLM            │
│    meeting_type_router picks an extraction prompt            │
│    extractor           Vertex AI Gemini → structured JSON    │
│    person_resolver     canonical Person resolution           │
│    dedup               don't re-ticket recurring items       │
│    pipeline            MERGE → Memgraph in ONE transaction   │
│    jira_pusher         ActionItems → Jira                    │
└───────────────────────────┬──────────────────────────────────┘
                            │ Bolt
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  MEMGRAPH + MAGE  (GCE VM now → GKE Autopilot later)         │
│    graph_algorithms  PageRank, Louvain/Leiden, centrality    │
│    memory/semantic   Fact, Preference, KNOWS, INTERESTED_IN  │
│    memory/episodic   PRECEDED_BY, CAUSED_BY, decay           │
│    memory/procedural Procedure, ProcedureStep                │
│    memory/vector     768-dim embeddings, semantic search     │
│    memory/retrieval  natural-language Q&A                    │
│  + Memgraph MCP server sidecar (Claude Desktop / agents)     │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  CLOUD RUN SERVICE — api/ (FastAPI, scales to zero)          │
│  query endpoints · /dashboard · /webhook/jira /webhook/github│
└──────────────────────────────────────────────────────────────┘

Cross-cutting: Secret Manager · Artifact Registry · Pub/Sub · Cloud Scheduler ·
Cloud Logging/Monitoring · budget alert.  All of it in Terraform.
```

Full detail, including the GCP resource inventory: `docs/ARCHITECTURE.md`.

---

## Repository Layout

```
meeting-notes-gcp/
├── CLAUDE.md                  ← this file, authoritative
├── AGENTS.md                  intent→skill map for non-Claude-Code agents
├── README.md
├── Makefile                   gcloud/terraform/test shortcuts
├── pyproject.toml
├── .env.example
├── docs/
│   ├── ARCHITECTURE.md        target architecture + GCP resources
│   ├── PHASE_PLAN.md          ← the build order. Execute this.
│   ├── MIGRATION_FROM_V5.md   module-by-module port map
│   ├── GOOGLE_AUTH.md         OAuth, the 7-day problem, refresh strategy
│   ├── DECISIONS.md           ADR log — append, never rewrite history
│   └── superpowers/specs/     design specs written during the build
├── terraform/
│   ├── *.tf
│   └── envs/{personal,onix}.tfvars
├── meeting_notes/             the installable package (all business logic)
│   ├── config.py              typed settings, the ONLY os.environ reader
│   ├── models.py              Pydantic v2 models
│   ├── utils.py               uuid5_id, with_retry, logging, json salvage
│   ├── db.py                  Cloud SQL — the ONLY file with SQL
│   ├── graph_client.py        Memgraph — the ONLY file with generic Cypher
│   ├── llm_client.py          vertex | gemini | fake seam
│   ├── classifier.py
│   ├── meeting_type_router.py
│   ├── person_resolver.py
│   ├── dedup.py
│   ├── extractor.py
│   ├── pipeline.py            classify→route→extract→graph→jira (ONE path)
│   ├── graph_algorithms.py    the ONLY file with MAGE CALL procedures
│   ├── jira_client.py         the ONLY file with Jira REST
│   ├── jira_pusher.py         ActionItems → Jira
│   ├── jira_sync.py           Jira status → graph (v5's jira_agent.py)
│   ├── access_control.py
│   ├── meeting_quality.py
│   ├── memory/{semantic,episodic,procedural,vector,retrieval}.py
│   ├── sources/{base,gmail,calendar,meet,jira}.py
│   └── dev_agent/              Phase 11, ADR-020 — autonomous ticket implementer
│       ├── lifecycle.py        state machine; SHIPPED is terminal
│       ├── guardrails.py       7 deterministic gates + independent LLM reviewer
│       ├── self_verify.py      cheap diff-vs-ticket scoring, never blocks review
│       ├── session_memory.py   resumable record per ticket, survives across attempts
│       ├── backend.py          coding-model routing — NOT llm_client, see Scope rules
│       ├── gemini_runner.py    spawns headless `gemini` as a subprocess
│       ├── git_ops.py          worktree per ticket
│       ├── github_client.py    read-only: find the PR the agent opened, fetch its diff
│       └── orchestrator.py     triage → process_ticket → poll_and_process
├── jobs/                      Cloud Run Job entrypoints — thin main() only
│   ├── ingest_{gmail,calendar,meet,jira}.py
│   ├── pipeline_drain.py
│   ├── nightly.py
│   ├── refresh_tokens.py
│   └── dev_agent_poll.py      Cloud Scheduler cadence, not an in-process scheduler
├── api/                       Cloud Run Service — FastAPI
│   ├── main.py
│   ├── routers/
│   └── static/dashboard.html
├── tests/
├── scripts/
│   └── auth_spike.py          Phase 0.5
└── sample_data/
```

`jobs/` and `api/` contain **entrypoints only**. Business logic lives in `meeting_notes/`.
If a job file grows past ~50 lines, the logic belongs in the package.

---

## Absolute Rules — Do NOT Violate

### Architecture
- DO NOT use Airbyte. Ingestion is our own connectors in `meeting_notes/sources/`.
- DO NOT use APScheduler or any in-process scheduler. Scheduling is Cloud Scheduler
  triggering Cloud Run Jobs. This is the main structural difference from v5.
- DO NOT create GCP resources by hand. Everything is Terraform.
- DO NOT hardcode a project ID, region, bucket name, or account email anywhere.
- DO NOT use Memgraph Cloud, Neon, Render, or Railway.
- DO NOT write to the v5 repo (`~/Desktop/airbyte-lm-studio-memgraph`) or the v3 repo
  (`shubham-gaur-x/airbyte-meeting`). Both are read-only reference.

### Module boundaries (these held perfectly in v5 — keep them)
- DO NOT put SQL outside `meeting_notes/db.py`.
- DO NOT put generic Cypher outside `meeting_notes/graph_client.py`. The memory modules may
  issue Cypher **only** for the node/edge types they own (listed below).
- DO NOT put MAGE `CALL` procedures anywhere except `meeting_notes/graph_algorithms.py`.
- DO NOT put Jira REST calls outside `meeting_notes/jira_client.py`.
- DO NOT read `os.environ` outside `meeting_notes/config.py`. Everything else imports settings.
- DO NOT instantiate an LLM client outside `meeting_notes/llm_client.py`. Every caller —
  extractor, memory modules, retrieval — goes through it.
- DO NOT call `memory/retrieval.py` from `pipeline.py`. Retrieval is query-time only.
- DO NOT write `MemorySession` nodes outside `memory/episodic.py`.

### Data and correctness
- DO NOT use `CREATE` in Cypher for unique nodes — always `MERGE`.
- DO NOT make sequential separate driver calls for related nodes — one ACID transaction.
- DO NOT use synchronous `requests` — always `httpx.AsyncClient`.
- DO NOT hardcode any secret or API key. Secret Manager, injected as env.
- DO NOT commit `.env`, a token file, a service-account key, or a `.tfvars` containing secrets.
- DO NOT derive a provenance node id anywhere except the one helper that owns it. Writer/reader
  id drift is a known past bug class in v5 — it cost real debugging time twice.

### Scope
- `dev_agent` moved from v2 to v1 (ADR-020) — Phase 11. `action_agent` stays deferred (see
  below).
- DO NOT auto-merge a pull request. Human review is the checkpoint. `dev_agent` opens PRs and
  never merges them; `CLOSED` is driven only by `/webhook/github`'s `pull_request.merged`
  event, i.e. a human actually merging.
- DO NOT let `dev_agent`'s coding-model selection go through `meeting_notes/llm_client.py`.
  That seam's contract (`chat_json`/`embed`, temperature 0, extraction-shaped) is for meeting
  data; invoking a headless coding agent is a different kind of call entirely — a subprocess
  with tool access, not a structured completion. `meeting_notes/dev_agent/backend.py` owns that
  routing, deliberately separate, exactly as v5 kept it separate.
- DO NOT add a second `dev_agent` coding backend (ADR-021). `gemini` is the only one:
  Claude on Vertex is a Cloud Marketplace purchase the GCP free-trial credit does not cover,
  the direct Anthropic API is not GCP-hosted, and local models are out of scope. A retired
  backend name must raise, never silently select something else.
- DO NOT let `meeting_notes/dev_agent/*` open its own Postgres connection or write its own SQL.
  `dev_agent_runs` and its queries live in `meeting_notes/db.py` like everything else — v5's
  `dev_agent/db.py` was a second SQL-owning module, which v6 does not permit.
- DO NOT let `dev_agent`'s poll loop run in-process. It is `jobs/dev_agent_poll.py`, a Cloud
  Run Job on a Cloud Scheduler cadence — v5 ran an `AsyncIOScheduler` inside its own FastAPI
  service, which is exactly the pattern the rest of this project removed.
- DO NOT treat `SHIPPED` as a non-terminal lifecycle state, and DO NOT let two places spell
  "terminal" independently. This is a confirmed-live v5 bug (ADR-020): `SHIPPED` was missing
  from `TERMINAL_STATES`, a second hardcoded exclusion list in `get_active_run()`'s SQL had
  drifted from it, and the poller resumed a shipped run on every single poll — 61 `AgentRun`
  nodes for one ticket in the live graph. The terminal set has exactly one definition, and
  `should_attempt()` is consulted before resuming an active run as a second, independent check.

---

## Deferred to v2 (do not build, but do not block)

`action_agent` (Airbyte Agents SDK deliverable drafter) is **out of scope for v1**. `dev_agent`
is no longer deferred — see Phase 11 and ADR-020.

One consequence you must respect while building v1:

- **`action_agent` may not survive at all.** It is built on the Airbyte Agents SDK, which is
  exactly the dependency v6 is walking away from. Re-evaluate its purpose in v2 rather than
  porting it reflexively.

---

## LLM Configuration

Default is **Vertex AI Gemini** in production. Three other backends exist for local
development and testing (ADR-014).

```
LLM_BACKEND=vertex          # vertex | gemini | fake
```

| Backend | Purpose |
|---|---|
| `vertex` | Production. GCP project with billing. |
| `gemini` | Direct AI Studio API key — no GCP project, no billing. Tier 1 of `docs/SETUP.md`. |
| `fake` | Replays recorded fixtures from `sample_data/llm_fixtures/`. No credentials, no network, deterministic. The tier-0 default and the test suite's mock. |

A `fake` fixture miss **raises**. It never falls through to `None` or a default —
a silently-wrong extraction is the worst outcome available here.

`meeting_notes/llm_client.py` owns every implementation behind one protocol:

```python
async def chat_json(system: str, user: str, *, temperature: float = 0.0) -> dict | None
async def embed(text: str) -> list[float] | None
```

Rules:
- Temperature is **0.0** for extraction. Always.
- Every module that needs inference imports `llm_client`. No module constructs its own client.
- Embeddings are **768-dimensional** in every backend, because the Memgraph vector indexes are
  configured for 768. Vertex `text-embedding-005` outputs 768 by default. Do not change the
  dimension without also migrating both vector indexes.
- Models wrap JSON in ```` ```json ```` fences despite instructions not to, and some
  sometimes emits the literal string `"null"` instead of a JSON null. Both defences (fence
  stripping, `_is_null_like`) are ported from v5 and must be kept — they were found by live
  testing, not by unit tests.

**Privacy claim.** v5's claim was "meeting data never leaves the Mac." v6's claim is
**"meeting data never leaves our GCP tenancy."** State it that way; do not overstate it.

---

## Graph Schema

Sourced from the **live v5 graph** (inspected 2026-08-13), which is more accurate than v5's
own documentation.

### Core
**Nodes:** `Meeting` · `Person` · `Organization` · `Topic` · `Decision` · `ActionItem`
**Edges:** `ATTENDED` · `DISCUSSED` · `PRODUCED` · `ASSIGNED_TO` · `WORKS_AT` · `FOLLOWS_UP` · `MENTIONS` · `MENTIONED_IN`

### Memory layer
**Nodes:** `Fact` · `Preference` · `Procedure` · `ProcedureStep` · `MemorySession`
**Edges:** `HAS_FACT` · `PREFERS` · `KNOWS{weight}` · `INTERESTED_IN{weight}` ·
`PRECEDED_BY{gap_days}` · `CAUSED_BY{confidence}` · `FOLLOWS_PROCEDURE{confidence}` ·
`HAS_STEP` · `NEXT_STEP` · `ACCESSED`

### Review / governance
**Nodes:** `PersonReview` · `Blocker`
**Edges:** `NEEDS_REVIEW` · `RAISES_BLOCKER`

### Provenance (schema in v1, writers in v2)
**Nodes:** `Ticket` · `PullRequest` · `AgentRun` · `Commit` · `FileChange`
**Edges:** `TICKETED_AS` (ActionItem→Ticket) · `IMPLEMENTS` (AgentRun→Ticket) ·
`PRODUCED` (AgentRun→PullRequest) · `FOLLOWS_UP_ON` (AgentRun→Meeting) ·
`RESOLVED_BY` (Ticket→PullRequest, on merge) · `CONTAINS` (PullRequest→Commit) ·
`MODIFIES` (Commit→FileChange)

The edge vocabulary is deliberately aligned with Matteo's engagement ontology
(`~/Desktop/ontology`) so the graph is legible to anyone who knows it: his DevLog `implements`
a Feature and `follows_up_on` a Meeting; our `AgentRun` is the same bridge concept.

### Invariants
- Every node has `id` (deterministic `uuid5_id`), `created_at`, `updated_at` (ISO 8601).
- `Meeting` additionally has `date`, `title`, `kind`, `platform`, `duration_minutes`, `summary`.
- `Person.tracked` (default `false`) is the governance gate. Per-person analytics — PageRank,
  centrality, any leaderboard — **must** filter on `tracked = true`. Aggregates are the default;
  naming individuals is opt-in.
- `Topic` MERGE key is **lowercased and stripped**. Using raw case fragmented single topics
  across multiple nodes in v5 and silently understated every insight query.
- `ActionItem.confidence` and `Decision.confidence` gate side effects. Below
  `JIRA_CONFIDENCE_THRESHOLD`, write the node with `jira_status = needs_review` and surface it
  in the review queue instead of creating a Jira ticket.

---

## Coding Conventions

- Python 3.11+, type hints on **all** function signatures.
- Pydantic v2, `model_config = ConfigDict(extra="ignore")`.
- `@with_retry(max_attempts=3, base_delay=2.0)` on every external call.
- Structured logging with `structlog`. Every log line carries `source`, `meeting_id`, `step`.
  **Never pass `event=` as a kwarg** — it collides with structlog's reserved message field and
  raises `TypeError` at call time. Use `github_event=`, `source_event=`, etc. This was a real
  production 500 in v5.
- `httpx.AsyncClient` for all HTTP.
- `uuid5_id(namespace, value)` for every deterministic id. Re-derive identically everywhere.
- Tests are mocked — the suite must run with no live GCP, no database, no LLM. v5 achieved this
  for 363 tests; do not regress it. A test requiring live credentials is a broken test.
- One test file per phase, named for what it proves. Follow v5's `test_phaseNN_*.py` convention.

---

## Environment Variables

Full annotated list in `.env.example`. Summary:

```env
# GCP
GCP_PROJECT_ID=                  # never hardcoded in source
GCP_REGION=us-central1

# LLM
LLM_BACKEND=vertex               # vertex | gemini | fake
GEMINI_API_KEY=                  # AI Studio key — tier 1 only, no GCP project needed
VERTEX_CHAT_MODEL=gemini-3.7-flash   # confirm current name at build time — they change
VERTEX_EMBEDDING_MODEL=text-embedding-005
VERTEX_LOCATION=global           # ADR-021: Gemini 3.x is served ONLY from `global`

# Cloud SQL
POSTGRES_HOST=
POSTGRES_PORT=5432
POSTGRES_DB=meeting_memory
POSTGRES_USER=
POSTGRES_PASSWORD=               # Secret Manager
CLOUD_SQL_CONNECTION_NAME=       # project:region:instance

# Memgraph
MEMGRAPH_HOST=
MEMGRAPH_PORT=7687
MEMGRAPH_USER=
MEMGRAPH_PASSWORD=               # Secret Manager

# Google Workspace OAuth (see docs/GOOGLE_AUTH.md)
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=      # Secret Manager
GOOGLE_REFRESH_TOKEN=            # Secret Manager — expires every 7 days on personal GCP
GOOGLE_WORKSPACE_USER=           # shubham.gaur@onixnet.com
MEET_PUBSUB_SUBSCRIPTION=

# Jira
JIRA_ENABLED=true
JIRA_DOMAIN=
JIRA_EMAIL=
JIRA_API_TOKEN=                  # Secret Manager
JIRA_PROJECT_KEY=SCRUM
JIRA_BOARD_ID=1
JIRA_ISSUE_TYPE=Task
JIRA_CONFIDENCE_THRESHOLD=0.6
JIRA_DEDUP_ENABLED=true
JIRA_DEDUP_THRESHOLD=0.9

# Governance
FACT_MIN_CONFIDENCE=0.5
PERSON_ROSTER_PATH=

# Dev agent (Phase 11 — ADR-020, ADR-021)
DEV_AGENT_LLM_BACKEND=gemini     # the only valid value; see ADR-021
DEV_AGENT_GEMINI_MODEL=gemini-3-pro-preview
DEV_AGENT_GEMINI_LOCATION=global
DEV_AGENT_GEMINI_CLI_HOME=       # config dir the agent OWNS — never the developer's ~/.gemini
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_TOKEN=                    # Secret Manager

# Service
LOG_LEVEL=INFO
GITHUB_WEBHOOK_SECRET=           # Secret Manager
```

---

## Where To Start

1. Read `docs/PHASE_PLAN.md` end to end.
2. Read `docs/MIGRATION_FROM_V5.md` before porting any module — it lists what changes and,
   more importantly, the bugs found live in v5 that must not be reintroduced.
3. Read `docs/GOOGLE_AUTH.md` before any OAuth work.
4. Append to `docs/DECISIONS.md` whenever you make a call that a future reader would question.

**Phase 0.5 (the auth spike) gates everything.** If the Onix Workspace admin blocks unverified
third-party apps, the entire ingestion design changes. Do not build Terraform, connectors, or
anything else until a real token has been held in hand.

---

## graphify

This repo is maintained under graphify, same as v5.

```bash
graphify .           # first run
graphify . --update  # after each phase
```

Commit `graphify-out/GRAPH_REPORT.md` and `graphify-out/graph.json`.
**Do not commit `graphify-out/cache/`** — it is already in `.gitignore`. v5 tracked ~180 cache
files by accident; do not repeat that.

## Claude Code Plugins

```
/plugin install superpowers@claude-plugins-official
/plugin marketplace add aneja5/forge-skills
/plugin install forge-skills@forge-skills
```

Superpowers drives brainstorm → spec → TDD → review. forge-skills provides `/architect`,
`/plan`, `/build`, `/review`, `/ship`. v5's design specs came out noticeably better for having
used them — write a spec into `docs/superpowers/specs/` before each substantial phase.
