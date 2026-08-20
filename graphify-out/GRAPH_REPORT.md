# Graph Report - meeting-notes-gcp  (2026-08-20)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1088 nodes · 2136 edges · 73 communities (55 shown, 18 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 125 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3faf2ba5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- select_restore_pair
- RecordingRunner
- ADR-018 One StagedRecord with a JSONB payload, not four typed raw tables
- Meet Transcripts & Auth Spike
- FakeTx
- Classifier Gate
- Action Item Dedup
- datetime
- Typed Settings Seam
- Coding Conventions & v5 Bugs
- Token Store & Env Loading
- ADR-013 Three-tier reproducibility contract
- Logging & Retry Helpers
- Meeting Type Router
- Token Expiry Reporting
- LLM Config & Local Stack
- graph_client.py
- sync.py
- Loopback Callback Server
- SyncError
- Swappable LLM Backend Seam
- Pipeline Path Consolidation
- Callback Request Handler
- OAuth Scopes & Consent
- Local Stack Port Shift (55432/57687/57444/53000)
- test_phase01_sync.py
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
- chat_json
- Phase 9 — Hardening
- Quota Project Troubleshooting
- Project Identity
- record_fixtures.py
- ArgumentParser
- datetime
- test_phase04_llm_seam.py
- extract_meeting
- embed
- extractor.py
- Phase 4 — LLM Seam (DONE)
- Phase 2 Pure Core Implementation Plan
- ADR-016 Ephemeral compute, durable storage
- Tier 0 — local, no credentials
- sync-up session start (~11 min)
- ADR-004 Memgraph on GCE VM first, GKE later
- build_system_prompt
- ADR-006 Claim rows with SELECT FOR UPDATE SKIP LOCKED
- Phase 3 Data Layer Implementation Plan
- meeting-notes-gcp

## God Nodes (most connected - your core abstractions)
1. `Settings` - 44 edges
2. `Status` - 36 edges
3. `chat_json()` - 29 edges
4. `CheckResult` - 22 edges
5. `RecordingRunner` - 20 edges
6. `run_checks()` - 19 edges
7. `sync_down()` - 19 edges
8. `Phase 0.5 auth spike implementation plan` - 19 edges
9. `FakeTx` - 18 edges
10. `Principal` - 17 edges

## Surprising Connections (you probably didn't know these)
- `probe_meet()` --conceptually_related_to--> `Meet transcripts via Workspace Events`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `save_token()` --references--> `Phase 0.5 auth runbook`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `render_report()` --conceptually_related_to--> `Secret handling rules`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `start_callback_server()` --implements--> `Loopback redirect and prompt=consent`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `CheckResult` --implements--> `doctor.py check contract`  [INFERRED]
  scripts/doctor.py → docs/superpowers/specs/2026-08-13-clone-and-run-design.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **One staging table gives one claiming query and one drain path** — docs_decisions_adr018, docs_decisions_staged_record_table, docs_decisions_adr006, docs_decisions_adr010, docs_decisions_per_source_adapter [EXTRACTED 1.00]
- **ADR-011's config rule enforced by two refactors and an AST check** — docs_decisions_adr011, docs_superpowers_plans_2026_08_20_phase_2_pure_core_scripts_env_exception [EXTRACTED 1.00]
- **Deferrals Recorded Rather Than Assumed** — docs_superpowers_plans_2026_08_20_phase_3_data_layer_scope_table [EXTRACTED 1.00]
- **Defences Against a Silently-Wrong Extraction** — docs_phase_plan_prompt_carried_byte_for_byte, docs_phase_plan_fixture_keys_cannot_drift, docs_phase_plan_retry_policy_is_a_test, docs_phase_plan_kind_no_repair [EXTRACTED 1.00]
- **What Made Tier 0 Actually Runnable** — docs_phase_plan_four_backend_seam, docs_phase_plan_tier0_replays_offline, docs_superpowers_plans_2026_08_20_phase_4_llm_seam_diverse_corpus, docs_phase_plan_model_names_confirmed_live [EXTRACTED 1.00]
- **Sync session lifecycle: ephemeral tier up, work, backed-up teardown** — docs_setup_iap_tunnel [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks [EXTRACTED 1.00]
- **Keeping v5 Safe While Building v6** — docker_compose_local_port_shift, docker_compose_local_stack [EXTRACTED 1.00]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_decisions_adr005, docs_decisions_adr007, docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Ephemeral sync-up/sync-down lifecycle** — docs_decisions_adr016, docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]

