# Phase Plan — meeting-notes-gcp

**This is the build order. Execute phases in sequence.**

Every phase has explicit exit criteria. Do not start phase N+1 until phase N's criteria are
met. Each phase ends with a green test suite and a commit.

Recommended workflow per phase, using the `superpowers` plugin:
brainstorm → write a spec into `docs/superpowers/specs/` → TDD the implementation →
request code review → commit → `graphify . --update`.

---

## Phase 0 — Documentation ✅ DONE

`CLAUDE.md`, `ARCHITECTURE.md`, `MIGRATION_FROM_V5.md`, `GOOGLE_AUTH.md`, `DECISIONS.md`,
repo skeleton, config files.

---

## Phase 0.5 — Auth spike ✅ DONE (2026-08-19, ADR-012)

**Outcome: passed on the first attempt. No Workspace admin allowlisting was needed.**
Gmail, Calendar, and Meet all returned real records. Meet transcription is **enabled** on
the Onix tenant, so `sources/meet.py` can be built as a first-class source in Phase 5 rather
than assuming the no-op degradation described in `GOOGLE_AUTH.md` §6.

The OAuth client lives in `meeting-notes-gcp-personal`, a personal-account GCP project,
reading the Onix Workspace account — the split ADR-009 commits to. Refresh token is on the
7-day External+Testing clock until Phase 10 makes the client Internal.

**Original gating rationale, kept for the record.** If the Onix Workspace admin blocks
unverified third-party apps, the entire ingestion design changes and everything built before
finding out is wasted.

Full runbook: `docs/GOOGLE_AUTH.md`.

**Tasks**
1. Create an OAuth 2.0 client (Desktop app) in the personal GCP project. External user type.
2. Add `shubham.gaur@onixnet.com` as a test user.
3. Enable Gmail, Calendar, Meet, and Pub/Sub APIs.
4. Write `scripts/auth_spike.py` — a local consent flow that stores a refresh token and then
   makes one real call against each of: Gmail list, Calendar list, Meet conference records.
5. Confirm whether Meet transcription is enabled on the Onix Workspace tenant.
6. Record the outcome in `docs/DECISIONS.md`.

**Exit criteria**
- A refresh token for `shubham.gaur@onixnet.com` is held, and one real message, one real event,
  and (if available) one real transcript have been fetched.
- The 7-day expiry behaviour is confirmed in practice, not just in theory.
- Meet transcript availability is a known yes or no.

**If blocked by the Workspace admin:** stop and escalate. Ask for the client ID to be marked
Trusted under Security → Access and data control → API controls. Do not work around it, and do
not proceed to Phase 1 — this is the natural moment to open the Onix GCP conversation.
*(Did not occur — see the outcome above.)*

---

## Phase 0.6 — Reproducibility skeleton 🟩

Spec: `docs/superpowers/specs/2026-08-13-clone-and-run-design.md`. ADRs 013–015.

A clone plus credentials must run the project end to end. Where a credential is genuinely
unavoidable, the failure must be loud, specific, and carry the exact fix. This phase builds
only the scaffolding that stands on its own today — the rest is specified and attributed to
the phase that owns it.

**Tasks**
1. `scripts/doctor.py` + `make doctor` — tier-aware preflight (0 local · 1 LLM · 2 cloud).
   Every check injects its probe, so the suite runs with no Docker, network, or gcloud.
   Secrets reported as set/unset/expired, never valued.
2. `docker-compose.local.yml` — Postgres 15 + `memgraph-mage` + Lab, tags taken from v5's
   proven compose rather than guessed. The Memgraph tag must match Phase 1's Terraform.
3. `.env.example` — four LLM backends, `GEMINI_API_KEY`, local defaults that match compose.
4. `terraform/envs/{personal,onix}.example.tfvars` — committed; real `.tfvars` gitignored.
5. `docs/SETUP.md` — the tiered runbook. README shrinks to a pointer.
6. `Makefile` — `doctor`, `demo`, `demo-up`, `demo-down`; normalise every target onto
   `$(PYTHON)`; `lint`/`typecheck` name only directories that exist.

**Deferred by the spec, not built here:** `fake`/`gemini` backends and fixture replay
(Phase 4) · sample corpus (Phase 6) · dual-mode `db.py` (Phase 3) · a working `make demo`
(Phase 6 pipeline → Phase 8 dashboard).

