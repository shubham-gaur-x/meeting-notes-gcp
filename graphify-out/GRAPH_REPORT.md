# Graph Report - meeting-notes-gcp  (2026-08-20)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1326 nodes · 2626 edges · 85 communities (64 shown, 21 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 147 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7fefd210`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Doctor & Reproducibility Contract
- Durable Terraform Resources
- Ephemeral Terraform Resources
- meeting_quality.py
- meeting-notes-gcp v6
- Person Resolution
- Pydantic Models & StagedRecord
- Access Control Policy
- test_phase02_pure_core.py
- test_phase05_auth_spike.py
- select_restore_pair
- RecordingRunner
- ADR-018 One StagedRecord with a JSONB payload, not four typed raw tables
- auth_spike.py
- FakeTx
- Classifier Gate
- similarity
- datetime
- db.py
- Phase 0.5 auth spike implementation plan
- Token Store & Env Loading
- ADR-013 Three-tier reproducibility contract
- Logging & Retry Helpers
- Meeting Type Router
- ProbeResult
- LLM Config & Local Stack
- graph_client.py
- sync.py
- Loopback Callback Server
- SyncError
- test_phase03_data_layer.py
- get_access_token
- Callback Request Handler
- build_auth_url
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
- Settings
- Phase 9 — Hardening
- Quota Project Troubleshooting
- Project Identity
- config.py
- ArgumentParser
- datetime
- test_phase04_llm_seam.py
- extract_meeting
- _lmstudio_settings
- CalendarSource
- Deliberately Mixed Sample Corpus
- Phase 2 Pure Core Implementation Plan
- ADR-016 Ephemeral compute, durable storage
- Tier 0 — local, no credentials
- sync-up session start (~11 min)
- ADR-004 Memgraph on GCE VM first, GKE later
- build_system_prompt
- ADR-006 Claim rows with SELECT FOR UPDATE SKIP LOCKED
- Phase 3 Data Layer Implementation Plan
- meeting-notes-gcp
- GmailSource
- test_phase05_connectors.py
- FetchedRecord
- runner.py
- MeetSource
- meet.py
- jira_client.py
- JiraSource
- Phase 5 — Connectors (DONE)
- FakeSession
- FixtureMiss
- sources/__init__.py

## God Nodes (most connected - your core abstractions)
1. `Settings` - 39 edges
2. `Status` - 36 edges
3. `chat_json()` - 29 edges
4. `FetchedRecord` - 28 edges
5. `CheckResult` - 22 edges
6. `RecordingRunner` - 20 edges
7. `run_checks()` - 19 edges
8. `sync_down()` - 19 edges
9. `Phase 0.5 auth spike implementation plan` - 19 edges
10. `FakeTx` - 18 edges

## Surprising Connections (you probably didn't know these)
- `probe_calendar()` --references--> `Phase 0.5 auth runbook`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `probe_gmail()` --references--> `Phase 0.5 auth runbook`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `probe_meet()` --conceptually_related_to--> `Meet transcripts via Workspace Events`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `probe_meet()` --references--> `Phase 0.5 auth runbook`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `save_token()` --references--> `Phase 0.5 auth runbook`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **One staging table gives one claiming query and one drain path** — docs_decisions_adr018, docs_decisions_staged_record_table, docs_decisions_adr006, docs_decisions_adr010, docs_decisions_per_source_adapter [EXTRACTED 1.00]
- **ADR-011's config rule enforced by two refactors and an AST check** — docs_decisions_adr011, docs_superpowers_plans_2026_08_20_phase_2_pure_core_scripts_env_exception [EXTRACTED 1.00]
- **Deferrals Recorded Rather Than Assumed** — docs_superpowers_plans_2026_08_20_phase_3_data_layer_scope_table [EXTRACTED 1.00]
- **Bugs Invisible to Review, Found by Running It** — docs_phase_plan_calendar_410_bug, docs_phase_plan_token_json_fallback_bug, docs_phase_plan_source_type_mypy_catch [EXTRACTED 1.00]
- **Shared Seams Instead of Four Near-Identical Connectors** — docs_superpowers_plans_2026_08_20_phase_5_watermark_ordering, docs_superpowers_plans_2026_08_20_phase_5_disabled_sources_noop, docs_phase_plan_transcript_source_not_a_port [EXTRACTED 1.00]
- **Sync session lifecycle: ephemeral tier up, work, backed-up teardown** — docs_setup_iap_tunnel [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks [EXTRACTED 1.00]
- **Keeping v5 Safe While Building v6** — docker_compose_local_port_shift, docker_compose_local_stack [EXTRACTED 1.00]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_decisions_adr005, docs_decisions_adr007, docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Ephemeral sync-up/sync-down lifecycle** — docs_decisions_adr016, docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]

