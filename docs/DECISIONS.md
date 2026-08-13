# Decision Log

Append-only. Never rewrite an entry — supersede it with a new one and mark the old one
`Superseded by ADR-NNN`. A decision recorded with its rejected alternatives is worth ten times
one recorded as a conclusion.

Format: context → decision → consequences → alternatives rejected.

---

## ADR-001 — Fresh repository, deliberate port

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5 (`airbyte-lm-studio-memgraph`) is a working system with 363 passing tests, but
it is shaped end to end by two assumptions that don't survive a move to GCP: everything runs on
one laptop, and Airbyte handles ingestion.

**Decision.** New repository, new git history. Port modules across one layer at a time,
justifying each. v5 becomes read-only reference.

**Consequences.** Slower than refactoring in place, and the test suite has to be re-established
phase by phase rather than staying green from minute one. In exchange, no Airbyte assumption
survives by accident, and every carried-over file has been consciously chosen.

**Rejected:** clone-and-refactor (inherits the local-first shape, and those assumptions become
invisible once they're already in the tree); full rewrite (throws away extraction prompts,
Cypher, and tests that took real live debugging to get right).

---

## ADR-002 — Vertex AI Gemini as the default LLM, behind a swappable seam

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5's hardest rule was that extraction is always local LM Studio. That rule served
a privacy claim ("never leaves the Mac") and a cost constraint. Neither survives unchanged on
GCP.

**Decision.** `meeting_notes/llm_client.py` owns both backends behind one protocol, selected by
`LLM_BACKEND=vertex|lmstudio`. Vertex is the default.

**Consequences.** The privacy claim is restated as "never leaves our GCP tenancy" — still
defensible, and closer to what an enterprise buyer actually asks about. Local development stays
free and the fully-local demo remains possible. Cost: one abstraction layer, roughly one file.

Vertex `text-embedding-005` outputs 768 dimensions by default, which matches the existing
Memgraph vector index configuration exactly — so `vector_memory` needs an endpoint change, not
a reindex. (Verified 2026-08-13.)

**Rejected:** hard-swap to Gemini with no seam (loses the free local path for no real saving);
self-hosting Gemma on GKE with vLLM (a GPU node would be the single largest line item, to serve
a model measurably worse at structured JSON extraction than Gemini).

---

## ADR-003 — Keep Memgraph; reject Spanner Graph

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** Spanner Graph is the GCP-native managed graph database, and choosing it would make
the "GCP-native" claim maximal.

**Decision.** Keep Memgraph + MAGE, self-hosted.

**Consequences.** We own a stateful VM and its backups. In exchange we keep ~99 Cypher call
sites, the whole MAGE algorithm suite (PageRank, Louvain, Leiden, betweenness, WCC), the vector
index, and the Memgraph MCP server.

**Rejected:** Spanner Graph. GQL is not openCypher, so `graph_client.py` is a rewrite; no MAGE,
so every graph algorithm — the actual differentiator of this project — is reimplemented by
hand; no in-engine vector index; and no MCP server, which is one of the most compelling parts
of the demo.

---

## ADR-004 — Memgraph on a GCE VM first, GKE later

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** Memgraph needs persistent storage and always-on availability, so Cloud Run is out.
GCE VM or GKE Autopilot. The personal-billing phase is cost-sensitive.

**Decision.** GCE VM now. Revisit GKE when the project moves to Onix billing.

**Consequences.** No autoscaling, and we manage a VM. Meaningfully cheaper.

This is deliberately a **reversible** decision: the application connects over
`bolt://host:7687` either way and no application code can tell the difference. Do not spend
time agonising over it.

---

## ADR-005 — Replace APScheduler with Cloud Scheduler + Cloud Run Jobs

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5's `transform_service` registers ten APScheduler jobs at startup. Deployed
unchanged to Cloud Run this forces `min-instances=1`, paying for an always-on container while
getting none of the platform's benefits — and keeping APScheduler's failure mode, where an
exception inside a tick is logged and then forgotten with no retry and no alert.

**Decision.** Every scheduled unit becomes a Cloud Run Job triggered by Cloud Scheduler. The
Cloud Run *service* keeps only genuinely request-driven work: queries, dashboard, webhooks.

**Consequences.** This is the largest structural difference between v5 and v6 and it touches
the shape of the whole repo — hence `jobs/` as a top-level directory. We gain per-execution
logs, automatic retries, execution history, and failure alerting. We take on a new problem:
concurrent executions can overlap, which v5 never had to handle. Addressed by ADR-006.

---

## ADR-006 — Claim rows with `SELECT ... FOR UPDATE SKIP LOCKED`

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5 ran exactly one container, so reading rows `WHERE processed = false` was safe.
Cloud Run Jobs can overlap: a slow execution may still be running when Scheduler fires the next
one.

**Decision.** Claim rows inside a transaction with `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n`.
Combined with deterministic `uuid5_id` node ids and mandatory `MERGE`, reprocessing is
idempotent.

