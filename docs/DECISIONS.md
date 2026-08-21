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

## ADR-016 — Ephemeral compute, durable storage: the system is up only when syncing

**Date:** 2026-08-19 · **Status:** Accepted

**Context.** This is a trial. The owner will not touch it for weeks at a stretch and only
wants it "on" for the duration of a sync session — build once, test end to end, then go quiet
for a month, then sync again on demand. `ARCHITECTURE.md` §7 and §8 already identify the two
always-on resources that dominate cost: the Cloud SQL instance and the Memgraph GCE VM.
Verified against the live Cloud Billing Catalog API (not estimated): `e2-medium` is
$0.021812/vCPU-hr + $0.002924/GiB-hr ≈ $40/mo if left running continuously; `db-f1-micro` is
$0.018/hr ≈ $13/mo. Both are irrelevant if the resources simply don't exist between sessions.
Cloud Run jobs/services, Secret Manager, Artifact Registry, and Pub/Sub are already
usage-priced or near-zero idle and need no special handling.

**Stopping instead of destroying does not work.** `gcloud sql instances patch
--activation-policy=NEVER` halts Cloud SQL billing, but Google auto-restarts a stopped
instance after ~7 days for maintenance — silently resuming the bill partway through a month of
inactivity. There is no equivalent forced-restart on a stopped GCE VM, but the asymmetry means
"stop everything" is not a single reliable pattern. Destroying is the only mode with a
guaranteed $0 idle cost for both resources, and it is also literally the Phase 1 exit criterion
already on the books: "`terraform destroy` then `apply` reproduces the environment exactly."
Treating that as the normal weekly-to-monthly workflow rather than a one-time validation is a
small reframing, not new scope.

**Decision.** Split every GCP resource into two tiers:

- **Durable** (created once, never destroyed by the normal lifecycle): the GCS backup bucket,
  Secret Manager secrets, Artifact Registry, the Pub/Sub topic/subscription, service accounts
  and IAM, the budget alert. All cheap-to-free while idle.
- **Ephemeral** (created at the start of a sync session, torn down at the end): the Cloud SQL
  instance and the Memgraph GCE VM (+ its attached disk).

Two new Makefile targets own the lifecycle:

- `make sync-up ENV=personal` — `terraform apply`, which recreates the Cloud SQL instance
  (importing the latest export from the GCS bucket if one exists) and the Memgraph VM (its disk
  created `source_snapshot = latest` if a snapshot exists). Then `make doctor TIER=2`, which
  will report the OAuth refresh token as `expired` — expected, since any gap over 7 days
  outlives it. The runbook step here is `make auth-spike ARGS=--reconsent`, not a bug to chase.
- `make sync-down ENV=personal` — `gcloud sql export sql` to the GCS bucket, a
  `google_compute_snapshot` of the Memgraph disk, then `terraform destroy` scoped to the
  ephemeral tier only.

Data survives the gap through the export/snapshot, not through the resource staying up.

**Consequences.** Every sync session pays a bring-up cost — Cloud SQL import and a fresh VM
boot before anything can run — and `sync-down` must actually complete before walking away, or
the next month's bill is the full always-on rate. A `sync-down` skipped or interrupted is a
silent cost leak, so `make doctor` should grow a tier-2 check that warns if the ephemeral
resources are currently up (Terraform state has them) with no active session, once state
inspection is available (Phase 1 implementation detail, not part of this decision). Backup and
restore now have to work correctly, not just exist — an export that silently fails means the
next `sync-up` starts from an empty graph. The OAuth 7-day expiry (`GOOGLE_AUTH.md`, ADR-012)
compounds with this: a monthly cadence means re-consent is *every* session, not an occasional
inconvenience, so `docs/SETUP.md`'s tier-2 walkthrough must present it as a normal step of
`sync-up`, not a troubleshooting footnote.

**Rejected:**
- *Stop, don't destroy.* Simpler — no export/import, no snapshot/restore — but Cloud SQL's
  forced restart after 7 days breaks the "$0 for a month" guarantee outright, and relying on it
  "mostly working" is worse than a design that is honest about the tradeoff.
- *Leave Cloud SQL running, only tear down Memgraph.* Cloud SQL is the more expensive of the
  two only at larger tiers; at `db-f1-micro` the two are close enough ($13 vs $40/mo) that
  half-measures don't earn back the added complexity of an asymmetric lifecycle.