## Communities (85 total, 21 thin omitted)

### Community 0 - "Doctor & Reproducibility Contract"
Cohesion: 0.06
Nodes (83): graphify maintenance discipline, Secret handling rules, No-secrets-in-output guarantee (spike), doctor exit code contract, Injected-probe check design, Leak-canary secret test, Phase 0.6 reproducibility implementation plan, doctor.py check contract (+75 more)

### Community 1 - "Durable Terraform Resources"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 2 - "Ephemeral Terraform Resources"
Cohesion: 0.09
Nodes (34): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+26 more)

### Community 3 - "meeting_quality.py"
Cohesion: 0.07
Nodes (35): composite_quality(), compute_quality(), _per_hour(), percentile_rank(), Any, Phase 31 — meeting quality scoring. The graph doesn't just remember meetings,…, Weighted mean over AVAILABLE (non-None) components, weights renormalized.…, Pure: turn one meeting's raw features into components + composite. ``features``… (+27 more)

### Community 4 - "meeting-notes-gcp v6"
Cohesion: 0.07
Nodes (34): Intent-to-skill map, Project context digest for agents, Absolute rules, Personal-then-Onix deployment context, Property graph schema, meeting-notes-gcp v6, Module boundaries, Person.tracked governance gate (+26 more)

### Community 5 - "Person Resolution"
Cohesion: 0.11
Nodes (30): Attendee, load_roster(), _name_sim(), _norm_name(), normalize_email(), Any, P3 entity resolution: resolve extracted attendees to canonical people. Two…, Resolve one attendee (anything with .name/.email/.role) to a canonical… (+22 more)

### Community 6 - "Pydantic Models & StagedRecord"
Cohesion: 0.08
Nodes (31): BaseModel, field_validator, ActionItem, Decision, ExtractedMeeting, Any, Pydantic models — extraction shapes and the single staging shape. Ported from…, One staged row from any source. `payload` is opaque here on purpose: a per-… (+23 more)

### Community 7 - "Access Control Policy"
Cohesion: 0.12
Nodes (35): AccessDenied, aggregates_only(), authorize(), load_policy(), parse_scope(), Principal, RuntimeError, Phase 33 (core) — principal → scope access policy. Design stance: hierarchy… (+27 more)

