# Graph Report - meeting-notes-gcp  (2026-08-20)

## Corpus Check
- 56 files · ~140,206 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2411 nodes · 4903 edges · 201 communities (117 shown, 84 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 207 edges (avg confidence: 0.92)
- Token cost: 176,995 input · 0 output

## Community Hubs (Navigation)
- Reproducibility & Doctor Preflight
- Dev Agent Guardrail Gates
- Graph Intelligence & Person Memory
- Pure Core Tests
- Terraform Durable Tier
- LLM Fixture Replay
- Dev Agent Backend Routing
- Graph Client Reads
- GitHub PR Client
- Postgres Data Layer
- Person Resolution & Graph Upsert
- LLM Seam & Settings
- Terraform Ephemeral Tier
- Google OAuth Token Exchange
- Calendar Adapter
- Jira Client & Pipeline Tests
- Jira & Meet Connectors
- Dev Agent Architecture Rules
- FastAPI App & Dependencies
- Calendar Source
- Data Layer Tests
- Semantic Memory
- Meet Transcript Source
- Fake Graph Driver
- Dev Agent Lifecycle
- Jira Status Sync
- Gmail Source
- Pipeline Drain Tests
- API Route Tests
- Jira Pusher & Action Items
- Job Entrypoints
- Source Staging Protocol
- Auth Spike Tests
- Sync Restore Planning
- Shared Utilities
- Auth Spike Runbook
- OAuth Code Exchange
- Ingestion Connectors
- Access Control
- Jira REST Client
- Webhook Route Tests
- Sync Lifecycle Tests
- Pydantic Domain Models
- Architecture Overview
- Meeting Quality Scoring
- Procedural Memory
- Vector Memory
- Graph API Router
- Dev Agent Session Memory
- MAGE Graph Algorithms
- Episodic Memory
- Cloud Run Job Runners
- Sync Orchestration Script
- Dashboard Loaders
- Git Worktree Operations
- Source Adapter Protocol
- Gemini Runner Tests
- Module Boundary Rules
- Token Health & Refresh
- Memory API Router
- Webhook Handlers
- Deployment & Portability ADRs
- LLM Extraction
- Lifecycle Transition Tests
- Webhook HMAC Verification
- Lenient JSON Parsing
- Memory Retrieval
- LLM Retry & Temperature Tests
- Graph Intelligence Phase Notes
- LLM Seam Design Rules
- Pipeline & Migration Bugs
- Phase 2 Plan
- Sync Command Runner
- Fixture Recording
- OAuth Callback Server
- Migration Runner
- Env & Token Loading
- Governance Scope Tests
- Graph Schema & Provenance
- Dev Agent Self-Verify
- Jira Source
- Sync Safety Guarantees
- Postgres Integration Tests
- Weekly Digest
- Embedding Dimension Guards
- Person Name Disambiguation
- Enrichment Failure Tolerance
- Insights API Router
- Phase 8 API & Dashboard
- Tiered Runbook & Troubleshooting
- Action Item Dedup
- JSON Array Salvage
- Fake Result Driver
- Review Queue Router
- OAuth Callback Handler
- OAuth Scopes & PKCE
- Memgraph Readiness Polling
- Meeting Type Router
- Email Normalisation
- Fake Session Driver
- Community Naming Tests
- V5 Port Map & Bugs
- Stored Token Model
- LLM Backend Contracts
- API Test Fixtures
- Classifier
- Algorithm Cadence Rules
- Durable Tier Resources
- OAuth Project Migration
- Sync Down Verification
- Phase 5 Connectors Plan
- Graph Algorithm Retry Rules
- Real ASGI Route Tests
- Local Stack Ports
- Airbyte Removal
- Rejected Storage Alternatives
- Ephemeral Tier Resources
- Billing & Live Validation Tasks
- Phase 3 Plan
- Phase 4 Plan & Corpus
- Dev Agent Package Init
- Package Init
- Memory Package Init
- Sources Package Init
- Terraform Bootstrap Script
- VM Startup Script
- UUID5 Id Parity
- JSON Fence Stripping
- Priority From Due Date
- StagedRecord Payload
- StagedRecord Source Validation
- Raw Model Parsing
- Source Type Discriminator
- Airbyte Webhook Removal
- Confidence Defaults
- Marketing Noise Gate
- Classifier Score Cap
- Calendar Metadata Signal
- Attendee Signal
- Email Source Routing
- Type-Specific Prompts
- Router vs Meeting Vocabularies
- Cosine Length Mismatch
- Embedding Precedence
- Best Match Scoring
- Scope Predicate Injection
- Policy Path Loading
- Agenda Detection
- Composite Score Gaps
- Insufficient Data Scoring
- Cloud SQL Connection Mode
- Provenance Ships In V1
- Vector Index Dimension
- Vector Dimension Settings
- Nightly Score Coverage
- MAGE Call Boundary
- Deterministic Fact Ids
- Pipeline Retrieval Boundary
- Degraded Health Reporting
- Cartesian Product Regression
- Preflight Failure Reporting
- Scheduler Replacement
- Exactly-Once Semantics
- Cost Posture
- Rejected Ingestion Options
- GKE Deferral
- Known Risks
- LM Studio As Backend
- Fresh Repo Decision
- Leiden Over-Fragmentation
- Structlog Reserved Kwarg
- Porting Order
- Phase 9 Hardening
- Consent Troubleshooting
- Terraform Troubleshooting
- Compose File Unignoring
- Sync Script Entry
- Standalone os.environ Exception
- Phase 6 Plan
- Settings Reference A
- Settings Reference B
- Settings Reference C
- Transport Reference A
- Settings Reference D
- Project Root Node
- Roster Model
- Argument Parser A
- Datetime Reference A
- Argument Parser B
- Datetime Reference B
- StagedRecord Reference
- Settings Reference E
- Transport Reference B
- Retry Decorator Reference

## God Nodes (most connected - your core abstractions)
1. `Settings` - 119 edges
2. `get_settings()` - 67 edges
3. `get_driver()` - 57 edges
4. `FakeSession` - 40 edges
5. `FakeDriver` - 37 edges
6. `Status` - 36 edges
7. `_get()` - 35 edges
8. `chat_json()` - 31 edges
9. `process_ticket()` - 30 edges
10. `FetchedRecord` - 28 edges

## Surprising Connections (you probably didn't know these)
- `probe_meet()` --conceptually_related_to--> `Meet transcripts via Workspace Events`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `render_report()` --conceptually_related_to--> `Secret handling rules`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `start_callback_server()` --implements--> `Loopback redirect and prompt=consent`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `CheckResult` --implements--> `doctor.py check contract`  [INFERRED]
  scripts/doctor.py → docs/superpowers/specs/2026-08-13-clone-and-run-design.md
- `Status` --implements--> `doctor.py check contract`  [INFERRED]
  scripts/doctor.py → docs/superpowers/specs/2026-08-13-clone-and-run-design.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **The SHIPPED fix, tested at three independent levels** — docs_superpowers_plans_2026_08_20_phase_11_dev_agent_terminal_states, docs_superpowers_plans_2026_08_20_phase_11_dev_agent_active_run_excluded_states, docs_superpowers_plans_2026_08_20_phase_11_dev_agent_should_attempt_second_check, docs_decisions_shipped_resume_loop_bug [EXTRACTED 1.00]
- **dev_agent's three structural departures from a literal v5 port** — claude_no_apscheduler_rule, claude_db_only_sql_owner, claude_dev_agent_backend_separate_seam, docs_decisions_adr_020_dev_agent_moves_from_v2_to_v1 [EXTRACTED 1.00]
- **Tests that passed while the behaviour they guarded was broken** — docs_decisions_mock_certified_the_bug, docs_phase_plan_route_enumeration_vacuous_test, docs_superpowers_plans_2026_08_20_phase_11_dev_agent_planted_violation_testing, docs_superpowers_plans_2026_08_20_phase_8_api_dashboard_asgi_transport_route_tests [INFERRED 0.85]
- **ADR-011's config rule enforced by two refactors and an AST check** — docs_superpowers_plans_2026_08_20_phase_2_pure_core_scripts_env_exception [EXTRACTED 1.00]
- **Deferrals Recorded Rather Than Assumed** — docs_superpowers_plans_2026_08_20_phase_3_data_layer_scope_table [EXTRACTED 1.00]
- **Shared Seams Instead of Four Near-Identical Connectors** — docs_superpowers_plans_2026_08_20_phase_5_watermark_ordering, docs_superpowers_plans_2026_08_20_phase_5_disabled_sources_noop [EXTRACTED 1.00]
- **Sync session lifecycle: ephemeral tier up, work, backed-up teardown** — docs_setup_iap_tunnel [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks [EXTRACTED 1.00]
- **Keeping v5 Safe While Building v6** — docker_compose_local_port_shift, docker_compose_local_stack [EXTRACTED 1.00]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Ephemeral sync-up/sync-down lifecycle** — docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]

## Communities (201 total, 84 thin omitted)

### Community 0 - "Reproducibility & Doctor Preflight"
Cohesion: 0.06
Nodes (84): Repo maintained under graphify (commit report + graph.json, never cache/), Secret handling rules, Standing exit criterion for Phases 1-9, No-secrets-in-output guarantee (spike), doctor exit code contract, Injected-probe check design, Leak-canary secret test, Phase 0.6 reproducibility implementation plan (+76 more)

### Community 1 - "Dev Agent Guardrail Gates"
Cohesion: 0.04
Nodes (73): CommandRunner, all_passed(), failed_gates(), gate_diff_budget(), gate_lint_type_clean(), gate_module_boundaries(), gate_no_new_deps(), gate_protected_paths() (+65 more)

### Community 2 - "Graph Intelligence & Person Memory"
Cohesion: 0.06
Nodes (66): person_memory_profile(), Everything the graph remembers about one person. No LLM call. Returns {} when…, Semantic search over Meeting summaries., search_similar_meetings(), FakeDriver, FakeSession, _meeting(), ExtractedMeeting (+58 more)

### Community 3 - "Pure Core Tests"
Cohesion: 0.03
Nodes (42): Phase 2 — the pure core. No I/O, no network, no database. Every test here runs…, The whole MERGE-not-CREATE strategy rests on this. Same input, same id, forever…, v5's actual boundaries: <= 14 days high, <= 60 medium, beyond that low., LLM output sometimes gives decisions as bare strings. v5's coercion is load-…, CLAUDE.md mandates extra='ignore' — an LLM adding a field must not fail the…, The gate is >= 2. One stray 'unsubscribe' in a genuine thread is not enough to…, CLASSIFIER_SCORE_THRESHOLD defaults to 0.40., Order matters: 'session' lives in review's keywords and would otherwise swallow… (+34 more)

### Community 4 - "Terraform Durable Tier"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 5 - "LLM Fixture Replay"
Cohesion: 0.06
Nodes (48): fixture_key(), FixtureMiss, RuntimeError, No recorded fixture for this prompt. Deliberately fatal (ADR-014). Falling back…, Stable, filename-safe key for a prompt. Covers the system prompt so editing it…, _fake_settings(), Path, Phase 4 — the LLM seam. Runs with no network, no API key, no LM Studio. Every… (+40 more)

### Community 6 - "Dev Agent Backend Routing"
Cohesion: 0.05
Nodes (51): ensure_cli_home(), model_for_run(), preflight(), preflight_gemini(), PreflightError, RuntimeError, Backend routing and preflight for the dev agent's headless coding runner.…, Verify the Gemini backend has a project and model configured. Does not make a… (+43 more)

### Community 7 - "Graph Client Reads"
Cohesion: 0.09
Nodes (46): AsyncDriver, get_action_confidence(), get_actions_needing_review(), get_all_communities(), get_bridge_nodes(), get_community_members(), get_driver(), get_influential_nodes() (+38 more)

### Community 8 - "GitHub PR Client"
Cohesion: 0.08
Nodes (41): Run the coding agent to completion on a real task, in `work_dir`. ``--approval-…, run_agent(), find_open_pr(), get_pr_diff(), _github_headers(), Any, with_retry, GitHub API client — read-only PR verification. The dev agent never opens a PR… (+33 more)

### Community 9 - "Postgres Data Layer"
Cohesion: 0.09
Nodes (43): apply_migrations(), claim_batch(), claim_dev_agent_run(), finish_dev_agent_run(), get_active_dev_agent_run(), get_dev_agent_run(), get_dev_agent_session_memory(), get_pool() (+35 more)

### Community 10 - "Person Resolution & Graph Upsert"
Cohesion: 0.08
Nodes (39): get_known_people(), ExtractedMeeting, with_retry, MERGE a whole meeting into the graph in ONE transaction. Meeting, People,…, Existing Person nodes, for probabilistic resolution (email, name, tracked)., Canonical email for an action item's owner, or None. This is the fix for bug…, _resolve_owner_email(), upsert_meeting_graph() (+31 more)

### Community 11 - "LLM Seam & Settings"
Cohesion: 0.10
Nodes (40): BaseSettings, Settings, chat_json(), chat_list(), _default_transport(), _fake_chat_json(), fixture_dir(), _gemini_chat_request() (+32 more)

### Community 12 - "Terraform Ephemeral Tier"
Cohesion: 0.09
Nodes (34): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+26 more)