## Communities (73 total, 18 thin omitted)

### Community 0 - "Doctor & Reproducibility Contract"
Cohesion: 0.06
Nodes (83): graphify maintenance discipline, Secret handling rules, No-secrets-in-output guarantee (spike), doctor exit code contract, Injected-probe check design, Leak-canary secret test, Phase 0.6 reproducibility implementation plan, doctor.py check contract (+75 more)

### Community 1 - "Durable Terraform Resources"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 2 - "Ephemeral Terraform Resources"
Cohesion: 0.09
Nodes (34): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+26 more)

### Community 3 - "Meeting Quality Scoring"
Cohesion: 0.08
Nodes (31): composite_quality(), compute_quality(), _per_hour(), percentile_rank(), Any, Phase 31 — meeting quality scoring. The graph doesn't just remember meetings,…, Weighted mean over AVAILABLE (non-None) components, weights renormalized.…, Pure: turn one meeting's raw features into components + composite. ``features``… (+23 more)

### Community 4 - "Project Governance & Schema"
Cohesion: 0.06
Nodes (37): Intent-to-skill map, Project context digest for agents, Absolute rules, Personal-then-Onix deployment context, Property graph schema, meeting-notes-gcp v6, Module boundaries, Person.tracked governance gate (+29 more)

### Community 5 - "Person Resolution"
Cohesion: 0.11
Nodes (30): Attendee, load_roster(), _name_sim(), _norm_name(), normalize_email(), Any, P3 entity resolution: resolve extracted attendees to canonical people. Two…, Resolve one attendee (anything with .name/.email/.role) to a canonical… (+22 more)

### Community 6 - "Pydantic Models & StagedRecord"
Cohesion: 0.08
Nodes (31): BaseModel, field_validator, ActionItem, Decision, ExtractedMeeting, Any, Pydantic models — extraction shapes and the single staging shape. Ported from…, One staged row from any source. `payload` is opaque here on purpose: a per-… (+23 more)

### Community 7 - "Access Control Policy"
Cohesion: 0.12
Nodes (35): AccessDenied, aggregates_only(), authorize(), load_policy(), parse_scope(), Principal, RuntimeError, Phase 33 (core) — principal → scope access policy. Design stance: hierarchy… (+27 more)

### Community 8 - "Shared Utils"
Cohesion: 0.10
Nodes (26): Trend over the last few occurrences of a recurring series. None for a non-…, score_recurrence_health(), extract_ticket_keys(), Return de-duplicated Jira ticket keys found in free text, order-preserving., Local models often wrap JSON responses in ```json ... ``` fences despite being…, strip_json_fences(), Phase 2 — the pure core. No I/O, no network, no database. Every test here runs…, Local models wrap JSON in ```json fences despite being told not to. Found by… (+18 more)

### Community 9 - "PKCE & OAuth Client"
Cohesion: 0.13
Nodes (22): Request, load_client_credentials(), pkce_pair(), Read the OAuth client id and secret, or explain exactly what's missing., Return a (code_verifier, code_challenge) pair using S256., _mock_client(), AsyncClient, Response (+14 more)

### Community 10 - "select_restore_pair"
Cohesion: 0.14
Nodes (14): Choose the export and snapshot to restore the ephemeral tier from. `sync_down`…, The shared timestamp in an export object path or a snapshot name., RestorePlan, select_restore_pair(), stamp_of(), The bug this exists to prevent. A sync-down that writes its export and then…, No matched pair must NOT mean discarding usable data — an export can outlive…, Nothing to restore is a legitimate, consistent state — not a mismatch. (+6 more)

### Community 11 - "RecordingRunner"
Cohesion: 0.12
Nodes (22): _ok(), CompletedProcess, `gcloud compute disks snapshot` operates on a zonal resource and 400s with…, `gcloud compute disks snapshot` exits 0 as soon as the snapshot is created,…, First ever run: no snapshots, no exports. Must still succeed. `gcloud storage…, End-to-end: the orphan export must not reach `gcloud sql import`., terraform reports the VM ready as soon as the API says RUNNING, which is well…, A VM that never finishes bootstrapping is a real problem, but the tier IS up… (+14 more)

