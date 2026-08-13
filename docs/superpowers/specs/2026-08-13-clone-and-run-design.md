# Design — Clone-and-run reproducibility

**Date:** 2026-08-13 · **Status:** Approved · **Drives:** Phase 0.6, plus standing obligations on Phases 1–9

---

## 1. Problem

A stranger who clones this repository today can run nothing. The pipeline needs a GCP project
with billing, a Google Workspace tenant whose admin permits an unverified OAuth client, a Jira
instance, and either Vertex AI or a multi-gigabyte local model. Each is a wall, and the first
one is hit before a single line of the project's actual value is visible.

The goal: **a clone plus credentials runs the project end to end.** Where a credential is
genuinely unavoidable, the failure must be loud, specific, and accompanied by the exact fix.

## 2. Non-goals

- **Terraform will not create the OAuth consent screen or OAuth client.** Google exposes no
  usable API for an External-type consent screen or a Desktop client with restricted Gmail
  scopes. `google_iap_brand` / `google_iap_client` cover neither case. This is a permanent
  manual step; the design detects and explains it rather than pretending otherwise.
- **No Workspace admin approval can be automated.** Same treatment.
- **`make demo` will not write to a real Jira.** It no-ops cleanly with `JIRA_ENABLED=false`,
  mirroring how v5's `meet_ingest.pull_and_stage` degrades when unconfigured.
- **Not multi-tenant.** Unchanged from `CLAUDE.md`.

## 3. The three-tier contract

Each tier is one command, and each is honest about what it proves. Higher tiers are **additive,
never prerequisites**.

| Tier | Command | Credentials | Infrastructure | Proves |
|---|---|---|---|---|
| 0 | `make demo` | none | docker-compose: Postgres 15 + Memgraph MAGE | pipeline, graph writes, algorithms, memory layers, API, dashboard |
| 1 | `make demo LLM=gemini` | one API key | same local compose | genuine LLM extraction and embeddings |
| 2 | `make deploy ENV=<env>` | GCP + Workspace + Jira | real Cloud Run / SQL / GCE | the actual product |

Tier 0 is the promise. It must work offline, on a clean clone, with no `.env` edits.

## 4. Scope split — what is buildable when

The reproducibility work is cross-cutting, but most of it cannot exist yet: there is no
`llm_client.py` to add a backend to, and no `pipeline.py` for a demo to drive. Phase 0.6 builds
only the scaffolding that stands on its own. Everything else is **specified here so it is not
re-litigated later**, and attributed to the phase that builds it.

### 4.1 Ships in Phase 0.6

| Deliverable | Notes |
|---|---|
| `scripts/doctor.py` + `make doctor` | Tier-aware preflight. §5 |
| `docker-compose.local.yml` | Postgres 15 + `memgraph-mage` + Lab. §6 |
| `.env.example` expansion | New `LLM_BACKEND` values, `GEMINI_API_KEY`, local-mode defaults |
| `docs/SETUP.md` | The tiered runbook. README's "Getting started" shrinks to a pointer |
| `terraform/envs/*.example.tfvars` | Committed; real `.tfvars` stay gitignored |
| Document amendments + ADRs | §10 |
| graphify baseline | `graphify .`, commit `GRAPH_REPORT.md` + `graph.json` |

### 4.2 Deferred, specified now

| Deliverable | Phase | Spec |
|---|---|---|
| `db.py` dual-mode connection | 3 | §9 |
| `LLM_BACKEND=fake` + `gemini` | 4 | §7 |
| Fixture recording / replay | 4 | §7 |
| Sample meeting corpus + seed | 6 | §8 |
| `make demo` becomes real | 6 (pipeline) → 8 (dashboard) | §3 |

## 5. `scripts/doctor.py`

The single highest-leverage file for the clone experience. It answers "why can't I run this?"
before the user has to read a stack trace.

### Contract

