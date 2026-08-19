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

## ADR-012 — Phase 0.5 auth spike: passed, no admin allowlisting needed

**Date:** 2026-08-19 · **Status:** Accepted

**Context.** Phase 0.5 gates every later phase — see ADR-009's risk register, item 2: the Onix
Workspace admin might block an unverified third-party OAuth app outright, which would force a
different ingestion design before any of it got built. The only way to know was to run
`scripts/auth_spike.py` against a real OAuth client and a real Workspace account.

The OAuth client lives in a **new personal-account GCP project**, `meeting-notes-gcp-personal`
(under `shubham.gaur.x@gmail.com`), not the pipeline's eventual home. This is the split ADR-009
already commits to: infrastructure project and data-source account are deliberately different
accounts. The pre-existing `ehole-benchmark-temp-z8s8` project was ruled out — unrelated,
named for other work — and `airbyte-meeting` (v3) was never touched, per `CLAUDE.md`'s
do-not-touch rule.

The consent screen was configured External + Testing, with the four scopes
(`gmail.readonly`, `calendar.readonly`, `meetings.space.readonly`, `pubsub`) and
`shubham.gaur@onixnet.com` added as a test user — Google's newer "Google Auth Platform" console
UI splits this across separate **Audience** (publishing status, test users) and **Data Access**
(scopes) pages rather than one linear wizard, which is worth knowing if this is ever redone
from scratch.

**Decision.** Ran `make auth-spike` against the real client and the real Onix account. Result:

```
[PASS] Gmail     reachable (1 record(s))
[PASS] Calendar  reachable (1 record(s))
[PASS] Meet      reachable (1 record(s))
```

- **No Workspace admin allowlisting was needed.** Consent completed on the first attempt, past
  the expected "Google hasn't verified this app" warning (External + Testing), with no
  additional block from the Onix admin console. ADR-009's worst-case risk did not materialize.
- **Meet transcription is enabled on the Onix tenant.** `conferenceRecords.list` returned a real
  record, not just a reachable-but-empty 200. The no-op fallback for `sources/meet.py` described
  in `docs/GOOGLE_AUTH.md` §6 is available if ever needed, but Phase 5 can build the transcript
  path as a first-class source from the start rather than assuming degradation.
- Refresh token issued 2026-08-19, on the standard 7-day External+Testing clock (ADR-009 risk
  item 1). Stored locally at `token.json`, mode 0600, gitignored — Secret Manager storage is
  Phase 1, per `docs/GOOGLE_AUTH.md` §5.4.

**Consequences.** Phase 0.5's gate is cleared. The ingestion design in `docs/ARCHITECTURE.md`
stands as written — no redesign forced by admin policy. Phase 0.6 (the clone-and-run
reproducibility work, already specced) can proceed, followed by Phase 1.