### Community 12 - "ADR-018 One StagedRecord with a JSONB payload, not four typed raw tables"
Cohesion: 0.15
Nodes (16): Airbyte removed (§2.1), Decision Log (ADR index), ADR-001 Fresh repository, deliberate port, ADR-007 Build our own connectors, remove Airbyte, ADR-010 Collapse three pipeline paths into one, ADR-018 One StagedRecord with a JSONB payload, not four typed raw tables, AirbyteWebhookPayload deleted, not ported, JSONB payload is opaque to SQL (+8 more)

### Community 13 - "Meet Transcripts & Auth Spike"
Cohesion: 0.25
Nodes (18): Meet transcripts via Workspace Events, Phase 0.5 auth runbook, Meet: reachable vs transcripts-present, Namespace, build_parser(), _consent(), main(), _probe() (+10 more)

### Community 14 - "FakeTx"
Cohesion: 0.09
Nodes (22): ExtractedMeeting, MERGE a whole meeting into the graph in ONE transaction. Meeting, People,…, upsert_meeting_graph(), FakeDriver, FakeSession, FakeTx, _meeting(), Records every Cypher statement instead of running it. (+14 more)

### Community 15 - "Classifier Gate"
Cohesion: 0.11
Nodes (17): classify(), Any, Rules-based "is this worth processing" score. No LLM. Ported from v5…, Two or more noise markers return 0.0 immediately, before any positive signal is…, The gate is >= 2. One stray 'unsubscribe' in a genuine thread is not enough to…, CLASSIFIER_SCORE_THRESHOLD defaults to 0.40., Every signal is individually capped and the total is clamped. Without the clamp…, Signal 7: a record with real calendar times is more likely a meeting. (+9 more)

### Community 16 - "Action Item Dedup"
Cohesion: 0.09
Nodes (24): best_match(), cosine(), _norm(), Any, P5 dedup decision: is a new action item a duplicate of an existing open one?…, Return the best candidate above ``threshold`` (with its ``score``), or None., similarity(), An all-zero embedding is what a failed embed() call looks like. It must return… (+16 more)

### Community 17 - "datetime"
Cohesion: 0.25
Nodes (11): datetime, export_object_name(), Compact UTC timestamp. Lowercase so it is legal in a GCE resource name, and…, GCS object path for a Cloud SQL export., GCE snapshot name for the Memgraph data disk. Must match…, snapshot_name(), _stamp(), GCE names must match [a-z]([-a-z0-9]*[a-z0-9])? and be <= 63 chars. (+3 more)

### Community 18 - "Typed Settings Seam"
Cohesion: 0.12
Nodes (17): BaseSettings, Settings, Settings must be constructible from an explicit dict so tests never depend on…, A clone with no .env at all must default to the offline backend — that is what…, Both Memgraph vector indexes are built for 768. Changing this without migrating…, Tier 0 and tier 1 must run the pipeline fully and create no tickets., ADR-015: db.py branches on this to pick its connection mode., test_cloud_sql_connection_name_blank_means_local() (+9 more)

### Community 19 - "Coding Conventions & v5 Bugs"
Cohesion: 0.17
Nodes (16): Coding conventions, Never pass event= to structlog, Bug 3: structlog reserved kwarg, Hand-rolled OAuth over httpx, Phase 0.5 auth spike implementation plan, _error_of(), exchange_code(), Response (+8 more)

### Community 20 - "Token Store & Env Loading"
Cohesion: 0.18
Nodes (16): MonkeyPatch, load_env_file(), load_token(), Path, Write the token 0600.      The mode is set at open time. A write-then-chmod woul, Load a stored token, or None if there isn't one., Load .env into os.environ if it exists. Returns whether a file was found.      A, save_token() (+8 more)

### Community 21 - "ADR-013 Three-tier reproducibility contract"
Cohesion: 0.27
Nodes (10): LM Studio becomes one of two LLM backends (§2.3), ADR-002 Vertex AI Gemini default behind a swappable seam, ADR-011 config.py is the only reader of os.environ, ADR-013 Three-tier reproducibility contract, ADR-014 fake fixture-replay backend and gemini tier-1 backend, ADR-015 db.py selects connection mode on configuration, Troubleshooting — Cloud SQL Proxy v2 not found in PATH, scripts/sync.py — sync lifecycle orchestration (+2 more)

