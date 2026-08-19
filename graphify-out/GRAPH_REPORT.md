# Graph Report - .  (2026-08-19)

## Corpus Check
- Corpus is ~29,982 words - fits in a single context window. You may not need a graph.

## Summary
- 304 nodes · 752 edges · 13 communities (12 shown, 1 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 89 edges (avg confidence: 0.9)
- Token cost: 183,883 input · 0 output

## Community Hubs (Navigation)
- Preflight Doctor
- Pipeline Rules & Graph Schema
- Token Exchange & Credentials
- GCP Infrastructure & Rejected Options
- PKCE Consent & Loopback Server
- Project Governance & Onix Split
- Reproducibility & Local Stack
- Token Store & Env Loading
- API Probes & Consent Flow
- Expiry Math & Outcome Report
- Auth Spike Conventions & CLI
- Project Root

## God Nodes (most connected - your core abstractions)
1. `Phase 0.6 reproducibility implementation plan` - 27 edges
2. `CheckResult` - 21 edges
3. `Phase 0.5 auth spike implementation plan` - 21 edges
4. `run_checks()` - 20 edges
5. `Phase 0.6 Reproducibility skeleton` - 15 edges
6. `check_token_age()` - 14 edges
7. `_mock_client()` - 14 edges
8. `doctor.py check contract` - 14 edges
9. `secret_status()` - 13 edges
10. `v5 to v6 port map` - 13 edges

## Surprising Connections (you probably didn't know these)
- `The four minimal OAuth scopes` --implements--> `build_auth_url()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Phase 0.5 auth runbook` --references--> `save_token()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Phase 0.5 auth runbook` --references--> `probe_gmail()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Phase 0.5 auth runbook` --references--> `probe_calendar()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Meet transcripts via Workspace Events` --conceptually_related_to--> `probe_meet()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **The Phase 0.5 auth gate** — docs_phase_plan_phase_0_5_auth_spike, docs_google_auth_workspace_admin_block, docs_decisions_adr_009_personal_gcp_project_onix_data, docs_decisions_adr_012_auth_spike_passed, scripts_auth_spike_main [EXTRACTED 1.00]
- **Cloud Run Job overlap safety net** — docs_architecture_concurrency_idempotency, docs_architecture_skip_locked_claiming, docs_decisions_adr_005_cloud_scheduler_replaces_apscheduler, docs_decisions_adr_006_skip_locked_row_claiming, claude_uuid5_id [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_decisions_adr_013_three_tier_reproducibility_contract, docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, docs_setup_tier_0_local, docs_setup_tier_1_real_llm, docs_setup_tier_2_deploy, scripts_doctor_run_checks, docker_compose_local_postgres_service [EXTRACTED 1.00]

## Communities (13 total, 1 thin omitted)

### Community 0 - "Preflight Doctor"
Cohesion: 0.07
Nodes (66): datetime, doctor exit code contract, Injected-probe check design, doctor.py check contract, build_parser(), check_command(), check_docker_daemon(), check_llm_backend() (+58 more)

### Community 1 - "Pipeline Rules & Graph Schema"
Cohesion: 0.08
Nodes (45): 768-dimensional embedding invariant, Deferred to v2: dev_agent and action_agent, Environment variable surface, Property graph schema, LLM configuration seam, Person.tracked governance gate, Lowercased Topic MERGE key, Deterministic uuid5_id node ids (+37 more)

### Community 2 - "Token Exchange & Credentials"
Cohesion: 0.11
Nodes (30): Request, exchange_code(), load_client_credentials(), pkce_pair(), Exchange an authorization code for tokens., Mint a fresh access token from a stored refresh token., Read the OAuth client id and secret, or explain exactly what's missing., Return a (code_verifier, code_challenge) pair using S256. (+22 more)

### Community 3 - "GCP Infrastructure & Rejected Options"
Cohesion: 0.10
Nodes (28): Airbyte removal, APScheduler removal, Budget alert, Cloud Run Jobs (one per source + drain + nightly), Cloud Scheduler triggering, Cost posture, Dataflow/Datastream rejected, FastAPI Cloud Run service (+20 more)

### Community 4 - "PKCE Consent & Loopback Server"
Cohesion: 0.10
Nodes (22): BaseHTTPRequestHandler, Loopback redirect and prompt=consent, Ephemeral-port loopback callback server, PKCE S256 authorization-code flow, HTTPServer, build_auth_url(), _CallbackHandler, CallbackResult (+14 more)

### Community 5 - "Project Governance & Onix Split"
Cohesion: 0.15
Nodes (24): Intent-to-skill map, Project context digest for agents, Absolute rules, Personal-then-Onix deployment context, meeting-notes-gcp v6, Module boundaries, Repository layout, v1-v6 version lineage (+16 more)

### Community 6 - "Reproducibility & Local Stack"
Cohesion: 0.22
Nodes (22): graphify maintenance discipline, Pinned image tags taken from v5, Memgraph Lab service, Local memgraph-mage service, Local Postgres 15 service, BigQuery as staging rejected, Cloud SQL PostgreSQL 15 staging layer, ADR-013 Three-tier reproducibility contract (+14 more)

### Community 7 - "Token Store & Env Loading"
Cohesion: 0.18
Nodes (16): MonkeyPatch, load_env_file(), load_token(), Path, Write the token 0600.      The mode is set at open time. A write-then-chmod woul, Load a stored token, or None if there isn't one., Load .env into os.environ if it exists. Returns whether a file was found.      A, save_token() (+8 more)

### Community 8 - "API Probes & Consent Flow"
Cohesion: 0.32
Nodes (14): Namespace, _consent(), _error_of(), _probe(), probe_calendar(), probe_gmail(), probe_meet(), ProbeResult (+6 more)

### Community 9 - "Expiry Math & Outcome Report"
Cohesion: 0.19
Nodes (11): A refresh token plus the metadata needed to reason about its expiry., Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, render_report(), StoredToken, The single most important test in this file. docs/GOOGLE_AUTH.md §7., test_age_and_expiry_math(), test_report_distinguishes_reachable_from_transcripts_present(), test_report_never_contains_the_token() (+3 more)

### Community 10 - "Auth Spike Conventions & CLI"
Cohesion: 0.31
Nodes (11): Coding conventions, Never pass event= to structlog, ADR-012 Phase 0.5 auth spike passed, Phase 0.5 auth runbook, The four minimal OAuth scopes, Hand-rolled OAuth over httpx, Phase 0.5 auth spike implementation plan, build_parser() (+3 more)

## Knowledge Gaps
- **5 isolated node(s):** `meeting-notes-gcp`, `Repository layout`, `Intent-to-skill map`, `Stack table`, `Cloud Scheduler triggering`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Phase 0.5 auth spike implementation plan` connect `Auth Spike Conventions & CLI` to `Preflight Doctor`, `Token Exchange & Credentials`, `Project Governance & Onix Split`, `Reproducibility & Local Stack`, `Token Store & Env Loading`, `API Probes & Consent Flow`, `Expiry Math & Outcome Report`?**
  _High betweenness centrality (0.163) - this node is a cross-community bridge._
- **Why does `Phase 0.6 reproducibility implementation plan` connect `Reproducibility & Local Stack` to `Preflight Doctor`, `Pipeline Rules & Graph Schema`, `Auth Spike Conventions & CLI`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `Phase 0.6 Reproducibility skeleton` connect `Reproducibility & Local Stack` to `Preflight Doctor`, `Pipeline Rules & Graph Schema`, `GCP Infrastructure & Rejected Options`, `Project Governance & Onix Split`, `Auth Spike Conventions & CLI`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Phase 0.6 Reproducibility skeleton` (e.g. with `Phase 0.6 reproducibility implementation plan` and `Problem: a stranger can run nothing`) actually correct?**
  _`Phase 0.6 Reproducibility skeleton` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `meeting-notes-gcp`, `Repository layout`, `Intent-to-skill map` to the rest of the system?**
  _5 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Preflight Doctor` be split into smaller, more focused modules?**
  _Cohesion score 0.06720321931589537 - nodes in this community are weakly interconnected._
- **Should `Pipeline Rules & Graph Schema` be split into smaller, more focused modules?**
  _Cohesion score 0.07777777777777778 - nodes in this community are weakly interconnected._