The 7-day token lifetime is still live until the Onix project migration makes the client
Internal (ADR-009's stated fix). Until then, `--reconsent` is a manual weekly action — Phase 5's
`jobs/refresh_tokens.py` automates the *access*-token refresh, but cannot extend a refresh
token's own 7-day expiry; only re-consent or moving to an Internal client does that.

**Rejected:** none — this is a factual outcome, not a design choice between alternatives.

---

## ADR-013 — A three-tier reproducibility contract, with the OAuth console step accepted as permanently manual

**Date:** 2026-08-19 · **Status:** Accepted

**Context.** Nothing in this repository could be run by anyone who is not Shubham. The
pipeline needs a GCP project with billing, a Workspace tenant whose admin permits an
unverified OAuth client, a Jira instance, and either Vertex AI or a multi-gigabyte local
model. Each is a wall, and the first is hit before any of the project's actual value is
visible. That is bad for a reviewer, bad for a future teammate, and bad for the author six
months from now on a new laptop.

**Decision.** Three tiers, each one command, each additive, each honest about what it proves:

| Tier | Command | Credentials | Proves |
|---|---|---|---|
| 0 | `make demo` | none | pipeline, graph writes, algorithms, memory layers, API, dashboard |
| 1 | `make demo LLM=gemini` | one AI Studio key | genuine LLM extraction and embeddings |
| 2 | `make deploy ENV=<env>` | GCP + Workspace + Jira | the deployed product |

`scripts/doctor.py` is the entry point for all three: it reports what is missing for the
requested tier and attaches a runnable command or a document anchor to every failure.

**And an explicit non-goal: Terraform will never create the OAuth consent screen or client.**
Google exposes no usable API for an External-type consent screen or a Desktop client with
restricted Gmail scopes — `google_iap_brand` and `google_iap_client` cover neither case. This
is accepted as permanently manual and *detected and explained* rather than papered over.
Pretending otherwise would produce a `terraform apply` that fails confusingly.

**Consequences.** A stranger can evaluate the project offline in about ten minutes with no
account anywhere. The local stack doubles as the test harness for Phases 3–8, so it is
exercised continuously rather than rotting between now and Phase 9 — which is the standing
exit criterion added to every remaining phase.

The cost is a docker-compose path that production never uses, and the risk that a green tier 0
is misread as evidence that tier 2 works. Both `SETUP.md` and `doctor` state per-tier scope
explicitly; tier 0 never claims to prove anything about GCP.

**Rejected:**
- *GCP-deploy only.* Simpler — one path, the real one — but nobody can evaluate the project
  without a GCP account, billing, and a Workspace tenant. That is the problem, not a solution.
- *Local demo only.* Least work, but the repo's headline claim is GCP-native and it would stay
  unclonable indefinitely.

---

## ADR-014 — A `fake` LLM backend that replays fixtures, and a `gemini` backend for tier 1

**Date:** 2026-08-19 · **Status:** Accepted

**Context.** `CLAUDE.md` originally sanctioned two backends, `vertex` and `lmstudio`. Neither
is usable by a stranger: Vertex needs a GCP project with billing, and LM Studio needs a
multi-gigabyte model download and realistically a capable Mac. Tier 0 promises a working
pipeline with **no credentials at all**, and neither existing backend can deliver that.

**Decision.** Two more backends behind the same unchanged `llm_client.py` protocol
(`chat_json`, `embed`), keeping it the only module that constructs an LLM client:

- **`fake`** — replays recorded responses from `sample_data/llm_fixtures/`, keyed by a hash of
  (system prompt + user content + temperature). Deterministic, offline, instant. The tier-0
  default and the mock the test suite needs anyway.
- **`gemini`** — direct AI Studio API key. No GCP project, no billing. Tier 1.

**A fixture miss raises.** It never falls through to `None`, a default, or an empty
extraction. A prompt edit changes the hash and therefore produces a loud, immediate failure
rather than a silently-wrong result. `scripts/record_fixtures.py` regenerates against a real
backend, so a deliberate prompt change is one command rather than hand-authored JSON.

Embeddings stay **768-dimensional in every backend, `fake` included**, because both Memgraph
vector indexes are configured for 768.

**Consequences.** `make demo` works offline on a clean clone, and the test suite gets a
principled mock instead of scattered ad-hoc patches. Four backends is more surface to keep
working, and fixtures must be re-recorded whenever a prompt changes deliberately.

The raise-on-miss choice will occasionally be annoying — someone will tweak a prompt and get a
hard failure. That is the intended trade. `CLAUDE.md`'s existing defences (`_is_null_like`,
fence stripping) exist precisely because quiet LLM misbehaviour cost real debugging time in
v5; a silently-wrong extraction is the worst outcome available here.

**Rejected:**
- *Gemini-only for the demo.* One env var is a small ask, but it is not zero, it is not
  offline, free-tier rate limits make a first run flaky, and a separate mock would still be
  needed for the tests.
- *LM Studio only, as v5 did.* No new backend and no ADR needed, but a several-gigabyte
  download is a far steeper wall than "put in your credentials."

---

## ADR-015 — `db.py` selects its connection mode on configuration

**Date:** 2026-08-19 · **Status:** Accepted

**Context.** Tier 0 runs against a plain Postgres container; tier 2 runs against Cloud SQL
through the Python connector. These acquire connections differently. Left undecided, the
question surfaces during Phase 3 — after `db.py` and possibly the connectors already exist.

**Decision.** `db.py` branches on configuration: `CLOUD_SQL_CONNECTION_NAME` set → Cloud SQL
connector; otherwise a plain DSN from `POSTGRES_HOST`. Decided now, implemented in Phase 3.

**All SQL stays inside `db.py`.** This is a connection-acquisition branch, not a second query
path — every query is written once and runs unmodified against both.

**Consequences.** The same code path is exercised locally and deployed, so local testing is
evidence about production rather than about a parallel implementation. One conditional in
connection setup, and `.env.example` must document that a blank `CLOUD_SQL_CONNECTION_NAME`
means local — which it now does.

Deciding it now follows the same reasoning `PHASE_PLAN.md` applies to the `StagedRecord`
question in Phase 2: a data-layer shape settled after the connectors exist is far more
expensive to change than one settled before.

**Rejected:**
- *Cloud SQL connector only, with a local proxy.* Keeps one code path, but forces every
  cloner to install and run `cloud-sql-proxy` — a credentialed GCP tool — which defeats
  tier 0's entire premise.
- *Two separate modules.* Would put SQL outside `db.py`, violating the module boundary in
  `CLAUDE.md` that held perfectly in v5.

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