### Community 22 - "Logging & Retry Helpers"
Cohesion: 0.10
Nodes (20): BoundLogger, date, F, configure_logging(), priority_from_due(), Shared helpers with no I/O: deterministic ids, retries, logging, parsing.…, Map a due date to a Jira priority. No due date is 'low', not 'medium'., Deterministic id for a node. Two-step on purpose: derive a per-namespace UUID… (+12 more)

### Community 23 - "Meeting Type Router"
Cohesion: 0.14
Nodes (13): prompt_hint(), P6 meeting-type routing: a cheap classifier between classify() and…, Return the meeting type for `title`/`text`. Email sources are always…, Return the type-specific instruction appended to the extractor system prompt., route(), Source type wins over any keyword in the subject., Order matters: 'session' lives in review's keywords and would otherwise swallow…, Everything except the deliberate `general` no-op must actually say something,… (+5 more)

### Community 24 - "Token Expiry Reporting"
Cohesion: 0.19
Nodes (11): A refresh token plus the metadata needed to reason about its expiry., Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, render_report(), StoredToken, The single most important test in this file. docs/GOOGLE_AUTH.md §7., test_age_and_expiry_math(), test_report_distinguishes_reachable_from_transcripts_present(), test_report_never_contains_the_token() (+3 more)

### Community 25 - "LLM Config & Local Stack"
Cohesion: 0.38
Nodes (7): 768-dimensional embedding invariant, Environment variable surface, LLM configuration seam, Bug 4: literal 'null' strings from the LLM, Hash-keyed fixture replay, Four LLM backends behind one protocol, Reproducibility risks

### Community 26 - "graph_client.py"
Cohesion: 0.11
Nodes (30): AsyncDriver, get_settings(), Typed settings — the ONLY module in this package that reads os.environ. Every…, Process-wide settings. Cached so the .env file is read once. Tests should…, close_driver(), get_action_confidence(), get_driver(), get_known_people() (+22 more)

### Community 27 - "sync.py"
Cohesion: 0.23
Nodes (16): Runner, build_parser(), main(), CompletedProcess, Default runner. Captures output so failures can be reported with context., Raise unless the command succeeded. Every destructive step in sync_down is…, Back up, verify the backup, then destroy the ephemeral tier. Ordering is a…, Block until the Memgraph stack is actually serving, or give up. Terraform… (+8 more)

### Community 28 - "Loopback Callback Server"
Cohesion: 0.24
Nodes (12): Ephemeral-port loopback callback server, HTTPServer, CallbackServer, An HTTPServer that captures a single OAuth callback., Bind an ephemeral loopback port and return the server and its redirect URI., Block until the callback arrives, then validate it and return the code., start_callback_server(), wait_for_code() (+4 more)

### Community 29 - "SyncError"
Cohesion: 0.19
Nodes (13): RuntimeError, A sync step failed. Raised rather than returned so no caller can accidentally…, SyncError, _fail(), The single most important test in this file. A failed export followed by a…, gcloud sql export can exit 0 having written nothing usable. Verify the object,…, Only the specific 'matched no objects' message is tolerated. Any other storage…, The console is not readable in the first seconds after boot. A failed read is… (+5 more)

### Community 30 - "Swappable LLM Backend Seam"
Cohesion: 0.10
Nodes (29): integration, build_dsn(), Plain-Postgres DSN. Only used when the Cloud SQL connector is not., _local_settings(), _norm(), Phase 3 — the data layer. Runs with no Postgres and no Memgraph. The claiming…, Point at the local compose Postgres regardless of the developer's .env., The ADR-006 guarantee, proven against a real Postgres. SKIP LOCKED is server-… (+21 more)

### Community 31 - "Pipeline Path Consolidation"
Cohesion: 0.12
Nodes (23): apply_migrations(), claim_batch(), close_pool(), get_pool(), _main(), mark_processed(), Any, Cloud SQL staging — the ONLY module in this package containing SQL.… (+15 more)

### Community 32 - "Callback Request Handler"
Cohesion: 0.29
Nodes (4): BaseHTTPRequestHandler, _CallbackHandler, CallbackResult, Silence the default stderr access log.          It would echo the query string,