### Community 8 - "test_phase02_pure_core.py"
Cohesion: 0.06
Nodes (39): cosine(), extract_ticket_keys(), Return de-duplicated Jira ticket keys found in free text, order-preserving., Local models often wrap JSON responses in ```json ... ``` fences despite being…, strip_json_fences(), Phase 2 — the pure core. No I/O, no network, no database. Every test here runs…, Local models wrap JSON in ```json fences despite being told not to. Found by…, MIGRATION_FROM_V5.md §4 — Airbyte residue must not be ported. (+31 more)

### Community 9 - "test_phase05_auth_spike.py"
Cohesion: 0.13
Nodes (26): Request, exchange_code(), load_client_credentials(), probe_gmail(), Exchange an authorization code for tokens., Mint a fresh access token from a stored refresh token., Read the OAuth client id and secret, or explain exactly what's missing., refresh_access_token() (+18 more)

### Community 10 - "select_restore_pair"
Cohesion: 0.14
Nodes (14): Choose the export and snapshot to restore the ephemeral tier from. `sync_down`…, The shared timestamp in an export object path or a snapshot name., RestorePlan, select_restore_pair(), stamp_of(), The bug this exists to prevent. A sync-down that writes its export and then…, No matched pair must NOT mean discarding usable data — an export can outlive…, Nothing to restore is a legitimate, consistent state — not a mismatch. (+6 more)

### Community 11 - "RecordingRunner"
Cohesion: 0.12
Nodes (22): _ok(), CompletedProcess, `gcloud compute disks snapshot` operates on a zonal resource and 400s with…, `gcloud compute disks snapshot` exits 0 as soon as the snapshot is created,…, First ever run: no snapshots, no exports. Must still succeed. `gcloud storage…, End-to-end: the orphan export must not reach `gcloud sql import`., terraform reports the VM ready as soon as the API says RUNNING, which is well…, A VM that never finishes bootstrapping is a real problem, but the tier IS up… (+14 more)

### Community 12 - "ADR-018 One StagedRecord with a JSONB payload, not four typed raw tables"
Cohesion: 0.15
Nodes (16): Airbyte removed (§2.1), Decision Log (ADR index), ADR-001 Fresh repository, deliberate port, ADR-007 Build our own connectors, remove Airbyte, ADR-010 Collapse three pipeline paths into one, ADR-018 One StagedRecord with a JSONB payload, not four typed raw tables, AirbyteWebhookPayload deleted, not ported, JSONB payload is opaque to SQL (+8 more)

### Community 13 - "auth_spike.py"
Cohesion: 0.26
Nodes (14): Meet transcripts via Workspace Events, Meet: reachable vs transcripts-present, Namespace, _consent(), _error_of(), _probe(), probe_calendar(), probe_meet() (+6 more)

### Community 14 - "FakeTx"
Cohesion: 0.11
Nodes (22): ExtractedMeeting, MERGE a whole meeting into the graph in ONE transaction. Meeting, People,…, upsert_meeting_graph(), FakeDriver, FakeTx, _meeting(), Records every Cypher statement instead of running it., CLAUDE.md: one ACID transaction per meeting. Sequential separate driver calls… (+14 more)

### Community 15 - "Classifier Gate"
Cohesion: 0.11
Nodes (17): classify(), Any, Rules-based "is this worth processing" score. No LLM. Ported from v5…, Two or more noise markers return 0.0 immediately, before any positive signal is…, The gate is >= 2. One stray 'unsubscribe' in a genuine thread is not enough to…, CLASSIFIER_SCORE_THRESHOLD defaults to 0.40., Every signal is individually capped and the total is clamped. Without the clamp…, Signal 7: a record with real calendar times is more likely a meeting. (+9 more)

### Community 16 - "similarity"
Cohesion: 0.13
Nodes (17): best_match(), _norm(), Any, P5 dedup decision: is a new action item a duplicate of an existing open one?…, Return the best candidate above ``threshold`` (with its ``score``), or None., similarity(), Dedup must still work when embeddings are unavailable — the text path is the…, Identical text but orthogonal embeddings must score by the embedding —… (+9 more)

### Community 17 - "datetime"
Cohesion: 0.25
Nodes (11): datetime, export_object_name(), Compact UTC timestamp. Lowercase so it is legal in a GCE resource name, and…, GCS object path for a Cloud SQL export., GCE snapshot name for the Memgraph data disk. Must match…, snapshot_name(), _stamp(), GCE names must match [a-z]([-a-z0-9]*[a-z0-9])? and be <= 63 chars. (+3 more)

### Community 18 - "db.py"
Cohesion: 0.09
Nodes (32): apply_migrations(), claim_batch(), close_pool(), get_pool(), get_watermark(), _main(), mark_processed(), Any (+24 more)