- *Smaller always-on tiers instead of teardown.* Even the smallest viable tiers still bill
  24/7. For a system touched a few hours a month, on-demand beats resized-but-permanent on
  cost by an order of magnitude.

---

## ADR-017 — Phase 1 validated live: the sync lifecycle works, and costs ~11 minutes to start

**Date:** 2026-08-20 · **Status:** Accepted

**Context.** ADR-016 committed to destroying the Cloud SQL instance and Memgraph VM
between sessions. That decision was made on price-list arithmetic. It was never run.
Phase 1's exit criterion demanded proof that data actually survives the gap — a marker
record written before `sync-down` and read back after the next `sync-up` — because
"destroy then apply worked" only proves Terraform is deterministic and says nothing
about the data.

**Outcome: the lifecycle works.** A full cycle was executed against real infrastructure:
durable apply → `sync-up` → write markers to both stores → `sync-down` → verify $0 →
`sync-up` → **both markers returned with their original timestamps**
(`2026-08-20T02:19:19` in Memgraph, `2026-08-20T02:21:04` in Postgres). Cloud SQL and
Compute both reported `Listed 0 items` while torn down.

**Measured timings** (from Cloud SQL operation logs and GCE serial console, not estimated):

| Step | Duration |
|---|---|
| `sync-up` — Cloud SQL instance creation | **11m05s** cold, **10m46s** restoring |
| `sync-up` — Memgraph VM boot to serving Bolt | ~2m13s |
| `sync-down` — export + verify + snapshot + verify | ~25s |
| `sync-down` — Cloud SQL deletion | ~1m50s |
| **Full `sync-up`** | **~11–12 min**, almost entirely Cloud SQL provisioning |
| **Full `sync-down`** | **~3 min** |

**Consequences.** A sync session costs about **eleven minutes to start and three to
end**. At the monthly cadence this project is built for that is a fair trade for $0
idle; at a daily cadence it would be intolerable. The number is worth revisiting only
if the cadence changes — and the fix would be scoped precisely, because the long pole
is *entirely* Cloud SQL instance provisioning. The Memgraph VM is serving Bolt in about
two minutes and is not the problem. Options if it ever matters: keep Cloud SQL running
and tear down only the VM (~$13/mo), or move staging to something with faster cold
start.

**The safety property held in production, unrehearsed.** One `sync-down` failed at the
snapshot step (a missing `--zone`). The export had already succeeded, the snapshot had
not, and **`terraform destroy` correctly never ran** — the tier stayed up and the error
said so. That left an orphan export in the backup bucket
(`meeting-memory-20260820t022231z.sql.gz`) with no matching snapshot. The bucket's
90-day lifecycle rule reclaims it, so it is untidy rather than a leak, but a partially
completed `sync-down` is now a known and observed state, not a theoretical one.

**Four real bugs were found by running it that review had not caught** (commit
`7972f9a`), every one a wrong assumption about how a Google API behaves:

1. The `google` provider needs `user_project_override` + `billing_project`, or
   `billingbudgets.googleapis.com` rejects user ADC credentials outright.
2. `cloudresourcemanager.googleapis.com` and `iam.googleapis.com` were missing from the
   required-APIs list. Service-account *creation* succeeded without the latter; the
   subsequent *read* of the same resource 403'd.
3. `gcloud sql export` writes to GCS as the **Cloud SQL instance's own** service
   account, not the calling identity. That account is regenerated on every instance
   creation, so the bucket grant has to live in the ephemeral module bound to
   `service_account_email_address` — a static durable-tier binding would go stale on
   the first teardown.
4. `gcloud storage ls` on an empty prefix exits **1** with "matched no objects", not 0
   with empty output. The unit test had mocked exit 0, so it passed while the first
   real `sync-up` failed. `gcloud compute disks snapshot` likewise needs an explicit
   `--zone`.

Bug 4 is the instructive one: a mock encoded an assumption about a tool's behaviour,
the assumption was wrong, and the test therefore certified the bug. Every fix now
carries a test that would have caught it, and the mocks match observed CLI behaviour
rather than expected behaviour.

**Rejected:**
- *Declaring Phase 1 done on a green `terraform apply`.* It would have shipped all four
  bugs above, since none of them appear until the second half of a full cycle.
- *Skipping the marker records.* A destroy/apply that reproduces empty resources proves
  Terraform is deterministic and proves nothing about backup and restore, which is the
  only thing standing between a teardown and permanent data loss.

---

## ADR-018 — One `StagedRecord` with a JSONB payload, not four typed raw tables