**Exit criteria**
- `make doctor` passes on a clean clone with no `.env` at all.
- `make doctor TIER=2` names every genuinely missing cloud prerequisite with a runnable fix.
- No check can emit a secret value — asserted by test, with a canary that cannot collide
  with a variable name.
- `docker compose -f docker-compose.local.yml config -q` validates, and every pinned image
  tag is confirmed to exist rather than assumed.

---

## Standing exit criterion — Phases 1 through 9

**In addition to** each phase's own criteria, every phase from here on must leave the repo
in this state before it is called done:

- A clean clone still passes `make doctor`.
- From Phase 6, `make demo` is green.
- `terraform/envs/*.example.tfvars` are committed; real `.tfvars` remain gitignored.
- `graphify . --update` has been run, with `GRAPH_REPORT.md` and `graph.json` committed —
  **never** `cache/` or `.graphify_root`.

This is what stops reproducibility becoming a retrofit at Phase 9. The local stack doubles as
the test harness for Phases 3–8, so it is exercised continuously rather than rotting.

---

## Phase 1 — Terraform foundation ✅ DONE (2026-08-20, ADR-016 / ADR-017)

**Outcome: the sync lifecycle works, proven end to end against real GCP.** A full
cycle ran — durable apply → `sync-up` → markers written to both stores → `sync-down`
→ verified `Listed 0 items` and `$0` → `sync-up` → **both markers returned with their
original timestamps.** Data survives the gap.

**A `sync-up` costs ~11–12 minutes, a `sync-down` ~3.** Almost the entire `sync-up` is
Cloud SQL instance provisioning (11m05s measured); the Memgraph VM serves Bolt in about
two minutes. Fine at a monthly cadence, and ADR-017 records where to cut if that ever
changes.

Running it found **four bugs review had missed** — all wrong assumptions about Google
API behaviour, including a unit-test mock that encoded the wrong `gcloud` exit code and
therefore certified the bug it was meant to catch. Details in ADR-017; fixes in
`7972f9a`, each with a test that would have caught it.

The backup-before-destroy guarantee also held unrehearsed: one `sync-down` failed at
the snapshot step and `terraform destroy` correctly never ran.

**Note for the next phase:** billing was the real blocker, not the code. Two personal
billing accounts were closed and "not in good standing"; the working setup is a billing
account owned by `work.shubham.gaur.x@gmail.com` with `roles/billing.user` granted to
`shubham.gaur.x@gmail.com`, which the project links to. $300 trial credit, 90 days.

---

### Original plan

Everything in code. No console clicks.

**Lifecycle model (ADR-016): the system is up only while syncing.** This is a trial touched a
few hours a month, not an always-on service. Every resource splits into durable (created once,
cheap-to-free while idle) or ephemeral (created at `sync-up`, torn down at `sync-down`):

| Tier | Resources |
|---|---|
| Durable | GCS backup bucket · Secret Manager · Artifact Registry · Pub/Sub topic + pull subscription · service accounts/IAM · budget alert |
| Ephemeral | Cloud SQL instance · Memgraph GCE VM + disk |

Cloud Run jobs/services need no special handling — `min-instances=0` already makes them free
idle. "Stop" was considered and rejected for the ephemeral tier: Cloud SQL auto-restarts a
stopped instance after ~7 days, silently resuming the bill mid-gap.

**Tasks**
1. `terraform/` — providers, backend (GCS state bucket), `variables.tf` with no defaults for
   `project_id` / `region`.
2. `terraform/envs/personal.tfvars` and `onix.tfvars` — **both gitignored**, since they carry
   project IDs. Commit `personal.example.tfvars` and `onix.example.tfvars` alongside them so
   the required variables are discoverable. (`.gitignore` excludes `*.tfvars` and re-includes
   `*.example.tfvars`.)
3. Durable-tier resources: Artifact Registry · Secret Manager secrets · service accounts with
   least-privilege IAM · Pub/Sub topic and **pull** subscription · **budget alert** · a GCS
   bucket for Cloud SQL exports and Memgraph disk snapshots.
4. Ephemeral-tier resources: Cloud SQL Postgres 15 (smallest viable tier), created importing
   the latest GCS export when one exists · GCE VM for Memgraph, its disk created with
   `source_snapshot` set to the latest snapshot when one exists.
