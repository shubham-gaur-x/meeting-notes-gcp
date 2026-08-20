# Graph Report - meeting-notes-gcp  (2026-08-20)

## Corpus Check
- 17 files · ~64,628 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 823 nodes · 1602 edges · 59 communities (44 shown, 15 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 123 edges (avg confidence: 0.9)
- Token cost: 120,823 input · 0 output

## Community Hubs (Navigation)
- Doctor & Reproducibility Contract
- Durable Terraform Resources
- Ephemeral Terraform Resources
- Meeting Quality Scoring
- Project Governance & Schema
- Person Resolution
- Pydantic Models & StagedRecord
- Access Control Policy
- Shared Utils
- PKCE & OAuth Client
- Sync Restore Pairing
- Sync Safety Tests
- ADR Log & Rearchitecture
- Meet Transcripts & Auth Spike
- Phase Plan & Phase 2 Outcome
- Classifier Gate
- Action Item Dedup
- sync.py CLI
- Typed Settings Seam
- Coding Conventions & v5 Bugs
- Token Store & Env Loading
- Rejected Backends
- Logging & Retry Helpers
- Meeting Type Router
- Token Expiry Reporting
- LLM Config & Local Stack
- Durable/Ephemeral Cost Model
- Injected Command Runner
- Loopback Callback Server
- SyncError Contract
- Swappable LLM Backend Seam
- Pipeline Path Consolidation
- Callback Request Handler
- OAuth Scopes & Consent
- Deterministic Node Ids
- Memgraph Bootstrap Wait
- Auth Risks & Onix Split
- Vocabulary Collision Pins
- Cypher Scope Filter
- Backup Verified Before Destroy
- Package Init
- State Bucket Bootstrap
- Memgraph VM Bootstrap
- Deferred v2 Agents
- Cost Posture
- Dataflow Rejection
- Leiden Fragmentation Bug
- Porting Order
- Phase 7 — Graph Intelligence
- Phase 9 — Hardening
- Quota Project Troubleshooting
- Project Identity
- RuntimeError
- ArgumentParser
- datetime

## God Nodes (most connected - your core abstractions)
1. `Status` - 36 edges
2. `CheckResult` - 22 edges
3. `Phase 0.6 reproducibility implementation plan` - 20 edges
4. `RecordingRunner` - 20 edges
5. `run_checks()` - 19 edges
6. `Phase 0.5 auth spike implementation plan` - 19 edges
7. `sync_down()` - 19 edges
8. `Principal` - 17 edges
9. `sync_up()` - 16 edges
10. `authorize()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Secret handling rules` --conceptually_related_to--> `render_report()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Meet transcripts via Workspace Events` --conceptually_related_to--> `probe_meet()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Loopback redirect and prompt=consent` --implements--> `start_callback_server()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `Phase 0.5 auth runbook` --references--> `save_token()`  [INFERRED]
  docs/GOOGLE_AUTH.md → scripts/auth_spike.py
- `doctor.py check contract` --implements--> `CheckResult`  [INFERRED]
  docs/superpowers/specs/2026-08-13-clone-and-run-design.md → scripts/doctor.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **One staging table gives one claiming query and one drain path** — docs_decisions_adr018, docs_decisions_staged_record_table, docs_decisions_adr006, docs_decisions_adr010, docs_decisions_per_source_adapter [EXTRACTED 1.00]
- **Phase 2 DONE: green suite, AST-verified config rule, governance bug fixed, two deferrals** — docs_phase_plan_phase2, docs_phase_plan_phase2_187_tests_green, docs_phase_plan_ast_verification_of_config_only_env_reader, docs_phase_plan_person_resolver_tracked_governance_bug, docs_phase_plan_deferred_person_resolution_upsert, docs_phase_plan_deferred_score_all_meetings [EXTRACTED 1.00]
- **ADR-011's config rule enforced by two refactors and an AST check** — docs_decisions_adr011, docs_phase_plan_load_roster_explicit_path, docs_phase_plan_load_policy_explicit_path, docs_phase_plan_ast_verification_of_config_only_env_reader, docs_superpowers_plans_2026_08_20_phase_2_pure_core_scripts_env_exception [EXTRACTED 1.00]
- **Sync session lifecycle: ephemeral tier up, work, backed-up teardown** — docs_setup_iap_tunnel [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks, docker_compose_local_postgres_service [EXTRACTED 1.00]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_decisions_adr005, docs_decisions_adr007, docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Ephemeral sync-up/sync-down lifecycle** — docs_decisions_adr016, docs_phase_plan_phase1, docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]

## Communities (59 total, 15 thin omitted)

### Community 0 - "Doctor & Reproducibility Contract"
Cohesion: 0.06
Nodes (83): graphify maintenance discipline, Secret handling rules, Standing exit criterion for Phases 1–9, No-secrets-in-output guarantee (spike), doctor exit code contract, Injected-probe check design, Leak-canary secret test, Phase 0.6 reproducibility implementation plan (+75 more)

### Community 1 - "Durable Terraform Resources"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 2 - "Ephemeral Terraform Resources"
Cohesion: 0.09
Nodes (34): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+26 more)

### Community 3 - "Meeting Quality Scoring"
Cohesion: 0.07
Nodes (35): composite_quality(), compute_quality(), _per_hour(), percentile_rank(), Any, Phase 31 — meeting quality scoring. The graph doesn't just remember meetings,…, Weighted mean over AVAILABLE (non-None) components, weights renormalized.…, Pure: turn one meeting's raw features into components + composite. ``features``… (+27 more)

### Community 4 - "Project Governance & Schema"
Cohesion: 0.07
Nodes (34): Intent-to-skill map, Project context digest for agents, Absolute rules, Personal-then-Onix deployment context, Property graph schema, meeting-notes-gcp v6, Module boundaries, Person.tracked governance gate (+26 more)

### Community 5 - "Person Resolution"
Cohesion: 0.11
Nodes (30): Attendee, load_roster(), _name_sim(), _norm_name(), normalize_email(), Any, P3 entity resolution: resolve extracted attendees to canonical people. Two…, Resolve one attendee (anything with .name/.email/.role) to a canonical… (+22 more)

### Community 6 - "Pydantic Models & StagedRecord"
Cohesion: 0.08
Nodes (31): BaseModel, field_validator, ActionItem, Decision, ExtractedMeeting, Any, Pydantic models — extraction shapes and the single staging shape. Ported from…, One staged row from any source. `payload` is opaque here on purpose: a per-… (+23 more)

### Community 7 - "Access Control Policy"
Cohesion: 0.14
Nodes (31): AccessDenied, aggregates_only(), authorize(), load_policy(), parse_scope(), Principal, RuntimeError, Phase 33 (core) — principal → scope access policy. Design stance: hierarchy… (+23 more)

### Community 8 - "Shared Utils"
Cohesion: 0.09
Nodes (29): cosine(), extract_ticket_keys(), Return de-duplicated Jira ticket keys found in free text, order-preserving., Local models often wrap JSON responses in ```json ... ``` fences despite being…, strip_json_fences(), Phase 2 — the pure core. No I/O, no network, no database. Every test here runs…, Local models wrap JSON in ```json fences despite being told not to. Found by…, MIGRATION_FROM_V5.md §4 — Airbyte residue must not be ported. (+21 more)

### Community 9 - "PKCE & OAuth Client"
Cohesion: 0.13
Nodes (22): Request, load_client_credentials(), pkce_pair(), Read the OAuth client id and secret, or explain exactly what's missing., Return a (code_verifier, code_challenge) pair using S256., _mock_client(), AsyncClient, Response (+14 more)

### Community 10 - "Sync Restore Pairing"
Cohesion: 0.12
Nodes (22): backup_uri(), Choose the export and snapshot to restore the ephemeral tier from. `sync_down`…, Name of the most recent item, or None if there are none. None is a legitimate…, RestorePlan, select_latest(), select_restore_pair(), Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016. Every test runs with…, The bug this exists to prevent. A sync-down that writes its export and then… (+14 more)

### Community 11 - "Sync Safety Tests"
Cohesion: 0.13
Nodes (19): _ok(), CompletedProcess, `gcloud compute disks snapshot` operates on a zonal resource and 400s with…, `gcloud compute disks snapshot` exits 0 as soon as the snapshot is created,…, First ever run: no snapshots, no exports. Must still succeed. `gcloud storage…, End-to-end: the orphan export must not reach `gcloud sql import`., A VM that never finishes bootstrapping is a real problem, but the tier IS up…, sync-up must not announce the tier is serving before it is. (+11 more)

### Community 12 - "ADR Log & Rearchitecture"
Cohesion: 0.11
Nodes (21): Airbyte removed (§2.1), APScheduler removed → Cloud Scheduler + Cloud Run Jobs (§2.2), Concurrency, idempotency, exactly-once (§6), Decision Log (ADR index), ADR-001 Fresh repository, deliberate port, ADR-005 Cloud Scheduler + Cloud Run Jobs replace APScheduler, ADR-006 Claim rows with SELECT FOR UPDATE SKIP LOCKED, ADR-007 Build our own connectors, remove Airbyte (+13 more)

### Community 13 - "Meet Transcripts & Auth Spike"
Cohesion: 0.25
Nodes (18): Meet transcripts via Workspace Events, Phase 0.5 auth runbook, Meet: reachable vs transcripts-present, Namespace, build_parser(), _consent(), main(), _probe() (+10 more)

### Community 14 - "Phase Plan & Phase 2 Outcome"
Cohesion: 0.18
Nodes (18): Phase Plan (build order), AST verification that config.py is the package's only env reader, Deferred to Phase 3: person resolution into the graph, Deferred to Phase 3: meeting_quality.score_all_meetings, Four plan assumptions corrected by reading v5 first, access_control.load_policy takes an explicit path, person_resolver.load_roster takes an explicit path, v5 governance bug: Person.tracked read off a leaked loop variable (+10 more)

### Community 15 - "Classifier Gate"
Cohesion: 0.11
Nodes (17): classify(), Any, Rules-based "is this worth processing" score. No LLM. Ported from v5…, Two or more noise markers return 0.0 immediately, before any positive signal is…, The gate is >= 2. One stray 'unsubscribe' in a genuine thread is not enough to…, CLASSIFIER_SCORE_THRESHOLD defaults to 0.40., Every signal is individually capped and the total is clamped. Without the clamp…, Signal 7: a record with real calendar times is more likely a meeting. (+9 more)

### Community 16 - "Action Item Dedup"
Cohesion: 0.13
Nodes (17): best_match(), _norm(), Any, P5 dedup decision: is a new action item a duplicate of an existing open one?…, Return the best candidate above ``threshold`` (with its ``score``), or None., similarity(), Dedup must still work when embeddings are unavailable — the text path is the…, Identical text but orthogonal embeddings must score by the embedding —… (+9 more)

### Community 17 - "sync.py CLI"
Cohesion: 0.18
Nodes (16): ArgumentParser, datetime, build_parser(), export_object_name(), main(), Compact UTC timestamp. Lowercase so it is legal in a GCE resource name, and…, GCS object path for a Cloud SQL export., GCE snapshot name for the Memgraph data disk. Must match… (+8 more)

### Community 18 - "Typed Settings Seam"
Cohesion: 0.12
Nodes (16): BaseSettings, get_settings(), Typed settings — the ONLY module in this package that reads os.environ. Every…, Process-wide settings. Cached so the .env file is read once. Tests should…, Settings, Settings must be constructible from an explicit dict so tests never depend on…, A clone with no .env at all must default to the offline backend — that is what…, Both Memgraph vector indexes are built for 768. Changing this without migrating… (+8 more)

### Community 19 - "Coding Conventions & v5 Bugs"
Cohesion: 0.17
Nodes (16): Coding conventions, Never pass event= to structlog, Bug 3: structlog reserved kwarg, Hand-rolled OAuth over httpx, Phase 0.5 auth spike implementation plan, _error_of(), exchange_code(), Response (+8 more)

### Community 20 - "Token Store & Env Loading"
Cohesion: 0.18
Nodes (16): MonkeyPatch, load_env_file(), load_token(), Path, Write the token 0600.      The mode is set at open time. A write-then-chmod woul, Load a stored token, or None if there isn't one., Load .env into os.environ if it exists. Returns whether a file was found.      A, save_token() (+8 more)

### Community 21 - "Rejected Backends"
Cohesion: 0.13
Nodes (15): BigQuery as the staging layer — rejected, GKE Autopilot from day one — deferred, Spanner Graph instead of Memgraph — rejected, ADR-003 Keep Memgraph, reject Spanner Graph, ADR-004 Memgraph on GCE VM first, GKE later, ADR-008 Defer dev_agent and action_agent, ship provenance schema in v1, Phase 8 — API and dashboard, v2 deferred scope (dev_agent, action_agent, push notifications, GKE) (+7 more)

### Community 22 - "Logging & Retry Helpers"
Cohesion: 0.14
Nodes (13): BoundLogger, date, F, configure_logging(), priority_from_due(), Shared helpers with no I/O: deterministic ids, retries, logging, parsing.…, Map a due date to a Jira priority. No due date is 'low', not 'medium'., Retry an async callable with exponential backoff. Async only — the wrapper… (+5 more)

### Community 23 - "Meeting Type Router"
Cohesion: 0.14
Nodes (13): prompt_hint(), P6 meeting-type routing: a cheap classifier between classify() and…, Return the meeting type for `title`/`text`. Email sources are always…, Return the type-specific instruction appended to the extractor system prompt., route(), Source type wins over any keyword in the subject., Order matters: 'session' lives in review's keywords and would otherwise swallow…, Everything except the deliberate `general` no-op must actually say something,… (+5 more)

### Community 24 - "Token Expiry Reporting"
Cohesion: 0.19
Nodes (11): A refresh token plus the metadata needed to reason about its expiry., Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, render_report(), StoredToken, The single most important test in this file. docs/GOOGLE_AUTH.md §7., test_age_and_expiry_math(), test_report_distinguishes_reachable_from_transcripts_present(), test_report_never_contains_the_token() (+3 more)

### Community 25 - "LLM Config & Local Stack"
Cohesion: 0.22
Nodes (13): 768-dimensional embedding invariant, Environment variable surface, LLM configuration seam, Pinned image tags taken from v5, Memgraph Lab service, Local memgraph-mage service, Local Postgres 15 service, Bug 4: literal 'null' strings from the LLM (+5 more)

### Community 26 - "Durable/Ephemeral Cost Model"
Cohesion: 0.19
Nodes (12): Durable resource tier, Ephemeral resource tier, GCP resource inventory (§4), ADR-016 Ephemeral compute, durable storage, ADR-017 Phase 1 validated live, sync lifecycle works, Phase 1 — Terraform foundation (DONE), Measured sync timings in the tier-2 walkthrough, terraform/durable module (+4 more)

### Community 27 - "Injected Command Runner"
Cohesion: 0.22
Nodes (13): Runner, CompletedProcess, Default runner. Captures output so failures can be reported with context., Raise unless the command succeeded. Every destructive step in sync_down is…, Back up, verify the backup, then destroy the ephemeral tier. Ordering is a…, Recreate the ephemeral tier, restoring the newest matched backup pair., _require(), run() (+5 more)

### Community 28 - "Loopback Callback Server"
Cohesion: 0.24
Nodes (12): Ephemeral-port loopback callback server, HTTPServer, CallbackServer, An HTTPServer that captures a single OAuth callback., Bind an ephemeral loopback port and return the server and its redirect URI., Block until the callback arrives, then validate it and return the code., start_callback_server(), wait_for_code() (+4 more)

### Community 29 - "SyncError Contract"
Cohesion: 0.24
Nodes (11): RuntimeError, A sync step failed. Raised rather than returned so no caller can accidentally…, SyncError, _fail(), The single most important test in this file. A failed export followed by a…, gcloud sql export can exit 0 having written nothing usable. Verify the object,…, Only the specific 'matched no objects' message is tolerated. Any other storage…, test_sync_down_never_destroys_when_the_export_object_is_missing() (+3 more)

### Community 30 - "Swappable LLM Backend Seam"
Cohesion: 0.31
Nodes (10): LM Studio becomes one of two LLM backends (§2.3), ADR-002 Vertex AI Gemini default behind a swappable seam, ADR-011 config.py is the only reader of os.environ, ADR-013 Three-tier reproducibility contract, ADR-014 fake fixture-replay backend and gemini tier-1 backend, ADR-015 db.py selects connection mode on configuration, Phase 0.6 — Reproducibility skeleton, Phase 4 — LLM seam (+2 more)

### Community 31 - "Pipeline Path Consolidation"
Cohesion: 0.24
Nodes (10): ADR-010 Collapse three pipeline paths into one, Phase 6 — Pipeline, Durable-tier one-time apply, The part nobody can automate — OAuth console setup, Tier 0 — local, no credentials, Tier 1 — real LLM, Tier 2 — deploy to your own GCP, Troubleshooting — Error 401 invalid_client during consent (+2 more)

### Community 32 - "Callback Request Handler"
Cohesion: 0.29
Nodes (4): BaseHTTPRequestHandler, _CallbackHandler, CallbackResult, Silence the default stderr access log.          It would echo the query string,

### Community 33 - "OAuth Scopes & Consent"
Cohesion: 0.38
Nodes (7): Loopback redirect and prompt=consent, The four minimal OAuth scopes, PKCE S256 authorization-code flow, build_auth_url(), Build the Google consent URL.      access_type=offline and prompt=consent are bo, test_auth_url_carries_offline_and_consent(), test_auth_url_requests_exactly_the_four_scopes()

### Community 34 - "Deterministic Node Ids"
Cohesion: 0.29
Nodes (7): Deterministic id for a node. Two-step on purpose: derive a per-namespace UUID…, uuid5_id(), The whole MERGE-not-CREATE strategy rests on this. Same input, same id, forever…, Pinned against v5's exact construction: a uuid5 of the namespace string under…, test_uuid5_id_is_deterministic(), test_uuid5_id_matches_the_value_v5_produces(), test_uuid5_id_separates_namespaces()

### Community 35 - "Memgraph Bootstrap Wait"
Cohesion: 0.29
Nodes (7): Block until the Memgraph stack is actually serving, or give up. Terraform…, wait_for_memgraph(), terraform reports the VM ready as soon as the API says RUNNING, which is well…, The console is not readable in the first seconds after boot. A failed read is…, test_wait_for_memgraph_polls_until_the_marker_shows_up(), test_wait_for_memgraph_returns_when_the_marker_appears(), test_wait_for_memgraph_tolerates_a_failing_serial_console_read()

### Community 36 - "Auth Risks & Onix Split"
Cohesion: 0.33
Nodes (6): Known risks (§8), ADR-009 Personal GCP project, Onix Workspace data, ADR-012 Phase 0.5 auth spike passed, Phase 0.5 — Auth spike (DONE), Phase 10 — Onix migration, Troubleshooting — consent succeeds but API calls 403

### Community 37 - "Vocabulary Collision Pins"
Cohesion: 0.50
Nodes (4): ExtractedMeeting.kind vs router.TYPES vocabulary collision, Task 2 — utils.py port with uuid5_id pinned, Task 5 — meeting_type_router.py, vocabularies pinned apart, uuid5_id byte-identical pinning against v5

### Community 38 - "Cypher Scope Filter"
Cohesion: 0.50
Nodes (4): Property filter that ``memgraph_client`` injects into generated Cypher. Returns…, scope_predicate(), This dict is injected into generated Cypher — an empty dict for org is…, test_scope_predicate_filters_team_and_project_but_not_org()

### Community 39 - "Backup Verified Before Destroy"
Cohesion: 0.67
Nodes (3): Export/snapshot verification before destroy, sync_down(), SyncError exception

## Knowledge Gaps
- **41 isolated node(s):** `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image`, `var.memgraph_machine`, `var.memgraph_restore_snapshot` (+36 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Phase 0.6 reproducibility implementation plan` connect `Doctor & Reproducibility Contract` to `LLM Config & Local Stack`, `Coding Conventions & v5 Bugs`?**
  _High betweenness centrality (0.179) - this node is a cross-community bridge._
- **Why does `Standing exit criterion for Phases 1–9` connect `Doctor & Reproducibility Contract` to `Swappable LLM Backend Seam`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Why does `ADR-013 Three-tier reproducibility contract` connect `Swappable LLM Backend Seam` to `Doctor & Reproducibility Contract`, `Rejected Backends`, `Pipeline Path Consolidation`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `Status` (e.g. with `doctor.py check contract` and `test_blank_secret_counts_as_unset()`) actually correct?**
  _`Status` has 32 INFERRED edges - model-reasoned connections that need verification._
- **What connects `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image` to the rest of the system?**
  _41 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Doctor & Reproducibility Contract` be split into smaller, more focused modules?**
  _Cohesion score 0.06269592476489028 - nodes in this community are weakly interconnected._
- **Should `Durable Terraform Resources` be split into smaller, more focused modules?**
  _Cohesion score 0.06271186440677966 - nodes in this community are weakly interconnected._