### Community 33 - "OAuth Scopes & Consent"
Cohesion: 0.38
Nodes (7): Loopback redirect and prompt=consent, The four minimal OAuth scopes, PKCE S256 authorization-code flow, build_auth_url(), Build the Google consent URL.      access_type=offline and prompt=consent are bo, test_auth_url_carries_offline_and_consent(), test_auth_url_requests_exactly_the_four_scopes()

### Community 35 - "test_phase01_sync.py"
Cohesion: 0.23
Nodes (11): backup_uri(), Name of the most recent item, or None if there are none. None is a legitimate…, select_latest(), Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016. Every test runs with…, The first-ever sync-up has no snapshot and no export. Not an error., A missing timestamp means gcloud changed its output shape. Fail loudly rather…, test_backup_uri_builds_a_gs_url(), test_select_latest_picks_the_most_recent() (+3 more)

### Community 36 - "Auth Risks & Onix Split"
Cohesion: 0.17
Nodes (12): Every schema statement, in application order. Returned rather than executed so…, statements(), CLAUDE.md's schema: every node has a unique id. A label with no constraint…, ADR-008: provenance cannot be backfilled. A merge that happens before the…, CLAUDE.md: 768 in both backends because the indexes are built for 768.…, If someone migrates the indexes, the setting is the single knob., Memgraph takes one statement per run(); a semicolon-joined blob fails., test_both_vector_indexes_use_the_configured_dimension() (+4 more)

### Community 39 - "Backup Verified Before Destroy"
Cohesion: 0.67
Nodes (3): Export/snapshot verification before destroy, sync_down(), SyncError exception

### Community 49 - "chat_json"
Cohesion: 0.10
Nodes (29): chat_json(), _default_transport(), _fake_chat_json(), fixture_dir(), FixtureMiss, _gemini_chat_request(), _gemini_text(), _lmstudio_chat_request() (+21 more)

### Community 53 - "record_fixtures.py"
Cohesion: 0.15
Nodes (18): ArgumentParser, RuntimeError, build_parser(), fetch_one(), load_corpus(), main(), prompts_for(), Any (+10 more)

### Community 59 - "test_phase04_llm_seam.py"
Cohesion: 0.10
Nodes (29): fixture_key(), _loads_lenient(), Stable, filename-safe key for a prompt. Covers the system prompt so editing it…, Parse JSON, tolerating a model that wraps the object in stray prose. Tries a…, select_backend(), Phase 4 — the LLM seam. Runs with no network, no API key, no LM Studio. Every…, Tier 0 must work on a clean clone with no .env at all., Observed live: models narrate around the object despite instructions. (+21 more)

### Community 60 - "extract_meeting"
Cohesion: 0.15
Nodes (22): extract_meeting(), Extract one meeting. Returns None if the model output cannot be used. Retry…, _fake_settings(), Path, Semantic-search tests need vectors that are stable across runs yet still…, The indexes use cosine similarity; unit vectors keep scores comparable., The exit criterion, on the fake backend: a recorded response in, a validated…, The invariant this whole mechanism rests on. CLAUDE.md calls writer/reader id… (+14 more)

### Community 61 - "embed"
Cohesion: 0.11
Nodes (20): embed(), _fake_vector(), A deterministic unit vector derived from the text. Stable across runs so…, Embed one string. Always `embedding_dimension` long, in every backend., _lmstudio_settings(), A timeout or 5xx is transient — retry it., At temperature 0 an identical retry yields identical output, so retrying a…, CLAUDE.md: temperature is 0.0 for extraction. Always. (+12 more)