5. Memgraph VM bootstrap: Docker Compose with `memgraph-mage`, `lab`, `mcp-memgraph`.
6. `Makefile` targets: `tf-plan`, `tf-apply`, `tf-destroy`, `secrets-put`, and the two lifecycle
   commands —
   - `sync-up`: `terraform apply` (ephemeral tier) → `make doctor TIER=2` (expect the OAuth
     token check to report `expired` and point at `make auth-spike ARGS=--reconsent` — a normal
     step at this cadence, not a failure) → ready to sync.
   - `sync-down`: `gcloud sql export sql` to the GCS bucket → snapshot the Memgraph disk →
     `terraform destroy` scoped to the ephemeral tier only.

**Price the design against current GCP rates in this phase and set the budget alert before the
first `apply`.** Do not trust the estimates in `ARCHITECTURE.md` — they were not verified.

**Exit criteria**
- `terraform apply` from clean produces a working environment.
- Memgraph reachable over Bolt; Cloud SQL reachable from Cloud Run.
- Budget alert active.
- `terraform destroy` then `apply` reproduces the environment exactly.
- `sync-down` then `sync-up` reproduces the environment **with data intact** — proven by
  writing a marker record before `sync-down` and reading it back after the next `sync-up`, not
  assumed from the export/import commands succeeding.

---

## Phase 2 — Pure core ✅ DONE (2026-08-20, ADR-018)

All nine modules ported into `meeting_notes/`. **187 tests green**, ruff and mypy clean over
`meeting_notes scripts tests`, no live services required by anything.

**Exit criteria met.** `config.py` is verified by AST — not grep — to be the only thing in the
package that reads the environment: no module imports `os` at all. (grep gives a false positive
on `person_resolver`'s docstring, which mentions `os.environ` while explaining that it no longer
uses it.)

**Two behavioural changes beyond the port**, both required by `CLAUDE.md`'s config rule:
`person_resolver.load_roster` and `access_control.load_policy` take an explicit path instead of
reading `PERSON_ROSTER_PATH` / `ACCESS_POLICY_FILE` themselves. Both are also now testable
without touching the process environment.

**A v5 governance bug was found and fixed** — not one of the ten in `MIGRATION_FROM_V5.md`.
`person_resolver`'s tier-2 branch read `tracked` off the leaked loop variable `p` (the last
person iterated) rather than the one that matched, so `Person.tracked` — the opt-in gate for
naming individuals in analytics — was decided by list ordering. Fixed, with a regression test
verified to fail against v5's line and pass against the fix.

**Reading v5 first corrected four plan assumptions**, each of which would have produced a test
that passed for the wrong reason: `uuid5_id` is a double uuid5; `priority_from_due(None)` is
`low`; `dedup.similarity` reads `candidate["task"]` not `["text"]`; `_HINTS["general"]` is
deliberately the empty string.

**v5 test disposition** — `PHASE_PLAN` requires every dropped test to have a written reason:

| v5 test file | Covers | Disposition |
|---|---|---|
| `test_phase31_meeting_quality.py` | `meeting_quality` | ported |
| `test_phase33_access_control.py` | `access_control` | ported |
| `test_phase39_person_resolver.py` | `person_resolver` | ported |
| `test_phase42_dedup.py` | `dedup` | ported |
| `test_phase43_meeting_type_router.py` | `meeting_type_router` | ported |
| `test_phase40_person_resolution_upsert.py` | person resolution **into the graph** | **deferred to Phase 3** — needs `graph_client` |
| — | `classifier` | **none existed in v5**; written here |

**Also deferred to Phase 3:** `meeting_quality.score_all_meetings()`. The plan assumed this
module was fully pure; it is not — that one function orchestrates `memgraph_client`. Every
other function in it is pure and ported.

---

### Original plan

The modules with no I/O. These port nearly unchanged and give a green suite early.

**Port:** `config.py` (new) · `models.py` · `utils.py` · `classifier.py` ·
`meeting_type_router.py` · `person_resolver.py` · `dedup.py` · `meeting_quality.py` ·
`access_control.py`

**Also decide:** the `StagedRecord` question in `MIGRATION_FROM_V5.md` §3. Record it as an ADR
before writing `db.py`. Deciding this after the connectors exist is much more expensive.

