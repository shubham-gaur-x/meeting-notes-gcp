# Graph Report - meeting-notes-gcp  (2026-08-19)

## Corpus Check
- 31 files · ~47,943 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 478 nodes · 947 edges · 33 communities (18 shown, 15 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 93 edges (avg confidence: 0.92)
- Token cost: 175,626 input · 0 output

## Community Hubs (Navigation)
- OAuth Auth Spike
- Doctor & Reproducibility Contract
- Durable Terraform Resources
- sync.py Orchestration
- Project Governance & Schema
- Ephemeral Terraform Resources
- Cost Posture & ADR Log
- Loopback Callback Server
- LLM Config & Local Stack
- Concurrency & Scheduling
- Airbyte Removal
- Graph Backend Rejections
- v2 Deferred Scope
- Backup Verification Before Destroy
- GKE Autopilot Deferral
- LM Studio Backend
- Pipeline Path Consolidation
- State Bucket Bootstrap
- Memgraph VM Bootstrap
- Deferred Agents
- Dataflow/Datastream Rejection
- Fresh Repo Port
- Leiden Fragmentation Bug
- Porting Order
- Phase 4 — LLM Seam
- Phase 5 — Connectors
- Phase 7 — Graph Intelligence
- Phase 9 — Hardening
- Project Identity

## God Nodes (most connected - your core abstractions)
1. `Status` - 36 edges
2. `CheckResult` - 22 edges
3. `Phase 0.6 reproducibility implementation plan` - 20 edges
4. `Phase 0.5 auth spike implementation plan` - 19 edges
5. `run_checks()` - 19 edges
6. `sync_down()` - 18 edges
7. `_mock_client()` - 14 edges
8. `doctor.py check contract` - 14 edges
9. `check_token_age()` - 14 edges
10. `secret_status()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Loopback redirect and prompt=consent` --implements--> `start_callback_server()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Meet transcripts via Workspace Events` --conceptually_related_to--> `probe_meet()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Secret handling rules` --conceptually_related_to--> `secret_status()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/doctor.py
- `Loopback redirect and prompt=consent` --implements--> `build_auth_url()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `The four minimal OAuth scopes` --implements--> `build_auth_url()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Ephemeral sync-up/sync-down lifecycle** — docs_decisions_adr016, docs_phase_plan_phase1, docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]
- **Swappable LLM backend seam (vertex/lmstudio/gemini/fake)** — docs_decisions_adr002, docs_decisions_adr014, docs_architecture_lmstudio_backend, docs_setup_tier1 [INFERRED 0.85]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_decisions_adr005, docs_decisions_adr007, docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks, docker_compose_local_postgres_service [EXTRACTED 1.00]

## Communities (33 total, 15 thin omitted)

### Community 0 - "OAuth Auth Spike"
Cohesion: 0.05
Nodes (94): Coding conventions, Never pass event= to structlog, datetime, Loopback redirect and prompt=consent, Meet transcripts via Workspace Events, Phase 0.5 auth runbook, The four minimal OAuth scopes, Secret handling rules (+86 more)

### Community 1 - "Doctor & Reproducibility Contract"
Cohesion: 0.07
Nodes (80): graphify maintenance discipline, Standing exit criterion — Phases 1 through 9, doctor exit code contract, Injected-probe check design, Phase 0.6 reproducibility implementation plan, doctor.py check contract, Standing exit criterion (spec), The three-tier contract (+72 more)

### Community 2 - "Durable Terraform Resources"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 3 - "sync.py Orchestration"
Cohesion: 0.07
Nodes (55): Runner, RuntimeError, backup_uri(), build_parser(), export_object_name(), main(), ArgumentParser, CompletedProcess (+47 more)

### Community 4 - "Project Governance & Schema"
Cohesion: 0.06
Nodes (39): Intent-to-skill map, Project context digest for agents, Absolute rules, Personal-then-Onix deployment context, Property graph schema, meeting-notes-gcp v6, Module boundaries, Person.tracked governance gate (+31 more)

### Community 5 - "Ephemeral Terraform Resources"
Cohesion: 0.09
Nodes (33): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+25 more)

### Community 6 - "Cost Posture & ADR Log"
Cohesion: 0.12
Nodes (21): Cost posture (§7), Durable resource tier, Ephemeral resource tier, GCP resource inventory (§4), ADR-011: config.py is the only reader of os.environ, ADR-013: Three-tier reproducibility contract, ADR-014: fake LLM backend replaying fixtures, gemini backend for tier 1, ADR-015: db.py selects connection mode on configuration (+13 more)

### Community 7 - "Loopback Callback Server"
Cohesion: 0.13
Nodes (16): BaseHTTPRequestHandler, Ephemeral-port loopback callback server, HTTPServer, _CallbackHandler, CallbackResult, CallbackServer, An HTTPServer that captures a single OAuth callback., Silence the default stderr access log.          It would echo the query string, (+8 more)

### Community 8 - "LLM Config & Local Stack"
Cohesion: 0.22
Nodes (13): 768-dimensional embedding invariant, Environment variable surface, LLM configuration seam, Pinned image tags taken from v5, Memgraph Lab service, Local memgraph-mage service, Local Postgres 15 service, Bug 4: literal 'null' strings from the LLM (+5 more)

### Community 9 - "Concurrency & Scheduling"
Cohesion: 0.40
Nodes (5): APScheduler removed → Cloud Scheduler + Cloud Run Jobs (§2.2), Concurrency, idempotency, exactly-once (§6), ADR-005: Replace APScheduler with Cloud Scheduler + Cloud Run Jobs, ADR-006: Claim rows with SELECT ... FOR UPDATE SKIP LOCKED, Phase 3 — Data layer

### Community 10 - "Airbyte Removal"
Cohesion: 0.67
Nodes (3): Airbyte removed (§2.1), ADR-007: Build own connectors; remove Airbyte, Airbyte residue to delete

### Community 11 - "Graph Backend Rejections"
Cohesion: 0.67
Nodes (3): BigQuery as the staging layer — rejected, Spanner Graph instead of Memgraph — rejected, ADR-003: Keep Memgraph; reject Spanner Graph

### Community 12 - "v2 Deferred Scope"
Cohesion: 0.67
Nodes (3): ADR-008: Defer dev_agent/action_agent to v2, ship provenance schema in v1, Phase 8 — API and dashboard, v2 — Deferred scope

### Community 13 - "Backup Verification Before Destroy"
Cohesion: 0.67
Nodes (3): Export/snapshot verification before destroy, sync_down(), SyncError exception

## Knowledge Gaps
- **41 isolated node(s):** `meeting-notes-gcp`, `Repository layout`, `Environment variable surface`, `Deferred to v2: dev_agent and action_agent`, `Intent-to-skill map` (+36 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `meeting-notes-gcp v6` connect `Project Governance & Schema` to `Cost Posture & ADR Log`?**
  _High betweenness centrality (0.086) - this node is a cross-community bridge._
- **Why does `Phase 0.5 auth spike implementation plan` connect `OAuth Auth Spike` to `Doctor & Reproducibility Contract`, `Project Governance & Schema`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `The 7-day refresh token problem` connect `Project Governance & Schema` to `OAuth Auth Spike`, `Doctor & Reproducibility Contract`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `Status` (e.g. with `doctor.py check contract` and `test_blank_secret_counts_as_unset()`) actually correct?**
  _`Status` has 32 INFERRED edges - model-reasoned connections that need verification._
- **What connects `meeting-notes-gcp`, `Repository layout`, `Environment variable surface` to the rest of the system?**
  _41 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `OAuth Auth Spike` be split into smaller, more focused modules?**
  _Cohesion score 0.05029890744176459 - nodes in this community are weakly interconnected._
- **Should `Doctor & Reproducibility Contract` be split into smaller, more focused modules?**
  _Cohesion score 0.06526610644257703 - nodes in this community are weakly interconnected._