### Community 62 - "extractor.py"
Cohesion: 0.12
Nodes (17): _is_null_like(), Any, LLM extraction — v5's tuned prompt, v6's swappable client. The system prompt…, True for None/empty AND for a model that emits the literal string "null"…, Fill required fields the model left null-like, in place. Carried from v5…, repair(), Tuned prompt text. Data, not logic. The extraction prompt is carried over from…, gemma3-12b emits the literal string "null" for optional fields. A plain `if not… (+9 more)

### Community 63 - "Phase 4 — LLM Seam (DONE)"
Cohesion: 0.25
Nodes (11): Fixture Keys Cannot Drift, Four Backends Behind One Protocol, Where v5's Parsing Helpers Landed, kind Is Deliberately Not Repaired, Vertex Model Names Confirmed Live, Phase 4 — LLM Seam (DONE), Extraction Prompt Carried Byte for Byte, Retry Policy Is Now a Test, Not a Comment (+3 more)

### Community 64 - "Phase 2 Pure Core Implementation Plan"
Cohesion: 0.20
Nodes (11): Phase 2 Pure Core Implementation Plan, ExtractedMeeting.kind vs router.TYPES vocabulary collision, Task 10 — verify exit criteria and close the phase, Task 2 — utils.py port with uuid5_id pinned, Task 4 — classifier.py port plus the tests v5 never had, Task 5 — meeting_type_router.py, vocabularies pinned apart, Task 6 — dedup.py, Task 7 — person_resolver.py, roster injected (+3 more)

### Community 65 - "ADR-016 Ephemeral compute, durable storage"
Cohesion: 0.25
Nodes (8): Durable resource tier, Ephemeral resource tier, GCP resource inventory (§4), ADR-016 Ephemeral compute, durable storage, terraform/durable module, terraform/ephemeral module, Task 0: Billing gate, Task 11: Live validation

### Community 66 - "Tier 0 — local, no credentials"
Cohesion: 0.32
Nodes (8): Durable-tier one-time apply, The part nobody can automate — OAuth console setup, Tier 0 — local, no credentials, Tier 1 — real LLM, Tier 2 — deploy to your own GCP, Troubleshooting — Error 401 invalid_client during consent, Troubleshooting — local port already in use, Three-tier reproducibility (0/1/2)

### Community 67 - "sync-up session start (~11 min)"
Cohesion: 0.29
Nodes (7): ADR-017 Phase 1 validated live, sync lifecycle works, make doctor — tier-aware preflight, Measured sync timings in the tier-2 walkthrough, The 7-day clock in the tier-2 runbook, sync-down session end (~3 min), sync-up session start (~11 min), Troubleshooting — worked yesterday, fails today

### Community 68 - "ADR-004 Memgraph on GCE VM first, GKE later"
Cohesion: 0.33
Nodes (6): BigQuery as the staging layer — rejected, GKE Autopilot from day one — deferred, Spanner Graph instead of Memgraph — rejected, ADR-003 Keep Memgraph, reject Spanner Graph, ADR-004 Memgraph on GCE VM first, GKE later, IAP tunnel to Memgraph Bolt

### Community 69 - "build_system_prompt"
Cohesion: 0.40
Nodes (5): build_system_prompt(), The system prompt, optionally with meeting-type guidance appended. The router's…, meeting_type_router's hint must actually reach the model, or routing is…, test_no_type_hint_leaves_the_prompt_untouched(), test_type_hint_is_appended_to_the_system_prompt()

### Community 70 - "ADR-006 Claim rows with SELECT FOR UPDATE SKIP LOCKED"
Cohesion: 0.50
Nodes (4): APScheduler removed → Cloud Scheduler + Cloud Run Jobs (§2.2), Concurrency, idempotency, exactly-once (§6), ADR-005 Cloud Scheduler + Cloud Run Jobs replace APScheduler, ADR-006 Claim rows with SELECT FOR UPDATE SKIP LOCKED

## Knowledge Gaps
- **44 isolated node(s):** `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image`, `var.memgraph_machine`, `var.memgraph_restore_snapshot` (+39 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Typed Settings Seam` to `Shared Utils`, `chat_json`, `record_fixtures.py`, `Swappable LLM Backend Seam`, `graph_client.py`, `test_phase04_llm_seam.py`, `extract_meeting`, `embed`, `extractor.py`, `Pipeline Path Consolidation`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Why does `meeting-notes-gcp v6` connect `Project Governance & Schema` to `Tier 0 — local, no credentials`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `check_token_age()` connect `Doctor & Reproducibility Contract` to `datetime`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `Settings` (e.g. with `extract_meeting()` and `chat_json()`) actually correct?**
  _`Settings` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `Status` (e.g. with `doctor.py check contract` and `test_blank_secret_counts_as_unset()`) actually correct?**
  _`Status` has 32 INFERRED edges - model-reasoned connections that need verification._
- **What connects `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image` to the rest of the system?**
  _44 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Doctor & Reproducibility Contract` be split into smaller, more focused modules?**
  _Cohesion score 0.0636193531141406 - nodes in this community are weakly interconnected._