### Community 13 - "Google OAuth Token Exchange"
Cohesion: 0.09
Nodes (34): get_access_token(), load_refresh_token(), _post_token(), Path, Settings, Transport, with_retry, Google OAuth for the connectors: refresh token in, access token out.… (+26 more)

### Community 14 - "Calendar Adapter"
Cohesion: 0.10
Nodes (13): CalendarAdapter, EmailAdapter, MeetAdapter, Any, Nothing. A mail header date is when the MESSAGE was sent, which is often not…, `start` is ground truth for a calendar event., A conference record's start_time is ground truth., A real transcript is strong signal on its own. Only the title-only fallback (no… (+5 more)

### Community 15 - "Jira Client & Pipeline Tests"
Cohesion: 0.12
Nodes (34): active_sprint_id(), create_issue(), The current active sprint on the configured board, or None. Not retried: a…, Create one Jira issue. Returns its key. Non-engineering items (meeting follow-…, _jira_settings(), _meeting(), ExtractedMeeting, Phase 6 — the pipeline. No live services; every dependency is injected. The… (+26 more)

### Community 16 - "Jira & Meet Connectors"
Cohesion: 0.10
Nodes (31): adf_to_text(), Flatten an Atlassian Document Format node to plain text. Carried from v5…, extract_body(), The message body as text, preferring text/plain over text/html., Jira connector — new code over a ported client. Incremental by JQL `updated >=…, decode_event(), Decode one Pub/Sub message into transcript coordinates. The fileGenerated event…, _b64() (+23 more)

### Community 17 - "Dev Agent Architecture Rules"
Cohesion: 0.09
Nodes (31): dev_agent subpackage (autonomous ticket implementer), dev_agent/backend.py owns coding-model routing, deliberately outside llm_client, jobs/ and api/ hold entrypoints only; logic lives in meeting_notes/, No in-process scheduler; Cloud Scheduler triggers Cloud Run Jobs, dev_agent never merges its own PR; CLOSED comes from a human merge, SHIPPED is terminal and 'terminal' has exactly one definition, ADR-005 Replace APScheduler with Cloud Scheduler + Cloud Run Jobs, ADR-020 dev_agent moves from v2 to v1, ported now (+23 more)

### Community 18 - "FastAPI App & Dependencies"
Cohesion: 0.13
Nodes (23): principal(), Shared dependencies for the API layer. Auth reuses `access_control` from Phase…, Resolve the caller from a bearer token, or 401/403., settings_dep(), create_app(), lifespan(), FastAPI service — Cloud Run, scales to zero. Entrypoint only: every route is a…, preflight() (+15 more)

### Community 19 - "Calendar Source"
Cohesion: 0.08
Nodes (23): CalendarSource, _default_transport(), event_time(), Any, Transport, with_retry, Google Calendar connector — new code; Airbyte did this in v5. Incremental by…, Returns the status rather than raising, so fetch() can act on a 410. (+15 more)

### Community 20 - "Data Layer Tests"
Cohesion: 0.10
Nodes (27): _norm(), Phase 3 — the data layer. Runs with no Postgres and no Memgraph. The claiming…, ADR-015: a blank CLOUD_SQL_CONNECTION_NAME means local Postgres., ADR-006. Without SKIP LOCKED two overlapping Cloud Run Jobs either block each…, Unordered claiming lets a steadily-arriving source keep jumping the queue and…, CLAUDE.md's schema: every node has a unique id. A label with no constraint…, Memgraph takes one statement per run(); a semicolon-joined blob fails., ADR-018: one table with a JSONB payload. (+19 more)

### Community 21 - "Semantic Memory"
Cohesion: 0.13
Nodes (26): _chat(), consolidate(), consolidate_preferences(), _driver(), extract_facts(), infer_preferences(), normalise_topic(), _parse_list() (+18 more)

### Community 22 - "Meet Transcript Source"
Cohesion: 0.10
Nodes (19): _default_transport(), entries_to_text(), MeetSource, Any, Transport, with_retry, Google Meet transcripts — ported from v5's `meet_ingest.py`. The one connector…, Pull pending transcript events. `since` is unused — Pub/Sub itself is the… (+11 more)

### Community 23 - "Fake Graph Driver"
Cohesion: 0.12
Nodes (18): FakeDriver, FakeTx, _meeting(), Records every Cypher statement instead of running it., CLAUDE.md: one ACID transaction per meeting. Sequential separate driver calls…, CLAUDE.md: DO NOT use CREATE for unique nodes — always MERGE., CLAUDE.md: the Topic MERGE key is lowercased and stripped. Raw case fragmented…, Regression test for MIGRATION_FROM_V5.md bug #1. v5 bound `owner_email =… (+10 more)

### Community 24 - "Dev Agent Lifecycle"
Cohesion: 0.09
Nodes (24): assert_transition(), IllegalTransition, is_terminal(), pull_request_node_id(), RuntimeError, Dev-agent run lifecycle: states, the legal-transition table, deterministic IDs.…, Raised when a run is asked to move between two states with no legal edge., Raise :class:`IllegalTransition` unless the edge is legal. (+16 more)

### Community 25 - "Jira Status Sync"
Cohesion: 0.10
Nodes (13): Jira status syncing back into the graph. Returns whether a node matched.…, update_action_jira_status(), _default_update_status(), Jira status -> graph. The reverse direction from jira_pusher. Ported from v5's…, _FakeDriver, _FakeResult, _FakeSession, Without exclude_id, an item can match itself at similarity 1.0 — by the time… (+5 more)

### Community 26 - "Gmail Source"
Cohesion: 0.10
Nodes (21): _collect_parts(), _decode(), _default_transport(), GmailSource, header(), Any, Transport, with_retry (+13 more)

### Community 27 - "Pipeline Drain Tests"
Cohesion: 0.11
Nodes (19): _email_payload(), _fake_settings(), StagedRecord, Stands in for graph_client.upsert_meeting_graph., Async stand-in for db.mark_processed., The cheap gate stays cheap: no LLM call for obvious noise., Temperature 0: an identical retry yields identical output, so a parse failure…, The tests above check extract_overrides() in isolation, which passes even if… (+11 more)

### Community 28 - "API Route Tests"
Cohesion: 0.08
Nodes (24): Phase 8 — the API. Every route is driven through the real ASGI app.…, The governance promise itself, against the real function with a fake driver --…, CLAUDE.md: scheduling is Cloud Scheduler triggering Cloud Run Jobs. v5's…, `event=` collides with structlog's reserved message field and raises TypeError…, CLAUDE.md: keep it single-file, no build step. No bundler, no CDN., Reorganised during the UX audit around what a user actually asks: what happened…, PersonReview and MemorySession are records of how the system worked, not things…, Most connected Person (0)" with a bare "Nothing here yet" reads as broken, when… (+16 more)

### Community 29 - "Jira Pusher & Action Items"
Cohesion: 0.12
Nodes (21): ActionItem, link_action_mentioned_in(), mark_action_needs_review(), Recurring mention of an existing item — link it rather than duplicating., Below JIRA_CONFIDENCE_THRESHOLD: write the node, create no ticket., update_action_jira_key(), _default_active_sprint_id(), _default_add_comment() (+13 more)

### Community 30 - "Job Entrypoints"
Cohesion: 0.12
Nodes (21): main(), Any, Sync one staged Jira issue's status into the graph. Returns whether an…, sync_one(), adapter_for(), _default_process(), _default_sync_jira(), drain_batch() (+13 more)

### Community 31 - "Source Staging Protocol"
Cohesion: 0.16
Nodes (18): FetchedRecord, One raw record, ready to stage. `watermark` is the source's own ordering value…, Fetch, stage everything, then advance the watermark. **The ordering is a…, stage_all(), StageFn, FakeSource, No records means nothing new; moving the watermark would be a lie., Stands in for db.stage_record + db.set_watermark. (+10 more)

### Community 32 - "Auth Spike Tests"
Cohesion: 0.15
Nodes (22): load_client_credentials(), pkce_pair(), Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, Read the OAuth client id and secret, or explain exactly what's missing., Return a (code_verifier, code_challenge) pair using S256., render_report(), Phase 0.5 — the auth spike.  Everything here runs with no live GCP, no Google cr, The single most important test in this file. docs/GOOGLE_AUTH.md §7. (+14 more)

### Community 33 - "Sync Restore Planning"
Cohesion: 0.12
Nodes (22): backup_uri(), Choose the export and snapshot to restore the ephemeral tier from. `sync_down`…, Name of the most recent item, or None if there are none. None is a legitimate…, RestorePlan, select_latest(), select_restore_pair(), Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016. Every test runs with…, The bug this exists to prevent. A sync-down that writes its export and then… (+14 more)

### Community 34 - "Shared Utilities"
Cohesion: 0.10
Nodes (20): BoundLogger, date, F, configure_logging(), extract_ticket_keys(), priority_from_due(), Shared helpers with no I/O: deterministic ids, retries, logging, parsing.…, Map a due date to a Jira priority. No due date is 'low', not 'medium'. (+12 more)

### Community 35 - "Auth Spike Runbook"
Cohesion: 0.24
Nodes (21): Meet transcripts via Workspace Events, Phase 0.5 auth runbook, Meet: reachable vs transcripts-present, Phase 0.5 auth spike implementation plan, Namespace, build_parser(), _consent(), main() (+13 more)

### Community 36 - "OAuth Code Exchange"
Cohesion: 0.11
Nodes (22): Hand-rolled OAuth over httpx, _error_of(), exchange_code(), Response, Pull Google's error string out of a response body.      Only the error/message f, Exchange an authorization code for tokens., Mint a fresh access token from a stored refresh token., refresh_access_token() (+14 more)

### Community 37 - "Ingestion Connectors"
Cohesion: 0.13
Nodes (15): The `Source` protocol and the one staging loop every connector shares. v5 had a…, Fetch what changed since `since`. Capture only — never interpret., Source, StageResult, build_google_source(), Any, Settings, One ingestion run, wired end to end. This exists so `jobs/*` stay thin.… (+7 more)

### Community 38 - "Access Control"
Cohesion: 0.17
Nodes (20): AccessDenied, aggregates_only(), authorize(), load_policy(), parse_scope(), Principal, RuntimeError, Phase 33 (core) — principal → scope access policy. Design stance: hierarchy… (+12 more)

### Community 39 - "Jira REST Client"
Cohesion: 0.20
Nodes (20): add_comment(), _default_transport(), get_issue(), get_issue_detail(), jira_base_url(), jira_headers(), list_active_sprint_tickets(), move_to_sprint() (+12 more)

### Community 40 - "Webhook Route Tests"
Cohesion: 0.13
Nodes (22): Response, _github_post(), _post(), Any, The endpoint must reach graph_client with label=Person, which is what triggers…, Also proves the route's own structlog call runs -- the exact thing v5 never…, ADR-020: this is the ONE place dev_agent's CLOSED state is written., Most merged PRs aren't the agent's, and a graph hiccup on the ones that are… (+14 more)

### Community 41 - "Sync Lifecycle Tests"
Cohesion: 0.13
Nodes (19): _ok(), CompletedProcess, `gcloud compute disks snapshot` operates on a zonal resource and 400s with…, `gcloud compute disks snapshot` exits 0 as soon as the snapshot is created,…, First ever run: no snapshots, no exports. Must still succeed. `gcloud storage…, End-to-end: the orphan export must not reach `gcloud sql import`., A VM that never finishes bootstrapping is a real problem, but the tier IS up…, sync-up must not announce the tier is serving before it is. (+11 more)

### Community 42 - "Pydantic Domain Models"
Cohesion: 0.13
Nodes (17): BaseModel, field_validator, Any, ActionItem, Attendee, Decision, ExtractedMeeting, Any (+9 more)

### Community 43 - "Architecture Overview"
Cohesion: 0.12
Nodes (20): db.py is the only module holding SQL, meeting-notes-gcp (v6), Target Architecture (sources -> Cloud Run Jobs -> Cloud SQL -> pipeline_drain -> Memgraph -> API), ADR-007 Build our own connectors; remove Airbyte, ADR-013 Three-tier reproducibility contract, OAuth console step permanently manual, ADR-015 db.py selects its connection mode on configuration, Calendar 410 Gone on updatedMin, falls back to a full sync, Phase 0.6 - Reproducibility skeleton (+12 more)

### Community 44 - "Meeting Quality Scoring"
Cohesion: 0.15
Nodes (19): composite_quality(), compute_quality(), _per_hour(), percentile_rank(), Any, Phase 31 — meeting quality scoring. The graph doesn't just remember meetings,…, Weighted mean over AVAILABLE (non-None) components, weights renormalized.…, Pure: turn one meeting's raw features into components + composite. ``features``… (+11 more)

### Community 45 - "Procedural Memory"
Cohesion: 0.15
Nodes (18): discover_procedures(), _driver(), match_to_procedure(), matches_pattern(), Any, ExtractedMeeting, Procedural memory — recognising the recurring shapes of meetings. Owns…, Nightly: promote frequently co-occurring meeting shapes to Procedures. Uses… (+10 more)

### Community 46 - "Vector Memory"
Cohesion: 0.19
Nodes (19): _driver(), embed_action_items_for_meeting(), embed_facts_for_meeting(), embed_meeting(), _embed_pending(), embed_text(), Any, Vector memory — 768-dim semantic search over Meeting, Fact and ActionItem. Owns… (+11 more)

### Community 47 - "Graph API Router"
Cohesion: 0.26
Nodes (18): actions_open(), decisions(), digest_weekly(), meeting_detail(), meeting_provenance(), meetings_recent(), person(), Any (+10 more)

### Community 48 - "Dev Agent Session Memory"
Cohesion: 0.12
Nodes (18): build_memory(), files_from_diff(), load_resume_context(), Any, Resumable session memory: a record of each dev-agent run, kept across attempts.…, Build and persist the session memory (best-effort). Returns the memory dict., The prior attempt's resume_context for injection into a retry, or None., Changed file paths from a unified diff (the `b/` side of each `diff --git`). (+10 more)

### Community 49 - "MAGE Graph Algorithms"
Cohesion: 0.18
Nodes (18): _driver(), get_jaccard_similarity(), Any, with_retry, MAGE algorithms — the ONLY module where `CALL <module>.<procedure>()` appears.…, Per-meeting path. Cheap enough to run after every processed record., Nightly path. Leiden over the whole graph., Jaccard similarity between two nodes by shared neighbours.… (+10 more)

### Community 50 - "Episodic Memory"
Cohesion: 0.17
Nodes (18): _best_overlap(), decay_relevance(), detect_causality(), _driver(), link_temporal_chain(), log_session(), Any, ExtractedMeeting (+10 more)

### Community 51 - "Cloud Run Job Runners"
Cohesion: 0.15
Nodes (14): main(), _run(), main(), _run(), close_pool(), Close the pool. Cloud Run Jobs are short-lived; leaking it holds server slots., close_driver(), Nightly graph maintenance — the orchestration, not the entrypoint. Sits… (+6 more)

### Community 52 - "Sync Orchestration Script"
Cohesion: 0.18
Nodes (16): ArgumentParser, datetime, build_parser(), export_object_name(), main(), Compact UTC timestamp. Lowercase so it is legal in a GCE resource name, and…, GCS object path for a Cloud SQL export., GCE snapshot name for the Memgraph data disk. Must match… (+8 more)

### Community 53 - "Dashboard Loaders"
Cohesion: 0.22
Nodes (16): get(path) - fetch + throw-on-not-ok JSON helper, loadActions() - /graph/actions/open into ACTIONS + owner filter, LOADERS - tab-name to loader map driving lazy tab population, loadHealth() - /health, shows graph reachability and llm_backend, loadMeetings() - /graph/meetings/recent into MEETINGS, loadOverview() - weekly digest cards + decisions, loadReview() - the three review queues (actions, people, blockers), loadWorkstreams() - communities + influential people, renders the opt-in notice (+8 more)

### Community 54 - "Git Worktree Operations"
Cohesion: 0.18
Nodes (15): authed_remote_url(), create_worktree(), ensure_repo_cloned(), GitError, has_changes(), RuntimeError, Git worktree operations for the dev agent — one worktree per ticket. **One…, Always a fresh clone. Cloud Run Jobs have no persistent filesystem between… (+7 more)

### Community 55 - "Source Adapter Protocol"
Cohesion: 0.12
Nodes (9): Adapter, Protocol, What one source contributes to the pipeline. Everything else is shared., The text handed to the classifier and, prefixed, to the extractor., Signals classify() uses beyond the text itself., meeting_type_router's prompt hint for this payload., Fallback values for null-like extractor fields (date, platform)., Fields where the SOURCE is authoritative and the model is not. A calendar… (+1 more)

### Community 56 - "Gemini Runner Tests"
Cohesion: 0.19
Nodes (12): _fake_spawn(), _FakeProc, Observed live: the CLI edited the file correctly and STILL emitted {"error":…, stderr is frequently just terminal warnings; the useful message is in the JSON…, A zero exit with non-JSON stdout must not crash the run., The CLI's field is `response`; Claude Code's was `result`. A silent mismatch…, _runner_settings(), test_run_agent_prefers_the_json_error_over_stderr_on_nonzero_exit() (+4 more)

### Community 57 - "Module Boundary Rules"
Cohesion: 0.14
Nodes (15): Intent-to-skill map, Project context digest for agents, Empty influential-people state explains tracked is opt-in by design, config.py is the only reader of os.environ, graph_client.py is the only module with generic Cypher, Module boundary rules (one owner per I/O surface), Person.tracked governance gate for per-person analytics, ADR-011 config.py is the only reader of os.environ (+7 more)

### Community 58 - "Token Health & Refresh"
Cohesion: 0.20
Nodes (13): main(), check(), Settings, Token health — proactive checking, so expiry is never a silent surprise. On the…, Refresh the token to prove it still works., render(), TokenHealth, A quiet log line is how a 7-day expiry becomes a three-week outage. (+5 more)

### Community 59 - "Memory API Router"
Cohesion: 0.24
Nodes (13): memory_person(), memory_query(), memory_sessions(), MemoryQuery, Any, BaseModel, post, Principal (+5 more)

### Community 60 - "Webhook Handlers"
Cohesion: 0.20
Nodes (13): _close_agent_run_on_merge(), Any, BackgroundTasks, post, Webhooks — the one public surface. HMAC-verified, never token-authed., GitHub merge/push events. Verified before anything else touches the payload.…, # NOTE: `github_event=`, never `event=`. structlog reserves `event` for the, Jira issue events — status syncing back into the graph. Jira Cloud webhooks… (+5 more)

### Community 61 - "Deployment & Portability ADRs"
Cohesion: 0.19
Nodes (14): Portability to the Onix project as a first-class constraint, ADR-009 Personal GCP project now, Onix Workspace data throughout, ADR-012 Phase 0.5 auth spike passed, no admin allowlisting needed, ADR-016 Ephemeral compute, durable storage: up only when syncing, ADR-017 Phase 1 validated live: the sync lifecycle works, ~11 min to start, A mock that encoded a wrong CLI assumption certified the bug it should have caught, The 7-day refresh-token expiry (External + Testing OAuth client), sync-up / sync-down lifecycle (durable vs ephemeral tiers) (+6 more)

### Community 62 - "LLM Extraction"
Cohesion: 0.20
Nodes (12): ExtractedMeeting, build_system_prompt(), extract_meeting(), _is_null_like(), Any, LLM extraction — v5's tuned prompt, v6's swappable client. The system prompt…, Extract one meeting. Returns None if the model output cannot be used. Retry…, True for None/empty AND for a model that emits the literal string "null"… (+4 more)

### Community 63 - "Lifecycle Transition Tests"
Cohesion: 0.14
Nodes (14): can_transition(), True if ``from_state -> to_state`` is a legal edge., CLOSED means an actual merge. Nothing else follows SHIPPED., A shipped run is done. It does not additionally become FAILED or NEEDS_HUMAN --…, The self-fix loop: the agent's own test run fails, it retries., The review-feedback loop., A human can always be pulled in — there is no state that traps a stuck run with…, test_debugging_can_loop_back_to_implementing() (+6 more)

### Community 64 - "Webhook HMAC Verification"
Cohesion: 0.22
Nodes (14): The header value GitHub would send for this body and secret., Constant-time HMAC check. `hmac.compare_digest` rather than `==`: a naive…, sign(), verify_signature(), _deployed(), _local(), Convenience for local development, where there is nothing to forge., v5 accepted any payload with no secret set. Deployed, that turns the endpoint… (+6 more)

### Community 65 - "Lenient JSON Parsing"
Cohesion: 0.14
Nodes (14): _loads_lenient(), Parse JSON, tolerating a model that wraps the object in stray prose. Tries a…, Observed live: models narrate around the object despite instructions., Local models wrap JSON in ```json fences despite being told not to. CLAUDE.md:…, chat_json promises a dict; a list would break every caller downstream., The object contract is unchanged -- that rejection is correct for extraction,…, test_a_bare_array_is_not_accepted_as_an_object(), test_chat_json_still_rejects_arrays() (+6 more)

### Community 66 - "Memory Retrieval"
Cohesion: 0.25
Nodes (13): assemble_context(), _chat(), _driver(), extract_entities(), full_memory_query(), Any, Memory retrieval — natural-language questions answered from the graph. **Query-…, Gather graph context for a question. Returns (context_lines, node_ids). (+5 more)

### Community 67 - "LLM Retry & Temperature Tests"
Cohesion: 0.14
Nodes (14): _lmstudio_settings(), A timeout or 5xx is transient — retry it., At temperature 0 an identical retry yields identical output, so retrying a…, CLAUDE.md: temperature is 0.0 for extraction. Always., The pipeline marks the record processed and moves on; it must not crash the…, Unrepairable output is still not a crash., test_a_correct_length_embedding_passes_through(), test_a_parse_failure_returns_none_rather_than_raising() (+6 more)

### Community 68 - "Graph Intelligence Phase Notes"
Cohesion: 0.17
Nodes (13): askMemory() - POST /graph/memory/query, shows the grounding node count, esc(v) - HTML-escaping helper applied to every interpolated value, graph_algorithms.py is the only module with MAGE CALL procedures, ADR-003 Keep Memgraph; reject Spanner Graph, ADR-004 Memgraph on a GCE VM first, GKE later, Leiden CPM singleton collapse (308/308 communities of size 1 in v5), Phase 7 - Graph intelligence, /webhook/github pull_request.merged writes CLOSED and RESOLVED_BY (+5 more)

### Community 69 - "LLM Seam Design Rules"
Cohesion: 0.23
Nodes (13): 768-dimensional embeddings pinned by the Memgraph vector indexes, fake backend: a fixture miss raises, never falls through, JSON fence stripping and _is_null_like defences, llm_client.py swappable LLM seam (chat_json / embed), Privacy claim: meeting data never leaves our GCP tenancy, Provenance id derivation belongs to one helper (writer/reader drift bug class), uuid5_id deterministic node ids, ADR-002 Vertex AI Gemini as default LLM behind a swappable seam (+5 more)

### Community 70 - "Pipeline & Migration Bugs"
Cohesion: 0.18
Nodes (13): pipeline.py: one classify->route->extract->graph->jira path, Topic MERGE key is lowercased and stripped, v5 airbyte-lm-studio-memgraph as read-only reference, ADR-006 Claim rows with SELECT ... FOR UPDATE SKIP LOCKED, ADR-010 Collapse the three duplicated pipeline paths into one, ADR-018 One StagedRecord with a JSONB payload, not four typed raw tables, MIGRATION bug #1 - ASSIGNED_TO never formed (owner matched on '@'), INTERESTED_IN silently never formed - semantic_memory matched raw-cased Topic (+5 more)

### Community 71 - "Phase 2 Plan"
Cohesion: 0.17
Nodes (13): Phase 2 Pure Core Implementation Plan, ExtractedMeeting.kind vs router.TYPES vocabulary collision, Task 10 — verify exit criteria and close the phase, Task 1 — config.py typed settings, Task 2 — utils.py port with uuid5_id pinned, Task 3 — models.py and StagedRecord, Task 4 — classifier.py port plus the tests v5 never had, Task 5 — meeting_type_router.py, vocabularies pinned apart (+5 more)

### Community 72 - "Sync Command Runner"
Cohesion: 0.22
Nodes (13): Runner, CompletedProcess, Default runner. Captures output so failures can be reported with context., Raise unless the command succeeded. Every destructive step in sync_down is…, Back up, verify the backup, then destroy the ephemeral tier. Ordering is a…, Recreate the ephemeral tier, restoring the newest matched backup pair., _require(), run() (+5 more)

### Community 73 - "Fixture Recording"
Cohesion: 0.24
Nodes (12): build_parser(), fetch_one(), load_corpus(), main(), prompts_for(), Any, Path, Every meeting in the corpus, sorted for a stable recording order. (+4 more)

### Community 74 - "OAuth Callback Server"
Cohesion: 0.24
Nodes (12): Ephemeral-port loopback callback server, HTTPServer, CallbackServer, An HTTPServer that captures a single OAuth callback., Bind an ephemeral loopback port and return the server and its redirect URI., Block until the callback arrives, then validate it and return the code., start_callback_server(), wait_for_code() (+4 more)

### Community 75 - "Migration Runner"
Cohesion: 0.17
Nodes (12): _main(), `make migrate` — apply the schema, then report what exists. A thin entrypoint…, Any, Run one named step. Imports are local so a single step does not drag in every…, Run each step, catching failures individually. Returns a per-step outcome map…, run(), run_step(), A transient Memgraph conflict in the full algorithm pass must not cost us the… (+4 more)

### Community 76 - "Env & Token Loading"
Cohesion: 0.23
Nodes (12): MonkeyPatch, load_env_file(), load_token(), Path, Load a stored token, or None if there isn't one., Load .env into os.environ if it exists. Returns whether a file was found.      A, Path, override=False, so `GOOGLE_OAUTH_CLIENT_ID=x make auth-spike` still wins. (+4 more)

### Community 77 - "Governance Scope Tests"
Cohesion: 0.27
Nodes (12): _policy(), Principal, Failing open here would hand a stranger whatever the default role is., The governance promise: aggregates are the default and naming individuals is…, test_a_lead_gets_aggregates_not_row_level_detail_at_org_scope(), test_a_member_can_reach_their_own_team(), test_a_member_cannot_reach_another_team(), test_a_member_cannot_reach_org_level() (+4 more)

### Community 78 - "Graph Schema & Provenance"
Cohesion: 0.18
Nodes (11): action_agent deferred to v2 (Airbyte Agents SDK dependency), Graph schema (core, memory, review, provenance), Edge vocabulary aligned with Matteo's engagement ontology, Provenance schema (Ticket, PullRequest, AgentRun, Commit, FileChange), End-to-end data flow (§5), ADR-008 Defer the agents to v2 but ship the provenance schema in v1, Bug 1: ASSIGNED_TO never forms, Bug 2: get_active_run resume loop (+3 more)

### Community 79 - "Dev Agent Self-Verify"
Cohesion: 0.18
Nodes (10): Any, Self-verification: score a dev-agent PR diff against the ticket intent. Runs…, Score one PR diff against its ticket. Never raises — degrades to unchecked., verify_pr(), Must never raise -- verification is best-effort and must not block the review…, test_verify_pr_degrades_to_unchecked_on_a_malformed_response(), test_verify_pr_degrades_to_unchecked_on_empty_output(), test_verify_pr_degrades_to_unchecked_when_the_runner_raises() (+2 more)

### Community 80 - "Jira Source"
Cohesion: 0.24
Nodes (8): JiraSource, Settings, Transport, Settings, Tiers 0 and 1 must run the whole pipeline with no Jira account., test_an_issue_stages_with_its_key_as_the_dedup_id(), test_disabled_jira_stages_nothing_and_does_not_raise(), test_the_jql_carries_the_watermark()

### Community 81 - "Sync Safety Guarantees"
Cohesion: 0.24
Nodes (11): RuntimeError, A sync step failed. Raised rather than returned so no caller can accidentally…, SyncError, _fail(), The single most important test in this file. A failed export followed by a…, gcloud sql export can exit 0 having written nothing usable. Verify the object,…, Only the specific 'matched no objects' message is tolerated. Any other storage…, test_sync_down_never_destroys_when_the_export_object_is_missing() (+3 more)

### Community 82 - "Postgres Integration Tests"
Cohesion: 0.24
Nodes (10): integration, build_dsn(), Plain-Postgres DSN. Only used when the Cloud SQL connector is not., _local_settings(), Point at the local compose Postgres regardless of the developer's .env., The ADR-006 guarantee, proven against a real Postgres. SKIP LOCKED is server-…, A connector re-run must stage no duplicates (PHASE_PLAN Phase 5)., test_build_dsn_uses_the_settings_not_the_environment() (+2 more)

### Community 83 - "Weekly Digest"
Cohesion: 0.24
Nodes (9): Any, Weekly digest — a rollup over the last seven days. Pure shaping over one graph…, Turn raw period activity into the digest. Pure — no I/O., shape(), weekly_digest(), Open vs closed vs high-priority is the whole point of the rollup., A quiet week must render zeros, not crash the dashboard's first tab., test_digest_handles_an_empty_period() (+1 more)

### Community 84 - "Embedding Dimension Guards"
Cohesion: 0.22
Nodes (9): embed(), _fake_vector(), A deterministic unit vector derived from the text. Stable across runs so…, Embed one string. Always `embedding_dimension` long, in every backend., embed() builds its own URL; the regional/global split must hold there too or…, A short vector would fail at Memgraph insert time, far from the call that…, test_a_wrong_length_embedding_raises_rather_than_being_stored(), test_fake_embed_follows_the_configured_dimension() (+1 more)

### Community 85 - "Person Name Disambiguation"
Cohesion: 0.22
Nodes (9): _known(), Meeting notes refer to colleagues by first name constantly, and whole-string…, Two Shubhams means genuine ambiguity. Guessing between colleagues is worse than…, Otherwise "Matteo Rossi" -- a different person -- would match "Matteo Vaiente"…, Deterministic resolution must stay ahead of probabilistic., test_a_first_name_resolves_to_the_one_person_it_names(), test_a_full_name_is_not_rescued_by_its_first_token(), test_an_ambiguous_first_name_stays_in_review() (+1 more)

### Community 86 - "Enrichment Failure Tolerance"
Cohesion: 0.28
Nodes (9): _noop_push(), _noop_upsert(), StagedRecord, A Meet transcript: it skips the classifier gate by design, so this fixture…, The graph write has already committed by the time enrichment runs, so a failing…, No point embedding something the classifier already rejected., _record(), test_a_failing_enrichment_still_leaves_the_record_processed() (+1 more)

### Community 87 - "Insights API Router"
Cohesion: 0.39
Nodes (8): bridges(), communities(), community_members(), influential(), node_insights(), Any, Principal, Top nodes by PageRank. **Governance:** for `Person`, only `tracked = true`…

### Community 88 - "Phase 8 API & Dashboard"
Cohesion: 0.25
Nodes (8): dashboard.html - six-tab single-file operator dashboard, structlog event= kwarg collision (a real v5 production 500), Phase 8 - API and dashboard, api/routers/dev_agent.py - trigger, preflight, run listing, Every route driven through the real ASGI app via httpx.ASGITransport, Endpoint inventory: ported, deferred, dropped, Phase 8 API and Dashboard Implementation Plan, Single-file dashboard.html, no build step

### Community 89 - "Tiered Runbook & Troubleshooting"
Cohesion: 0.25
Nodes (8): make doctor — tier-aware preflight, IAP tunnel to Memgraph Bolt, Measured sync timings in the tier-2 walkthrough, The 7-day clock in the tier-2 runbook, sync-down session end (~3 min), sync-up session start (~11 min), Troubleshooting — Cloud SQL Proxy v2 not found in PATH, Troubleshooting — worked yesterday, fails today

### Community 90 - "Action Item Dedup"
Cohesion: 0.39
Nodes (7): best_match(), cosine(), _norm(), Any, P5 dedup decision: is a new action item a duplicate of an existing open one?…, Return the best candidate above ``threshold`` (with its ``score``), or None., similarity()

### Community 91 - "JSON Array Salvage"
Cohesion: 0.25
Nodes (8): _loads_lenient_list(), Parse a JSON ARRAY, tolerating prose around it. `chat_json` deliberately…, The bug: several prompts say "respond ONLY with a JSON array", and routing them…, Models wrap the array in an object despite being told not to., test_a_bare_array_parses_through_the_list_path(), test_the_list_path_returns_none_for_a_plain_object(), test_the_list_path_salvages_an_array_wrapped_in_prose(), test_the_list_path_unwraps_a_single_key_object()

### Community 93 - "Review Queue Router"
Cohesion: 0.38
Nodes (7): actions(), blockers(), people(), Any, Principal, Items held back from Jira for being below the confidence threshold., Attendees that could not be resolved. Held, never silently dropped.

### Community 94 - "OAuth Callback Handler"
Cohesion: 0.29
Nodes (4): BaseHTTPRequestHandler, _CallbackHandler, CallbackResult, Silence the default stderr access log.          It would echo the query string,

### Community 95 - "OAuth Scopes & PKCE"
Cohesion: 0.38
Nodes (7): Loopback redirect and prompt=consent, The four minimal OAuth scopes, PKCE S256 authorization-code flow, build_auth_url(), Build the Google consent URL.      access_type=offline and prompt=consent are bo, test_auth_url_carries_offline_and_consent(), test_auth_url_requests_exactly_the_four_scopes()

### Community 96 - "Memgraph Readiness Polling"
Cohesion: 0.29
Nodes (7): Block until the Memgraph stack is actually serving, or give up. Terraform…, wait_for_memgraph(), terraform reports the VM ready as soon as the API says RUNNING, which is well…, The console is not readable in the first seconds after boot. A failed read is…, test_wait_for_memgraph_polls_until_the_marker_shows_up(), test_wait_for_memgraph_returns_when_the_marker_appears(), test_wait_for_memgraph_tolerates_a_failing_serial_console_read()

### Community 97 - "Meeting Type Router"
Cohesion: 0.33
Nodes (5): prompt_hint(), P6 meeting-type routing: a cheap classifier between classify() and…, Return the meeting type for `title`/`text`. Email sources are always…, Return the type-specific instruction appended to the extractor system prompt., route()

### Community 98 - "Email Normalisation"
Cohesion: 0.33
Nodes (6): normalize_email(), Lowercase, trim, and drop any ``+tag`` from the local part., alice+jira@corp.com and alice@corp.com are one person. Not collapsing them is…, test_normalize_email_drops_plus_tags(), test_normalize_email_lowercases_and_strips(), test_normalize_email_on_none_is_empty()

### Community 100 - "Community Naming Tests"
Cohesion: 0.33
Nodes (6): _fake_driver_returning(), Minimal async driver returning fixed rows, for exercising the REAL graph_client…, Community 1, size 63" tells a reader nothing. Named by its top topics it reads…, Never render a blank cell., test_a_community_with_no_topics_still_gets_a_label(), test_communities_are_named_not_just_numbered()

### Community 101 - "V5 Port Map & Bugs"
Cohesion: 0.40
Nodes (5): Bug 8: sync_jira_issue always returned True, Bug 10: test-stub pollution, v5 to v6 port map, StagedRecord normalisation question, db.py dual-mode connection

### Community 103 - "LLM Backend Contracts"
Cohesion: 0.50
Nodes (4): Bug 4: literal 'null' strings from the LLM, Hash-keyed fixture replay, Four LLM backends behind one protocol, Reproducibility risks

### Community 104 - "API Test Fixtures"
Cohesion: 0.50
Nodes (4): fixture, app(), Replace every graph read with a shaped stub, so routes are driven for real…, stub_graph()

### Community 105 - "Classifier"
Cohesion: 0.50
Nodes (3): classify(), Any, Rules-based "is this worth processing" score. No LLM. Ported from v5…

### Community 106 - "Algorithm Cadence Rules"
Cohesion: 0.33
Nodes (4): Fast runs per meeting and must stay cheap; Leiden is the more accurate but more…, CLAUDE.md: DO NOT write MemorySession nodes outside memory/episodic.py., test_fast_uses_louvain_and_full_uses_leiden(), test_memory_sessions_are_written_only_by_episodic()

### Community 107 - "Durable Tier Resources"
Cohesion: 0.67
Nodes (3): Durable resource tier, GCP resource inventory (§4), terraform/durable module

### Community 108 - "OAuth Project Migration"
Cohesion: 1.00
Nodes (3): OAuth user type follows the project/account split, Migration to the Onix project, The 7-day refresh token problem

### Community 109 - "Sync Down Verification"
Cohesion: 0.67
Nodes (3): Export/snapshot verification before destroy, sync_down(), SyncError exception

### Community 110 - "Phase 5 Connectors Plan"
Cohesion: 0.67
Nodes (3): Phase 5 Connectors Implementation Plan, Disabled Sources Are No-Ops, Not Errors, Watermark Advances Only After Staging Succeeds

### Community 111 - "Graph Algorithm Retry Rules"
Cohesion: 0.67
Nodes (3): Fast algorithms per meeting, full algorithms nightly, Per-CALL retry for Memgraph 'Cannot resolve conflicting transactions', Every algorithm result consumed before the next CALL (async driver misattribution)

### Community 112 - "Real ASGI Route Tests"
Cohesion: 0.67
Nodes (3): parametrize, Drives the REAL ASGI app. v5's tests called handler functions directly, so a…, test_every_read_route_responds()

## Knowledge Gaps
- **68 isolated node(s):** `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image`, `var.memgraph_machine`, `var.memgraph_restore_snapshot` (+63 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **84 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `LLM Seam & Settings` to `Dev Agent Guardrail Gates`, `Graph Intelligence & Person Memory`, `Pure Core Tests`, `LLM Fixture Replay`, `Dev Agent Backend Routing`, `Graph Client Reads`, `GitHub PR Client`, `Postgres Data Layer`, `Jira Client & Pipeline Tests`, `FastAPI App & Dependencies`, `Data Layer Tests`, `Semantic Memory`, `Cloud SQL Connection Mode`, `Pipeline Drain Tests`, `API Route Tests`, `Jira REST Client`, `Webhook Route Tests`, `Procedural Memory`, `Vector Memory`, `Episodic Memory`, `LLM Extraction`, `Webhook HMAC Verification`, `Memory Retrieval`, `LLM Retry & Temperature Tests`, `Fixture Recording`, `Postgres Integration Tests`, `Embedding Dimension Guards`?**
  _High betweenness centrality (0.177) - this node is a cross-community bridge._
- **Why does `Workspace admin third-party app block` connect `Module Boundary Rules` to `OAuth Scopes & PKCE`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `Module boundary rules (one owner per I/O surface)` connect `Module Boundary Rules` to `Architecture Overview`, `Graph Intelligence Phase Notes`, `LLM Seam Design Rules`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Are the 62 inferred relationships involving `Settings` (e.g. with `settings_dep()` and `extract_meeting()`) actually correct?**
  _`Settings` has 62 INFERRED edges - model-reasoned connections that need verification._
- **What connects `var.cloudsql_tier`, `var.memgraph_disk_gb`, `var.memgraph_image` to the rest of the system?**
  _68 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Reproducibility & Doctor Preflight` be split into smaller, more focused modules?**
  _Cohesion score 0.062434691745036575 - nodes in this community are weakly interconnected._
- **Should `Dev Agent Guardrail Gates` be split into smaller, more focused modules?**
  _Cohesion score 0.043963963963963966 - nodes in this community are weakly interconnected._