**Date:** 2026-08-20 · **Status:** Accepted

**Context.** v5 stages four near-identical models — `RawEmail`, `RawCalendarEvent`,
`RawMeetTranscript`, `RawJiraIssue` — each with its own table and each carrying a
`source_table` string so downstream code can tell them apart. The shapes overlap heavily
(`id`, `source_id`, `processed`, plus a body-ish text field and some context), and the
differences are exactly the parts only that source's adapter cares about.
`MIGRATION_FROM_V5.md` §3 flags this as a decision to make **before** `db.py`, `models.py`,
and the connectors exist, because changing it afterwards means touching all three.

**Decision.** One staging table:

```
StagedRecord:
    id, source_id, source_type, payload (JSONB), fetched_at, processed
```

A per-source adapter parses `payload` into the corresponding typed Pydantic model and
produces the extraction text and context. **The typed models survive** — `RawEmail` and
friends remain the adapters' parse targets, so validation stays exactly as strict as v5's.
This is a change to how rows are *stored*, not a loss of typing.

**Consequences.** One table means one `SELECT ... FOR UPDATE SKIP LOCKED` claiming query
rather than four or a UNION, which is what ADR-006 wants, and one drain path, which is what
ADR-010 wants. Adding a fifth source later is a new adapter and no migration at all.

The cost is real and worth stating plainly: `payload` is opaque to SQL. "Every email from
X" needs JSON operators or a graph query rather than a plain `WHERE`. That is acceptable
here because **nothing queries staging analytically** — staging exists to be drained into
Memgraph, and the graph is where questions get asked. If that assumption ever breaks, the
fix is to promote specific fields into real indexed columns, which is an additive migration
rather than a redesign.

Validation also moves from write time to read time. A malformed payload is caught by the
adapter during the drain, not by Postgres on insert. The drain already has to handle a
record it cannot process, so this adds no new failure mode — but it does mean connectors
must not assume the database will reject bad data for them.

`AirbyteWebhookPayload` is deleted outright rather than ported (`MIGRATION_FROM_V5.md` §4).

**Rejected:**
- *Keep the four typed tables.* Strict SQL columns and directly queryable fields, but it
  carries v5's overlapping shapes and the `source_table` field forward unchanged, needs a
  migration per new source, and forces the claiming query to become four queries or a UNION
  — pushing against both ADR-006 and ADR-010 for a queryability benefit nothing currently
  uses.
- *Hybrid: JSONB plus promoted columns.* The right answer *if* a concrete query needs a
  column, and reachable additively later. Doing it now would mean guessing which fields
  matter across four sources before a single connector exists.

---

## ADR-020 — `dev_agent` moves from v2 to v1, ported now rather than deferred

**Date:** 2026-08-20 · **Status:** Accepted

**Context.** `CLAUDE.md` and `PHASE_PLAN.md` deferred `dev_agent` (the autonomous Jira-ticket
implementer) to v2, reasoning that "the pipeline has to be solid first." That reasoning was
sound in isolation but rested on an unstated assumption: that porting it would be cheap once
the time came. Reading v5's implementation end to end to check that assumption surfaced two
things that change the calculus.

**Finding 1 — v5's `dev_agent` never completed an autonomous run.** It is substantial and
well-engineered — 1,815 lines across 12 modules: an explicit lifecycle state machine, seven
deterministic pre-merge gates plus an independent LLM reviewer, resumable session memory,
self-verification of the diff against ticket intent, git-worktree isolation per ticket. But
`docs/CHECKPOINT-live-run-backend.md`, still present at v5's HEAD, records the actual outcome:
blocked on free-tier LLM quotas. Groq's free tier is 12k TPM against a 68k-token request (5-6x
over); Gemini's free-tier `generateContent` quota was set to 0, requiring billing even for the
nominally free allowance. The checkpoint doc ends with "to resume the live run, pick one" and
names the abandoned test ticket. Every commit after that checkpoint is unrelated work. So
"port it in v2" was never "port a proven component" — it was always "finish something v5 left
blocked," and that fact was invisible until read closely.