Each check yields `(name, status, detail, remediation)` where status is `PASS` / `WARN` / `FAIL`.
Output is a table. **Every `FAIL` carries a remediation** that is either a runnable command or a
document anchor (`docs/GOOGLE_AUTH.md §5.3`).

### Tier awareness

- `make doctor` — tier 0 only
- `make doctor LLM=gemini` — adds tier 1
- `make doctor ENV=personal` — adds tier 2

Exit codes: `0` all checks pass for the requested tier · `1` at least one `FAIL` · `2` warnings
only. CI and `make demo` both call it and refuse to proceed on `1`.

### Checks

**Tier 0** — Python ≥ 3.11 · Docker daemon reachable · `docker compose` available · ports 5432,
7687, 7444, 8080 free · disk space · `sample_data/` present · package importable.

**Tier 1** — `GEMINI_API_KEY` set, *or* LM Studio reachable at `LM_STUDIO_BASE_URL` with both
named models loaded.

**Tier 2** — `gcloud` installed and authenticated · `terraform` installed, version pinned range ·
`GCP_PROJECT_ID` set, project exists, billing enabled · required APIs enabled · OAuth client id
and secret present · `token.json` present and its age against the 7-day clock · `JIRA_*` complete
when `JIRA_ENABLED=true` · `terraform/envs/<ENV>.tfvars` exists.

### Secret handling

Credentials are reported as `set` / `unset` / `expired`. **No value is ever printed, in whole or
in part.** No prefix, no length, no truncation. `GOOGLE_AUTH.md` §7.

## 6. Local stack

`docker-compose.local.yml`, separate from any production compose:

- **Postgres 15** — matches the Cloud SQL major version; named volume; healthcheck gates
  dependents.
- **`memgraph/memgraph-mage`** — pinned tag, matching the image Terraform puts on the GCE VM so
  MAGE procedure availability is identical. Persistent volume.
- **Memgraph Lab** — for inspecting the demo graph, which is most of the "wow" for a cloner.

The API runs on the host, not in compose, so the edit-reload loop stays fast during phases 3–8.
`make demo` starts it as a managed background process after the compose healthchecks pass, and
prints the dashboard URL as its final line. A cloner never runs a second command to see the
dashboard; `make demo-down` stops both the API and the compose stack.

## 7. LLM backends (Phase 4)

`CLAUDE.md` currently sanctions `vertex | lmstudio`. This design adds two, keeping
`llm_client.py`'s protocol (`chat_json`, `embed`) unchanged and its position as the only module
that constructs an LLM client.

| Backend | Purpose |
|---|---|
| `vertex` | production. Unchanged |
| `gemini` | direct AI Studio API key — no GCP project, no billing. Tier 1 |
| `lmstudio` | local, unchanged from v5 |
| `fake` | replay recorded responses. Tier 0 default, and the test suite's mock |

### Fixture replay

Fixtures live in `sample_data/llm_fixtures/`, keyed by a **hash of (system prompt + user
content + temperature)**.

Two properties are deliberate:

1. **A prompt edit changes the hash, producing a loud miss.** A miss **raises**; it never falls
   through to `None` or a default. A silently-wrong extraction is the worst outcome available
   here, and `CLAUDE.md`'s existing defences (`_is_null_like`, fence stripping) exist precisely
   because quiet LLM misbehaviour cost real debugging time in v5.
2. **`scripts/record_fixtures.py` regenerates against a real backend**, so refreshing after a
   deliberate prompt change is one command rather than hand-authoring JSON.

Embeddings remain **768-dimensional in every backend**, including `fake`, because both Memgraph
vector indexes are configured for 768.

## 8. Sample corpus (Phase 6)

A realistic **mix** of meeting types — standups, 1:1s, design reviews, planning, incident calls,
email threads — not a single type repeated.

