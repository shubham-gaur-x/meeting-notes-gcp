# Graph Report - meeting-notes-gcp  (2026-08-19)

## Corpus Check
- 10 files · ~49,683 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 522 nodes · 1084 edges · 36 communities (26 shown, 10 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 111 edges (avg confidence: 0.91)
- Token cost: 121,071 input · 0 output

## Community Hubs (Navigation)
- Doctor & Secret-Handling Contract
- sync.py Orchestration
- Durable Terraform Resources
- Ephemeral Terraform Resources
- Project Governance & Schema
- PKCE & API Probes
- Durable/Ephemeral Cost Model
- Airbyte & Scheduler Removal
- Token Store & Env Loading
- Hand-rolled OAuth Flow
- Phase 1 Live Validation (ADR-017)
- Token Expiry Reporting
- LLM Config & Local Stack
- Meet Transcripts & Spike Entry
- Reproducibility Contract
- Swappable LLM Backend Seam
- Loopback Callback Server
- Auth Risks & Onix Split
- Rejected Backends & Export SA Bug
- OAuth Scopes & Consent URL
- Callback Request Handler
- Backup Verified Before Destroy
- State Bucket Bootstrap
- Memgraph VM Bootstrap
- Deferred v2 Agents
- Cost Posture
- Dataflow Rejection
- Leiden Fragmentation Bug
- Porting Order
- Project Identity
- ArgumentParser
- datetime

## God Nodes (most connected - your core abstractions)
1. `Status` - 36 edges
2. `CheckResult` - 22 edges
3. `Phase 0.6 reproducibility implementation plan` - 20 edges
4. `run_checks()` - 19 edges
5. `Phase 0.5 auth spike implementation plan` - 19 edges
6. `sync_down()` - 19 edges
7. `ADR-016 — Ephemeral compute, durable storage: the system is up only when syncing` - 15 edges
8. `check_token_age()` - 14 edges
9. `_mock_client()` - 14 edges
10. `doctor.py check contract` - 14 edges

## Surprising Connections (you probably didn't know these)
- `Phase 0.5 auth runbook` --references--> `probe_calendar()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Phase 0.5 auth runbook` --references--> `probe_gmail()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Meet transcripts via Workspace Events` --conceptually_related_to--> `probe_meet()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Phase 0.5 auth runbook` --references--> `probe_meet()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Secret handling rules` --conceptually_related_to--> `render_report()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Phase 1 live validation cycle: markers, timings, bugs, safety property** — docs_decisions_adr017, docs_phase_plan_phase1_outcome, docs_decisions_marker_record_proof, docs_decisions_measured_sync_up_duration, docs_decisions_four_live_discovered_bugs, docs_decisions_orphan_export [EXTRACTED 1.00]
- **Sync session lifecycle: ephemeral tier up, work, backed-up teardown** — docs_decisions_ephemeral_tier, docs_decisions_durable_tier, docs_decisions_sync_up, docs_decisions_sync_down, docs_setup_iap_tunnel, docs_decisions_seven_day_refresh_token_expiry [EXTRACTED 1.00]
- **Three-tier reproducibility contract realised across docs and tooling** — docs_decisions_adr013, docs_decisions_adr014, docs_decisions_adr015, docs_setup_tier0, docs_setup_tier1, docs_setup_tier2, docs_setup_doctor, docs_phase_plan_phase06 [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks, docker_compose_local_postgres_service [EXTRACTED 1.00]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_decisions_adr005, docs_decisions_adr007, docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Ephemeral sync-up/sync-down lifecycle** — docs_decisions_adr016, docs_phase_plan_phase1, docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]

## Communities (36 total, 10 thin omitted)

### Community 0 - "Doctor & Secret-Handling Contract"
Cohesion: 0.07
Nodes (80): Secret handling rules, No-secrets-in-output guarantee (spike), doctor exit code contract, Injected-probe check design, Leak-canary secret test, Phase 0.6 reproducibility implementation plan, doctor.py check contract, The three-tier contract (+72 more)

### Community 1 - "sync.py Orchestration"
Cohesion: 0.07
Nodes (59): ArgumentParser, datetime, Runner, RuntimeError, backup_uri(), build_parser(), export_object_name(), main() (+51 more)

### Community 2 - "Durable Terraform Resources"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 3 - "Ephemeral Terraform Resources"
Cohesion: 0.09
Nodes (34): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+26 more)

### Community 4 - "Project Governance & Schema"
Cohesion: 0.07
Nodes (36): Intent-to-skill map, Project context digest for agents, Absolute rules, Coding conventions, Personal-then-Onix deployment context, Property graph schema, meeting-notes-gcp v6, Module boundaries (+28 more)

### Community 5 - "PKCE & API Probes"
Cohesion: 0.13
Nodes (25): Request, load_client_credentials(), pkce_pair(), probe_gmail(), Read the OAuth client id and secret, or explain exactly what's missing., Return a (code_verifier, code_challenge) pair using S256., _mock_client(), AsyncClient (+17 more)

### Community 6 - "Durable/Ephemeral Cost Model"
Cohesion: 0.14
Nodes (18): Durable resource tier, Ephemeral resource tier, GCP resource inventory (§4), ADR-011 — config.py is the only reader of os.environ, ADR-016 — Ephemeral compute, durable storage: the system is up only when syncing, Bug 1 — google provider needs user_project_override + billing_project, Durable resource tier (bucket, secrets, registry, Pub/Sub, IAM, budget alert), Stopping instead of destroying does not work (+10 more)

### Community 7 - "Airbyte & Scheduler Removal"
Cohesion: 0.16
Nodes (16): Airbyte removed (§2.1), APScheduler removed → Cloud Scheduler + Cloud Run Jobs (§2.2), Concurrency, idempotency, exactly-once (§6), ADR-001 — Fresh repository, deliberate port, ADR-005 — Replace APScheduler with Cloud Scheduler + Cloud Run Jobs, ADR-006 — Claim rows with SELECT ... FOR UPDATE SKIP LOCKED, ADR-007 — Build our own connectors; remove Airbyte, ADR-008 — Defer dev_agent and action_agent to v2, ship provenance schema in v1 (+8 more)

### Community 8 - "Token Store & Env Loading"
Cohesion: 0.18
Nodes (16): MonkeyPatch, load_env_file(), load_token(), Path, Write the token 0600.      The mode is set at open time. A write-then-chmod woul, Load a stored token, or None if there isn't one., Load .env into os.environ if it exists. Returns whether a file was found.      A, save_token() (+8 more)

### Community 9 - "Hand-rolled OAuth Flow"
Cohesion: 0.17
Nodes (15): Hand-rolled OAuth over httpx, Phase 0.5 auth spike implementation plan, build_parser(), _error_of(), exchange_code(), main(), ArgumentParser, Response (+7 more)

### Community 10 - "Phase 1 Live Validation (ADR-017)"
Cohesion: 0.25
Nodes (14): ADR-017 — Phase 1 validated live: the sync lifecycle works, and costs ~11 minutes to start, Backup-before-destroy guarantee, Bug 4 — gcloud storage ls exits 1 on an empty prefix, Bug 2 — cloudresourcemanager and iam APIs missing from required list, Cloud SQL provisioning is the sync-up long pole, A fake-backend fixture miss raises, Four bugs found by running the full cycle that review missed, Marker-record proof of data survival across teardown (+6 more)

### Community 11 - "Token Expiry Reporting"
Cohesion: 0.19
Nodes (11): A refresh token plus the metadata needed to reason about its expiry., Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, render_report(), StoredToken, The single most important test in this file. docs/GOOGLE_AUTH.md §7., test_age_and_expiry_math(), test_report_distinguishes_reachable_from_transcripts_present(), test_report_never_contains_the_token() (+3 more)

### Community 12 - "LLM Config & Local Stack"
Cohesion: 0.22
Nodes (13): 768-dimensional embedding invariant, Environment variable surface, LLM configuration seam, Pinned image tags taken from v5, Memgraph Lab service, Local memgraph-mage service, Local Postgres 15 service, Bug 4: literal 'null' strings from the LLM (+5 more)

### Community 13 - "Meet Transcripts & Spike Entry"
Cohesion: 0.36
Nodes (12): Meet transcripts via Workspace Events, Meet: reachable vs transcripts-present, Namespace, _consent(), _probe(), probe_calendar(), probe_meet(), ProbeResult (+4 more)

### Community 14 - "Reproducibility Contract"
Cohesion: 0.24
Nodes (12): graphify maintenance discipline, ADR-013 — Three-tier reproducibility contract with a permanently manual OAuth console step, ADR-015 — db.py selects its connection mode on configuration, Phase 0.6 — Reproducibility skeleton, Standing exit criterion — Phases 1 through 9, make doctor — tier-aware preflight, IAP tunnel to Memgraph Bolt, sync-up session start (~11 min) (+4 more)

### Community 15 - "Swappable LLM Backend Seam"
Cohesion: 0.21
Nodes (12): LM Studio becomes one of two LLM backends (§2.3), 768-dimensional embeddings in every backend, ADR-002 — Vertex AI Gemini as default LLM behind a swappable seam, ADR-014 — A fake LLM backend replaying fixtures, and a gemini backend for tier 1, llm_client.py single-protocol backend seam, OAuth console step accepted as permanently manual, Durable-tier one-time apply, The part nobody can automate — OAuth console setup (+4 more)

### Community 16 - "Loopback Callback Server"
Cohesion: 0.24
Nodes (12): Ephemeral-port loopback callback server, HTTPServer, CallbackServer, An HTTPServer that captures a single OAuth callback., Bind an ephemeral loopback port and return the server and its redirect URI., Block until the callback arrives, then validate it and return the code., start_callback_server(), wait_for_code() (+4 more)

### Community 17 - "Auth Risks & Onix Split"
Cohesion: 0.25
Nodes (11): Known risks (§8), ADR-009 — Personal GCP project now, Onix Workspace data throughout, ADR-012 — Phase 0.5 auth spike passed, no admin allowlisting needed, 7-day refresh token expiry (External + Testing OAuth client), Phase 0 — Documentation (DONE), Phase 0.5 — Auth spike (DONE 2026-08-19), Phase 10 — Onix migration, Phase 9 — Hardening and demo (+3 more)

### Community 18 - "Rejected Backends & Export SA Bug"
Cohesion: 0.22
Nodes (9): BigQuery as the staging layer — rejected, GKE Autopilot from day one — deferred, Spanner Graph instead of Memgraph — rejected, ADR-003 — Keep Memgraph; reject Spanner Graph, ADR-004 — Memgraph on a GCE VM first, GKE later, Bug 3 — gcloud sql export writes as the instance's own service account, Ephemeral resource tier (Cloud SQL instance + Memgraph VM and disk), Phase 7 — Graph intelligence (+1 more)

### Community 19 - "OAuth Scopes & Consent URL"
Cohesion: 0.36
Nodes (8): Loopback redirect and prompt=consent, Phase 0.5 auth runbook, The four minimal OAuth scopes, PKCE S256 authorization-code flow, build_auth_url(), Build the Google consent URL.      access_type=offline and prompt=consent are bo, test_auth_url_carries_offline_and_consent(), test_auth_url_requests_exactly_the_four_scopes()

### Community 20 - "Callback Request Handler"
Cohesion: 0.29
Nodes (4): BaseHTTPRequestHandler, _CallbackHandler, CallbackResult, Silence the default stderr access log.          It would echo the query string,

### Community 21 - "Backup Verified Before Destroy"
Cohesion: 0.67
Nodes (3): Export/snapshot verification before destroy, sync_down(), SyncError exception

## Knowledge Gaps
- **30 isolated node(s):** `tf_bootstrap.sh script`, `startup.sh script`, `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image` (+25 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Phase 0.6 reproducibility implementation plan` connect `Doctor & Secret-Handling Contract` to `LLM Config & Local Stack`, `Project Governance & Schema`, `Reproducibility Contract`?**
  _High betweenness centrality (0.219) - this node is a cross-community bridge._
- **Why does `Standing exit criterion — Phases 1 through 9` connect `Reproducibility Contract` to `Doctor & Secret-Handling Contract`, `Durable/Ephemeral Cost Model`?**
  _High betweenness centrality (0.181) - this node is a cross-community bridge._
- **Why does `Phase 0.5 auth spike implementation plan` connect `Hand-rolled OAuth Flow` to `Doctor & Secret-Handling Contract`, `Project Governance & Schema`, `PKCE & API Probes`, `Token Store & Env Loading`, `Token Expiry Reporting`, `Meet Transcripts & Spike Entry`, `OAuth Scopes & Consent URL`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `Status` (e.g. with `doctor.py check contract` and `test_blank_secret_counts_as_unset()`) actually correct?**
  _`Status` has 32 INFERRED edges - model-reasoned connections that need verification._
- **What connects `tf_bootstrap.sh script`, `startup.sh script`, `var.cloudsql_tier` to the rest of the system?**
  _30 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Doctor & Secret-Handling Contract` be split into smaller, more focused modules?**
  _Cohesion score 0.06610644257703081 - nodes in this community are weakly interconnected._
- **Should `sync.py Orchestration` be split into smaller, more focused modules?**
  _Cohesion score 0.07192460317460317 - nodes in this community are weakly interconnected._