### Community 19 - "Phase 0.5 auth spike implementation plan"
Cohesion: 0.24
Nodes (12): Coding conventions, Never pass event= to structlog, OAuth user type follows the project/account split, Migration to the Onix project, The 7-day refresh token problem, Bug 3: structlog reserved kwarg, Hand-rolled OAuth over httpx, Phase 0.5 auth spike implementation plan (+4 more)

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

### Community 24 - "ProbeResult"
Cohesion: 0.20
Nodes (12): ProbeResult, A refresh token plus the metadata needed to reason about its expiry., Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, render_report(), StoredToken, The single most important test in this file. docs/GOOGLE_AUTH.md §7., test_age_and_expiry_math(), test_report_distinguishes_reachable_from_transcripts_present() (+4 more)

### Community 25 - "LLM Config & Local Stack"
Cohesion: 0.38
Nodes (7): 768-dimensional embedding invariant, Environment variable surface, LLM configuration seam, Bug 4: literal 'null' strings from the LLM, Hash-keyed fixture replay, Four LLM backends behind one protocol, Reproducibility risks

### Community 26 - "graph_client.py"
Cohesion: 0.12
Nodes (27): AsyncDriver, close_driver(), get_action_confidence(), get_driver(), get_known_people(), get_open_actions_for_owner(), link_action_mentioned_in(), mark_action_needs_review() (+19 more)

### Community 27 - "sync.py"
Cohesion: 0.23
Nodes (16): Runner, build_parser(), main(), CompletedProcess, Default runner. Captures output so failures can be reported with context., Raise unless the command succeeded. Every destructive step in sync_down is…, Back up, verify the backup, then destroy the ephemeral tier. Ordering is a…, Block until the Memgraph stack is actually serving, or give up. Terraform… (+8 more)

### Community 28 - "Loopback Callback Server"
Cohesion: 0.24
Nodes (12): Ephemeral-port loopback callback server, HTTPServer, CallbackServer, An HTTPServer that captures a single OAuth callback., Bind an ephemeral loopback port and return the server and its redirect URI., Block until the callback arrives, then validate it and return the code., start_callback_server(), wait_for_code() (+4 more)

### Community 29 - "SyncError"
Cohesion: 0.19
Nodes (13): RuntimeError, A sync step failed. Raised rather than returned so no caller can accidentally…, SyncError, _fail(), The single most important test in this file. A failed export followed by a…, gcloud sql export can exit 0 having written nothing usable. Verify the object,…, Only the specific 'matched no objects' message is tolerated. Any other storage…, The console is not readable in the first seconds after boot. A failed read is… (+5 more)

### Community 30 - "test_phase03_data_layer.py"
Cohesion: 0.10
Nodes (29): integration, build_dsn(), Plain-Postgres DSN. Only used when the Cloud SQL connector is not., _local_settings(), _norm(), Phase 3 — the data layer. Runs with no Postgres and no Memgraph. The claiming…, Point at the local compose Postgres regardless of the developer's .env., The ADR-006 guarantee, proven against a real Postgres. SKIP LOCKED is server-… (+21 more)

### Community 31 - "get_access_token"
Cohesion: 0.06
Nodes (46): main(), get_access_token(), load_refresh_token(), _post_token(), Path, Settings, Transport, with_retry (+38 more)

### Community 32 - "Callback Request Handler"
Cohesion: 0.29
Nodes (4): BaseHTTPRequestHandler, _CallbackHandler, CallbackResult, Silence the default stderr access log.          It would echo the query string,

### Community 33 - "build_auth_url"
Cohesion: 0.19
Nodes (13): Loopback redirect and prompt=consent, Phase 0.5 auth runbook, The four minimal OAuth scopes, PKCE S256 authorization-code flow, build_auth_url(), pkce_pair(), Return a (code_verifier, code_challenge) pair using S256., Build the Google consent URL.      access_type=offline and prompt=consent are bo (+5 more)

### Community 35 - "test_phase01_sync.py"
Cohesion: 0.23
Nodes (11): backup_uri(), Name of the most recent item, or None if there are none. None is a legitimate…, select_latest(), Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016. Every test runs with…, The first-ever sync-up has no snapshot and no export. Not an error., A missing timestamp means gcloud changed its output shape. Fail loudly rather…, test_backup_uri_builds_a_gs_url(), test_select_latest_picks_the_most_recent() (+3 more)