This is not cosmetic. `CLAUDE.md` records that the v5 graph is 73% standups and that its
algorithm output is distorted accordingly, and `PHASE_PLAN.md` Phase 7 requires a realistic mix
before drawing any conclusion from PageRank. Seeding a skewed corpus would bake that same
distortion into every cloner's first impression.

Seeding must be **idempotent** — re-running produces no duplicates, which deterministic
`uuid5_id` + `MERGE` already guarantee at the graph layer and the seed script must respect at
the staging layer.

## 9. `db.py` dual-mode (Phase 3)

Tier 0 needs plain Postgres; tier 2 needs the Cloud SQL connector. `db.py` selects on
configuration: `CLOUD_SQL_CONNECTION_NAME` set → connector; otherwise `POSTGRES_HOST` DSN.

Decided now rather than during Phase 3 because `PHASE_PLAN.md` §Phase 2 makes exactly this
argument about the `StagedRecord` question — a data-layer shape settled after the connectors
exist is far more expensive to change. All SQL stays inside `db.py`; this is a connection-
acquisition branch, not a second query path.

## 10. Document amendments

None of these are edited silently.

| File | Change |
|---|---|
| `CLAUDE.md` | LLM backends → `vertex \| gemini \| lmstudio \| fake`; env var list gains `GEMINI_API_KEY` |
| `docs/PHASE_PLAN.md` | Insert Phase 0.6; add the standing exit criterion to Phases 1–9 |
| `docs/GOOGLE_AUTH.md` | §5.4 says "Print the refresh token" — contradicts §7 and `CLAUDE.md`. Corrected to print the issue date only |
| `docs/DECISIONS.md` | Three new ADRs, below |
| `README.md` | "Getting started" replaced by a pointer to `docs/SETUP.md` |

### New ADRs

- **Three-tier reproducibility contract** — why a local path exists in a GCP-native project, and
  why the OAuth console step is accepted as permanently manual.
- **`fake` backend and fixture replay** — why a fourth backend earns its place, and why fixture
  misses raise.
- **Dual-mode `db.py`** — why the branch is decided before Phase 3.

**Numbering:** Phase 0.5's outcome ADR lands first and takes **ADR-012**. These become
**ADR-013, ADR-014, ADR-015**. `DECISIONS.md` is append-only; numbers are never reused.

## 11. Standing exit criterion (Phases 1–9)

Added to every phase from Phase 1 onward:

> A clean clone still passes `make doctor`. From Phase 6, `make demo` is green. `terraform/envs/*.example.tfvars` are committed while real `.tfvars` remain gitignored. `graphify . --update` has been run and `GRAPH_REPORT.md` + `graph.json` committed — never `cache/`.

This is what prevents the retrofit. The local stack doubles as the test harness for phases 3–8,
so it is exercised continuously rather than rotting between now and Phase 9.

## 12. Testing

- `doctor.py` is unit-tested with mocked probes — no Docker, no network, no `gcloud`. Both the
  pass and fail branch of every check, and an assertion that **no check ever emits a secret
  value**.
- Fixture replay is tested for hit, miss-raises, and 768-dimension conformance.
- The existing rule holds without exception: the suite runs with no live GCP, no database, no
  LLM. A test requiring live credentials is a broken test.

## 13. Risks

| Risk | Mitigation |
|---|---|
| Fixtures drift from prompts | Hash-keyed, loud miss, one-command re-record |
| A compose path production never uses rots | It is the test harness for phases 3–8 |
| Tier 0 passing implies tier 2 works | `SETUP.md` and `doctor` state per-tier scope explicitly; tier 0 never claims to prove GCP |
| Local Memgraph image drifts from the VM image | Same pinned tag in compose and Terraform; asserted by `doctor` at tier 2 |

## 14. Open questions

None blocking. Deferred to their owning phases: exact Postgres and MAGE image tags (Phase 1,
must match Terraform), and the size of the sample corpus (Phase 6, "enough that community
detection does not collapse to singletons").