**Finding 2 — the specific blocker is already gone.** v6 has Vertex AI with real billing,
verified working this session for both chat extraction and 768-dim embeddings. v5 hit its wall
specifically because every backend it tried was either free-tier-limited or required a card it
didn't have. v6's Vertex project already clears that bar. Claude Code supports Vertex AI
natively (`CLAUDE_CODE_USE_VERTEX=1` + Application Default Credentials, the same auth path
already proven in `llm_client.py`'s `_vertex_auth_header()`), so this is not a new integration
to build — it is pointing an existing, working credential at a feature Claude Code already
has.

**Finding 3 — a live, confirmed bug in the state machine, with an exact fix.** v5's own
migration notes (`MIGRATION_FROM_V5.md` #2) flagged this as "fix it when porting," and reading
the code confirms both halves precisely:

- `lifecycle.TERMINAL_STATES = {CLOSED, FAILED, NEEDS_HUMAN}` — `SHIPPED` (a successful run
  that opened a PR and moved the ticket to review) is *not* terminal.
- `db.get_active_run()`'s SQL independently hardcodes `state NOT IN ('CLOSED', 'FAILED',
  'NEEDS_HUMAN')` — the same three states, spelled a second time, already drifted from
  `TERMINAL_STATES` in the sense that nothing keeps them in sync.
- `orchestrator.poll_and_process()` calls `get_active_run()` first and, if it finds a
  "non-terminal" run, calls `process_ticket()` on it directly — bypassing `should_attempt()`
  entirely.

The result, live: a `SHIPPED` run matches the SQL's exclusion list, so every subsequent poll
treats it as a crashed run to resume, reprocesses the ticket, and `db.start_run()`'s
`ON CONFLICT ... attempt_count = attempt_count + 1` increments forever. **61 `AgentRun` nodes
for one ticket** in the live v5 graph, confirmed in `MIGRATION_FROM_V5.md`'s node counts.

**Decision.** Port `dev_agent` now, as Phase 11, with three deliberate departures from a
literal port:

1. **`SHIPPED` joins `TERMINAL_STATES`, and the terminal set has exactly one definition.**
   `db.get_active_run()`'s query is built from `lifecycle.TERMINAL_STATES` rather than a
   second hardcoded tuple — the drift between two spellings of the same fact is the root
   cause, not a coincidence, so the fix is a single source of truth, not a corrected copy.
   `poll_and_process()` also calls `should_attempt()` before resuming an active run, as a
   second independent check — belt and suspenders, per `MIGRATION_FROM_V5.md`'s explicit
   instruction.
2. **No APScheduler.** v5's `orchestrator.py` ran an in-process `AsyncIOScheduler` inside its
   own FastAPI service — a direct violation of the rule the rest of v6 already holds to.
   `jobs/dev_agent_poll.py` is a Cloud Run Job on a Cloud Scheduler cadence; manual
   trigger/status becomes routes on the existing `api/` service rather than a second FastAPI
   process, since v6 (unlike v5) already has one.
3. **One SQL-owning module, still.** v5's `dev_agent/db.py` opened its own pool and owned its
   own queries — a second SQL module, which `CLAUDE.md` forbids in v6. The `dev_agent_runs`
   table and its queries move into `meeting_notes/db.py`; `meeting_notes/dev_agent/*` calls
   those functions rather than touching Postgres directly.

Everything else — the seven deterministic guardrail gates, the independent LLM reviewer, git
worktrees per ticket, resumable session memory, self-verification that flags rather than
blocks, and the rule that the agent **never merges its own PR** — carries across as designed.
That design is sound; what was missing was runway, not correctness.

**Consequences.** This is real new scope, not a formality: git/GitHub/Jira write access, a
container image with the `claude` CLI and `gh` installed, and a guardrail surface that has to
actually hold up against a real PR before anyone trusts it unattended. The `CLOSED` transition
(an actual merge) is driven by `/webhook/github`'s `pull_request.merged` event, which Phase 8
built as acknowledge-only specifically because ADR-008 deferred provenance *writers* to v2 —
this ADR is what un-defers that write path. Live end-to-end verification (a real ticket, a
real PR, a real merge) needs credentials this session does not have on hand and should not be
assumed; it is called out explicitly in the Phase 11 plan rather than claimed.

**Rejected:**
- *Leave it in v2 as originally decided.* The reasoning for deferring it ("pipeline has to be
  solid first") was about sequencing risk, not about the component being unsound — and eight
  phases of the pipeline are now built and tested. Continuing to defer a component whose only
  real blocker is already resolved trades a stale caution for no benefit.
- *Port literally, fix the bug later.* The bug is fully diagnosed now, with its exact location
  and fix already known from reading the code. Porting it in and coming back later means
  reintroducing a documented, confirmed-live data-corruption bug on purpose.

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