### Community 36 - "Auth Risks & Onix Split"
Cohesion: 0.17
Nodes (12): Every schema statement, in application order. Returned rather than executed so…, statements(), CLAUDE.md's schema: every node has a unique id. A label with no constraint…, ADR-008: provenance cannot be backfilled. A merge that happens before the…, CLAUDE.md: 768 in both backends because the indexes are built for 768.…, If someone migrates the indexes, the setting is the single knob., Memgraph takes one statement per run(); a semicolon-joined blob fails., test_both_vector_indexes_use_the_configured_dimension() (+4 more)

### Community 39 - "Backup Verified Before Destroy"
Cohesion: 0.67
Nodes (3): Export/snapshot verification before destroy, sync_down(), SyncError exception

### Community 49 - "Settings"
Cohesion: 0.10
Nodes (37): BaseSettings, Settings, chat_json(), _default_transport(), embed(), _fake_chat_json(), _fake_vector(), fixture_dir() (+29 more)

### Community 53 - "config.py"
Cohesion: 0.11
Nodes (22): ArgumentParser, get_settings(), Typed settings — the ONLY module in this package that reads os.environ. Every…, Process-wide settings. Cached so the .env file is read once. Tests should…, LLM extraction — v5's tuned prompt, v6's swappable client. The system prompt…, Tuned prompt text. Data, not logic. The extraction prompt is carried over from…, build_parser(), fetch_one() (+14 more)

### Community 59 - "test_phase04_llm_seam.py"
Cohesion: 0.07
Nodes (40): _is_null_like(), Any, True for None/empty AND for a model that emits the literal string "null"…, Fill required fields the model left null-like, in place. Carried from v5…, repair(), fixture_key(), _loads_lenient(), Stable, filename-safe key for a prompt. Covers the system prompt so editing it… (+32 more)

### Community 60 - "extract_meeting"
Cohesion: 0.15
Nodes (22): extract_meeting(), Extract one meeting. Returns None if the model output cannot be used. Retry…, _fake_settings(), Path, Semantic-search tests need vectors that are stable across runs yet still…, The indexes use cosine similarity; unit vectors keep scores comparable., The exit criterion, on the fake backend: a recorded response in, a validated…, The invariant this whole mechanism rests on. CLAUDE.md calls writer/reader id… (+14 more)

### Community 61 - "_lmstudio_settings"
Cohesion: 0.13
Nodes (15): _lmstudio_settings(), A timeout or 5xx is transient — retry it., At temperature 0 an identical retry yields identical output, so retrying a…, CLAUDE.md: temperature is 0.0 for extraction. Always., A short vector would fail at Memgraph insert time, far from the call that…, The pipeline marks the record processed and moves on; it must not crash the…, Unrepairable output is still not a crash., test_a_correct_length_embedding_passes_through() (+7 more)

### Community 62 - "CalendarSource"
Cohesion: 0.08
Nodes (23): CalendarSource, _default_transport(), event_time(), Any, Transport, with_retry, Google Calendar connector — new code; Airbyte did this in v5. Incremental by…, Returns the status rather than raising, so fetch() can act on a 410. (+15 more)

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

### Community 73 - "GmailSource"
Cohesion: 0.10
Nodes (21): _collect_parts(), _decode(), _default_transport(), GmailSource, header(), Any, Transport, with_retry (+13 more)

### Community 74 - "test_phase05_connectors.py"
Cohesion: 0.15
Nodes (22): adf_to_text(), Flatten an Atlassian Document Format node to plain text. Carried from v5…, extract_body(), The message body as text, preferring text/plain over text/html., _b64(), _gmail_transport(), Phase 5 — the connectors. No live credentials, no network, no database. Every…, Real Gmail nests: multipart/mixed > multipart/alternative > text/plain. A… (+14 more)