**Exit criteria**
- `pytest` green, no live services required.
- `config.py` is the only module referencing `os.environ`.
- Every ported test from v5 either passes or has a written reason for being dropped.

---

## Phase 3 — Data layer ✅ DONE (2026-08-20)

**All three exit criteria met, and the two that matter were proven rather than assumed.**

**Schema applies cleanly and idempotently.** `make migrate` creates `staged_records` +
`watermarks`; run twice, second run exit 0, and Postgres confirms the partial index and the
`(source_type, source_id)` unique constraint were actually built. `scripts/setup_memgraph.py`
applies 26/26 statements, and 26/26 again on re-run.

**Concurrent claiming proven against real Postgres**, not a mock — `SKIP LOCKED` is
server-side behaviour no mock can demonstrate. Against the same 20 staged rows:

| claim | result |
|---|---|
| plain `FOR UPDATE` (v5's shape) | second drain **blocked**, timed out on row locks |
| `FOR UPDATE SKIP LOCKED` (ADR-006) | batch1=10, batch2=10, **overlap=0** |

**Smoke write against real Memgraph** verified by Cypher count: Meeting 1 · Person 1 ·
PersonReview 1 · **Topic 1 (from two case variants)** · Decision 1 · ActionItem 1 ·
**ASSIGNED_TO 1**.

**`db.py` is a rewrite, not a port.** v5's is shaped end to end by Airbyte — `information_schema`
discovery of a hash-suffixed Jira table, `ALTER`s against Airbyte's own tables, four per-source
getters each with an Airbyte-preferred branch — and it has **no `SKIP LOCKED` anywhere**, safe
only because v5 ran a single container.

**Two v5 bugs fixed, each with a regression test verified to fail against v5's line:**

- **MIGRATION bug #1 — `ASSIGNED_TO` never formed.** v5 bound
  `owner_email = action.owner if "@" in action.owner else None`; the extractor emits display
  names, so the live edge count was **zero**. Owners now go through the same resolver the
  attendees use. The smoke write above shows the edge forming from the name "Alice Smith".
- **doctor never checked Memgraph Lab's port** — a pre-existing gap surfaced by replacing a
  hardcoded port list with one derived from `docker-compose.local.yml`.

**The local stack now runs on 55432 / 57687 / 57444 / 53000**, not the conventional ports. v5's
stack has been up for weeks holding 5432/7687/3000, and v5 is read-only reference: pointing
v6's migration at `localhost:5432` would have applied v6 schema **into v5's database**.

**Deferred, with reasons:**

| Deferred | To | Why |
|---|---|---|
| ~16 read/query functions (`get_timeline`, `get_person_graph`, `get_influential_nodes`, …) | **Phase 8** | Only the API calls them; testable properly there via `httpx.ASGITransport` |
| `get_meetings_quality_inputs`, `set_meeting_quality` | **Phase 7** | Land with the nightly quality job and `score_all_meetings` |
| `write_run_provenance`, `write_commits_and_files`, `merge_ticket_resolved_by_pr` | **v2** | ADR-008 — schema in v1, writers in v2. The **schema ships now**. |
| `migrate_schema_v5` | **dropped** | A v5-specific one-off migration |
| `watermarks` accessors | **Phase 5** | The table ships now; adding it later would be a second migration |

---

### Original plan

**Tasks**
1. `db.py` — Cloud SQL connector, staging schema as a **migration** (not a 5-minute heartbeat),
   `SELECT ... FOR UPDATE SKIP LOCKED` claiming (ADR-006). Delete every trace of the Airbyte
   table-discovery logic (`MIGRATION_FROM_V5.md` §4).
2. `graph_client.py` — port `memgraph_client.py`. Move the six Cypher queries v5 leaked into
   `main.py` in here where they belong.
3. `scripts/setup_memgraph.py` — constraints, indexes, both 768-dim vector indexes, seeded
   procedures, **and the v1 provenance constraints** (ADR-008).

**Exit criteria**
- Schema applies cleanly to a fresh Cloud SQL instance and a fresh Memgraph.
- Two concurrent `pipeline_drain` executions provably claim disjoint batches — write a test
  that proves it, don't assume it.
- Graph write path tested against mocks; one manual smoke write against the real Memgraph.

---

## Phase 4 — LLM seam ✅ DONE (2026-08-20)

**All four exit criteria met, the live ones verified against real Vertex.**

**Model names confirmed, not assumed** — the phase explicitly warned they change.
`gemini-2.5-flash` responds on Vertex in `us-central1`, and **`text-embedding-005` returns
exactly 768 dimensions**, already unit-normalised, which is what the cosine-metric vector
indexes want. `.env.example` now carries both as confirmed defaults with the date checked.

**Four backends behind one protocol** (ADR-014) — `fake` · `gemini` · `lmstudio` · `vertex`.
Every one is exercised through an injected transport, so all 259 tests run with no network, no
API key and no LM Studio.

**Retry semantics are now a test rather than a comment.** Transport errors retry three times;
a parse failure returns `None` and is **not** retried, because at temperature 0 an identical
retry yields identical output and would only burn quota to fail the same way.

**Tier 0 works offline.** Three recorded fixtures replay with `duration_ms=0` and no
credentials. Extraction quality on the corpus is good: `kind` correct per meeting type, due
dates parsed from prose ("September 5th" → `2026-09-05`), `is_engineering_task` separating
"tell the exec team" from "spec the dual-write", and a negative decision ("no contractor")
captured rather than dropped.

**Where v5's helpers landed.** `_loads_lenient` moved to `llm_client.py` — its body unchanged.
That follows from the protocol `CLAUDE.md` mandates: `chat_json` returns a `dict`, so turning
model output into one is the seam's job. `_is_null_like` stayed with the extractor, where it
repairs fields against *our* schema.

**The prompt is carried byte for byte** and lives in `meeting_notes/prompts.py`, with a test
that diffs it against v5's file. Verified the test catches drift — changing one word fails it.
It sits in its own module because it contains over-length lines, and reflowing tuned prompt
text to satisfy a linter is not a trade worth making; E501 is waived there alone.

**Fixture keys cannot drift.** The recorder derives prompts from the extractor's own helper,
and a test proves what it writes is exactly what `extract_meeting` looks up. `CLAUDE.md` calls
writer/reader id drift a known v5 bug class that cost real debugging time twice.

**Note on `kind`:** required in v6 exactly as in v5, so no porting regression. Deliberately
*not* given a repair — silently coercing an unknown kind to `other` would distort the very
Phase 7 algorithms that key off meeting type.

---

### Original plan

**Tasks**
1. `llm_client.py` — `chat_json()` and `embed()`, backends `vertex` and `lmstudio`.
2. `extractor.py` — keep the v5 system prompt **verbatim**; it is tuned. Swap the client only.
   Keep `_is_null_like` and `_loads_lenient` exactly as they are.
3. Confirm the current Vertex model names — do not assume; they change. Model names are env
   vars, never literals.
4. Verify `text-embedding-005` really returns 768 dimensions against the live API before
   relying on it.

**Exit criteria**
- Both backends produce a valid `ExtractedMeeting` from the same fixture input.
- Backend selection is env-driven and covered by tests.
- Retry semantics preserved: transport errors retry, JSON parse failures do not.
- Gemini's behaviour on the literal-`"null"` bug (`MIGRATION_FROM_V5.md` #4) is checked, not
  assumed.

---

## Phase 5 — Connectors 🟩🟦

The only genuinely new code in the project.

**Tasks**
1. `sources/base.py` — the `Source` protocol, generalised from v5's `TranscriptSource`.
2. `sources/gmail.py` — incremental by history id or internal date. Reuse
   `processed_gmail_ids`.
3. `sources/calendar.py` — incremental by `updatedMin` / sync token.
4. `sources/jira.py` — JQL by `updated >= watermark`, through `jira_client.py`.
5. `sources/meet.py` — port `meet_ingest.py`, Pub/Sub pull.
6. `jobs/ingest_*.py` — thin entrypoints, one per source.
7. `jobs/refresh_tokens.py` — token refresh with an alert on failure.
8. Watermark storage, per source.

**Exit criteria**
- Each connector fetches real data from the Onix account and stages rows.
- Re-running a connector stages no duplicates.
- A deliberately expired token produces a visible alert, not silent failure.
- All connector tests mocked; no live credentials in the suite.

---

## Phase 6 — Pipeline 🟩

**Tasks**
1. `pipeline.py` — one `process(record, adapter)` (ADR-010) with per-source adapters.
2. `jira_pusher.py` and `jira_sync.py`.
3. `jobs/pipeline_drain.py`.
4. **Fix bug #1** from `MIGRATION_FROM_V5.md`: resolve `action.owner` through `person_resolver`
   so `ASSIGNED_TO` actually forms.

**Exit criteria**
- One real email end-to-end: staged → classified → routed → extracted → graph → Jira ticket.
- `ASSIGNED_TO` edges exist in the graph. Verify with a Cypher count, not by reading the code.
- Confidence gating works: a low-confidence item goes to `needs_review` and creates no ticket.
- Dedup works: the same action item raised twice does not open a second ticket.

---

## Phase 7 — Graph intelligence 🟩

**Port:** `graph_algorithms.py` · `memory/semantic.py` · `memory/episodic.py` ·
`memory/procedural.py` · `memory/vector.py` · `memory/retrieval.py` · `jobs/nightly.py`

**Tasks**
- Confirm MAGE procedure availability on the deployed Memgraph image.
- Check v5's git history for the Leiden over-fragmentation fix before enabling community
  detection.
- Seed a realistic meeting-type mix before drawing any conclusion from PageRank. The v5 graph
  is 73% standups and its algorithm output is distorted accordingly.

**Exit criteria**
- Fast algorithms run after each processed meeting; full algorithms run nightly.
- Semantic search returns sensible results for a query with zero keyword overlap.
- `POST /graph/memory/query` answers a natural-language question from real graph data.
- Community detection does not collapse to singletons.

---

## Phase 8 — API and dashboard 🟩

**Tasks**
1. `api/main.py` + `api/routers/` — every v5 endpoint, **zero APScheduler**.
2. `api/static/dashboard.html` — port as-is. Keep it single-file, no build step.
3. `/webhook/github` (ADR-008) and `/webhook/jira`.
4. Deploy as a Cloud Run service with `min-instances=0`.
5. Auth on query endpoints. Webhooks stay public but HMAC-verified.

**Exit criteria**
- Every v5 endpoint responds with equivalent data.
- Dashboard renders all four tabs against live data with no console errors — check in a
  browser, not just in tests.
- Service cold-starts and scales to zero.
- `/graph/insights/influential` respects the `Person.tracked` gate. Verify it; it is the
  governance promise.
- Every route has an `httpx.ASGITransport` test that drives the real ASGI app
  (`MIGRATION_FROM_V5.md` #3).

---

## Phase 9 — Hardening and demo 🟩🟦

**Tasks**
1. End-to-end validation on real data over several days.
2. Alerting: job failure, token expiry, budget threshold.
3. Backup and restore rehearsal: Cloud SQL export, Memgraph snapshot. **Actually restore.**
4. `docs/DEMO_GUIDE.md`, `docs/RUNBOOK.md`.
5. Connect Claude Desktop to the Memgraph MCP server and verify NL graph queries.
6. `graphify . --update`; commit the report.
7. Update `README.md` to reflect what was built rather than what was planned.

**Exit criteria**
- Runs unattended for a week with no manual intervention beyond OAuth re-consent.
- Restore from backup rehearsed successfully.
- Demo runs end to end without a laptop in the loop.

---

## Phase 10 — Onix migration 🟦 (when approved)

**Tasks**
1. `terraform/envs/onix.tfvars`; `terraform apply` into the new project.
2. New OAuth client — **Internal** user type. This removes the 7-day expiry and the
   verification requirement entirely (`GOOGLE_AUTH.md` §6).
3. Migrate data: Cloud SQL export/import, Memgraph dump/load.
4. Re-push images to the new Artifact Registry.
5. Decommission the personal project. Delete the data in it.

**Exit criteria**
- Everything runs in the Onix project.
- Refresh tokens no longer expire weekly.
- The personal project is empty and its data destroyed.

---

## v2 — Deferred scope

Not in v1. See ADR-008.

- `dev_agent` — port with bug #2 fixed (the `SHIPPED` resume loop that created 61 `AgentRun`
  nodes for one ticket).
- `action_agent` — re-evaluate whether it should exist at all. It is built on the Airbyte
  Agents SDK, the dependency v6 deliberately removes.
- Gmail/Calendar push notifications via `users.watch` → Pub/Sub, replacing polling.
- GKE Autopilot migration for Memgraph (ADR-004).