**Consequences.** Jira issue creation remains the one genuinely non-idempotent side effect and
must be gated on `ActionItem.jira_key IS NULL` inside the transaction that sets it. With that,
Cloud Run Job retries are safe to enable.

---

## ADR-007 — Build our own connectors; remove Airbyte

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5 used Airbyte Cloud with a `bore`/`ngrok` tunnel so Airbyte could reach a
Postgres running on the laptop. The tunnel existed only because the destination was local.

**Decision.** One Cloud Run Job per source behind a `Source` protocol. Start with scheduled
polling; upgrade Gmail and Calendar to `users.watch` → Pub/Sub push as a later phase.

**Consequences.** We own connector code, incremental watermarks, and OAuth token lifecycle. In
exchange: no tunnel, no third-party dependency, no per-connector cost, and full control of the
sync cadence. Precedent already exists in-house — v5's `meet_ingest.py` is a hand-written
connector and the simplest ingestion path in that repo.

**Rejected:** Dataflow/Datastream (overkill and expensive for three low-volume sources);
keeping Airbyte Cloud (reintroduces the exact external dependency this rearchitecture removes).

---

## ADR-008 — Defer `dev_agent` and `action_agent` to v2, but ship the provenance schema in v1

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5 has two autonomous agents. Porting them alongside the pipeline would roughly
double v1 and delay anything demo-able.

**Decision.** v1 is ingestion → extraction → graph → intelligence → API/dashboard. Both agents
are v2. **But** the provenance node and edge types (`Ticket`, `PullRequest`, `AgentRun`,
`Commit`, `FileChange`, `Blocker` and their edges) are created in v1's schema setup, and
`/webhook/github` exists in v1.

**Consequences.** Provenance cannot be backfilled — a merge that happens before the schema
exists is lost forever. Shipping the schema early costs almost nothing and preserves the
option.

Separately: `action_agent` is built on the Airbyte Agents SDK, which is exactly the dependency
v6 is walking away from. Re-evaluate whether it should exist at all in v2 rather than porting
it reflexively.

---

## ADR-009 — Personal GCP project now, Onix Workspace data throughout

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** Infrastructure runs in Shubham's personal GCP project until an Onix project is
approved. The data being read belongs to the Onix Workspace account throughout.

**Decision.** Proceed with the split. Treat portability as a first-class constraint:
everything in Terraform, no hardcoded project IDs or account emails, all secrets in Secret
Manager, migration to Onix reduced to a new `.tfvars` plus re-consent.

**Consequences — accepted knowingly:**

1. The OAuth client must be **External** user type (the personal GCP project is outside the
   Onix Workspace org). External + Testing publishing status means **refresh tokens expire
   every 7 days**. Gmail scopes are restricted scopes, so publishing to Production requires
   Google verification plus a third-party security assessment — not viable here. Mitigated
   by a scheduled refresh job and an alert; permanently fixed by moving to Onix, where the
   client can be **Internal** (no verification, no expiry).
2. The Onix Workspace admin may block unverified third-party apps outright. This is a hard
   stop, so Phase 0.5 exists to find out before anything is built on top of it.
3. Onix meeting content will sit in a personal GCP project. Mitigations: own mailbox only,
   short retention on raw tables, and raising it proactively when requesting the Onix project
   rather than being asked about it afterwards.

---

## ADR-010 — Collapse the three duplicated pipeline paths into one

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5's `graph_builder.py` has `process_email`, `process_calendar_event`, and
`process_transcript` — three functions that are roughly 90% identical, with the entire
nine-call memory-enrichment block copy-pasted verbatim three times. Any change to the
enrichment sequence has to be made in three places, and drift between them is invisible.

**Decision.** One `pipeline.process(record, adapter)`. Each source contributes a small adapter
supplying the extraction text, the context dict, and the routing inputs.

**Consequences.** Adding a fifth source becomes an adapter, not a fourth copy of the pipeline.
Slight indirection cost; worth it.

---

## ADR-011 — `config.py` is the only reader of `os.environ`

**Date:** 2026-08-13 · **Status:** Accepted

**Context.** v5 reads `os.environ` in a dozen modules, including lambdas evaluated at call time
in `dev_agent/orchestrator.py`. That pattern made a real test-isolation bug possible — a test
silently depended on an ambient environment variable being unset — and it makes the full
configuration surface impossible to see in one place.

**Decision.** A single typed settings object in `meeting_notes/config.py`. Every other module
imports it. Nothing else touches `os.environ`.

**Consequences.** Configuration errors surface at startup rather than at first use. Tests
override a settings object instead of mutating global environment state. Cloud Run injects
Secret Manager values as environment variables, which `config.py` reads once.

---

## Template

```
## ADR-NNN — <short imperative title>

**Date:** YYYY-MM-DD · **Status:** Proposed | Accepted | Superseded by ADR-NNN

**Context.** What forced a choice.

**Decision.** What we chose.

**Consequences.** What this costs and what it buys. Include the bad parts.

**Rejected:** alternatives, each with the reason.
```