### Community 75 - "FetchedRecord"
Cohesion: 0.16
Nodes (18): FetchedRecord, One raw record, ready to stage. `watermark` is the source's own ordering value…, Fetch, stage everything, then advance the watermark. **The ordering is a…, stage_all(), StageFn, FakeSource, No records means nothing new; moving the watermark would be a lie., Stands in for db.stage_record + db.set_watermark. (+10 more)

### Community 76 - "runner.py"
Cohesion: 0.13
Nodes (15): The `Source` protocol and the one staging loop every connector shares. v5 had a…, Fetch what changed since `since`. Capture only — never interpret., Source, StageResult, build_google_source(), Any, Settings, One ingestion run, wired end to end. This exists so `jobs/*` stay thin.… (+7 more)

### Community 77 - "MeetSource"
Cohesion: 0.14
Nodes (12): MeetSource, Transport, with_retry, Pull pending transcript events. `since` is unused — Pub/Sub itself is the…, Ack the messages from the last fetch. Called by the job AFTER staging succeeds.…, .env.example promises transcript ingestion disables cleanly., Acking inside fetch would lose a transcript permanently on a staging failure:…, test_a_malformed_event_is_still_acked_so_it_cannot_block_forever() (+4 more)

### Community 78 - "meet.py"
Cohesion: 0.15
Nodes (15): decode_event(), _default_transport(), entries_to_text(), Any, Google Meet transcripts — ported from v5's `meet_ingest.py`. The one connector…, Decode one Pub/Sub message into transcript coordinates. The fileGenerated event…, Speaker-tagged plain text, which is what the extractor expects., _pubsub_message() (+7 more)

### Community 79 - "jira_client.py"
Cohesion: 0.36
Nodes (12): add_comment(), _default_transport(), get_issue(), jira_base_url(), jira_headers(), Any, Settings, Transport (+4 more)

### Community 80 - "JiraSource"
Cohesion: 0.19
Nodes (9): JiraSource, Settings, Transport, Jira connector — new code over a ported client. Incremental by JQL `updated >=…, Settings, Tiers 0 and 1 must run the whole pipeline with no Jira account., test_an_issue_stages_with_its_key_as_the_dedup_id(), test_disabled_jira_stages_nothing_and_does_not_raise() (+1 more)

### Community 81 - "Phase 5 — Connectors (DONE)"
Cohesion: 0.31
Nodes (9): Calendar 410 Gone — Permanent Breakage After First Success, Phase 5 — Connectors (DONE), mypy Caught a Source-Type Mismatch Before It Ran, No Path From Auth Spike to Connectors, TranscriptSource Shares a Name, Not a Concept, Verified Against Local Postgres, Not Cloud SQL, Phase 5 Connectors Implementation Plan, Disabled Sources Are No-Ops, Not Errors (+1 more)

### Community 83 - "FixtureMiss"
Cohesion: 0.67
Nodes (3): FixtureMiss, No recorded fixture for this prompt. Deliberately fatal (ADR-014). Falling back…, RuntimeError

## Knowledge Gaps
- **45 isolated node(s):** `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image`, `var.memgraph_machine`, `var.memgraph_restore_snapshot` (+40 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `meeting-notes-gcp v6` connect `meeting-notes-gcp v6` to `Tier 0 — local, no credentials`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `The 7-day refresh token problem` connect `Phase 0.5 auth spike implementation plan` to `Doctor & Reproducibility Contract`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `OAuth user type follows the project/account split` connect `Phase 0.5 auth spike implementation plan` to `meeting-notes-gcp v6`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Settings` (e.g. with `extract_meeting()` and `get_driver()`) actually correct?**
  _`Settings` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `Status` (e.g. with `doctor.py check contract` and `test_blank_secret_counts_as_unset()`) actually correct?**
  _`Status` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `FetchedRecord` (e.g. with `CalendarSource` and `GmailSource`) actually correct?**
  _`FetchedRecord` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image` to the rest of the system?**
  _45 weakly-connected nodes found - possible documentation gaps or missing edges._