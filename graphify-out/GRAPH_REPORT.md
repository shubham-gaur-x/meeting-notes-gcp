# Graph Report - meeting-notes-gcp  (2026-08-24)

## Corpus Check
- 61 files · ~166,924 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2747 nodes · 5457 edges · 246 communities (128 shown, 118 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 296 edges (avg confidence: 0.92)
- Token cost: 120,000 input · 0 output

## Community Hubs (Navigation)
- Guardrail Gate Runner
- Doctor Preflight & Secret Rules
- API Route Tests
- Pure Core Tests
- Terraform Durable Tier
- Guardrail Gate Functions
- Dev Agent API & Poll Job
- Source Adapter Protocol
- Connector Base & Staging
- Dev Agent Orchestrator
- GitHub PR Client
- Graph Read Queries
- Coding Backend Preflight
- Connector Tests
- Drain & Jira Status Sync
- LLM Seam Tests
- Graph Intelligence Tests
- Fake Graph Driver
- LLM Client & Fixtures
- Access Control Policy
- FastAPI App & Auth Deps
- Terraform Ephemeral Tier
- Jira REST Client
- Git Worktree Operations
- Jira Ticket Pusher
- Pipeline Tests
- OAuth Token Refresh
- Episodic Memory
- Vector Embeddings
- Fake Transaction Driver
- OAuth Code Exchange
- Attendee Resolution
- Semantic Memory Consolidation
- KT Deck Generator
- Postgres Staging Layer
- Gmail Connector
- Snapshot & Restore Tests
- Architecture Rules & ADRs
- Auth Spike Runbook
- Dev Agent Lifecycle
- Memgraph Client Core
- PR Self-Verification
- Google Source Construction
- PKCE Loopback Auth Flow
- Meeting Quality Scoring
- Person Name Matching
- Vector Search Tests
- Fake Async Result Driver
- SKIP LOCKED Claiming
- Fake Subprocess Runner
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 134
- Community 135
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 141
- Community 142
- Community 143
- Community 144
- Community 145
- Community 146
- Community 147
- Community 148
- Community 149
- Community 150
- Community 151
- Community 152
- Community 153
- Community 154
- Community 155
- Community 156
- Community 157
- Community 158
- Community 159
- Community 160
- Community 161
- Community 162
- Community 163
- Community 164
- Community 165
- Community 166
- Community 167
- Community 168
- Community 169
- Community 171
- Community 172
- Community 173
- Community 175
- Community 176
- Community 177
- Community 178
- Community 179
- Community 180
- Community 181
- Community 182
- Community 183
- Community 184
- Community 185
- Community 186
- Community 187
- Community 188
- Community 189
- Community 190
- Community 191
- Community 193
- Community 194
- Community 195
- Community 196
- Community 197
- Community 198
- Community 199
- Community 200
- Community 201
- Community 202
- Community 203
- Community 204
- Community 205
- Community 206
- Community 207
- Community 208
- Community 209
- Community 210
- Community 211
- Community 212
- Community 213
- Community 214
- Community 215
- Community 216
- Community 217
- Community 218
- Community 219
- Community 220
- Community 221
- Community 222
- Community 223
- Community 224
- Community 225
- Community 226
- Community 227
- Community 228
- Community 229
- Community 230
- Community 232
- Community 233
- Community 234
- Community 237
- Community 238
- Community 239
- Community 240
- Community 241
- Community 242
- Community 243
- Community 244
- Community 245

## God Nodes (most connected - your core abstractions)
1. `Settings` - 143 edges
2. `get_settings()` - 79 edges
3. `get_driver()` - 58 edges
4. `Principal` - 52 edges
5. `_get()` - 43 edges
6. `FakeSession` - 40 edges
7. `FakeDriver` - 37 edges
8. `Status` - 36 edges
9. `_settings()` - 33 edges
10. `chat_json()` - 29 edges

## Surprising Connections (you probably didn't know these)
- `render_report()` --conceptually_related_to--> `Secret handling rules`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `save_token()` --references--> `Phase 0.5 auth runbook`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `probe_meet()` --conceptually_related_to--> `Meet transcripts via Workspace Events`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `Lowercased Topic MERGE Key` --semantically_similar_to--> `Cross-Source Duplicate Meetings`  [INFERRED] [semantically similar]
  CLAUDE.md → docs/KNOWLEDGE_TRANSFER.html
- `StoredToken` --implements--> `Phase 0.5 auth spike implementation plan`  [EXTRACTED]
  scripts/auth_spike.py → docs/superpowers/plans/2026-08-13-phase-0.5-auth-spike.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **The dev_agent safety net: port, backend, gates, reviewer** — docs_decisions_adr020, docs_decisions_adr021, docs_decisions_adr022, docs_decisions_adr024 [EXTRACTED 1.00]
- **The reproducibility contract (tiers, fake backend, dual-mode db)** — docs_decisions_adr013, docs_decisions_adr014, docs_decisions_adr015, docs_phase_plan_phase06 [EXTRACTED 1.00]
- **Dashboard graph view render path** — api_static_dashboard_loadgraph, api_static_dashboard_layout, api_static_dashboard_wiregraphcanvas, api_static_dashboard_drawgraph, api_static_dashboard_radiusof [EXTRACTED 1.00]
- **ADR-011's config rule enforced by two refactors and an AST check** — docs_superpowers_plans_2026_08_20_phase_2_pure_core_scripts_env_exception [EXTRACTED 1.00]
- **Deferrals Recorded Rather Than Assumed** — docs_superpowers_plans_2026_08_20_phase_3_data_layer_scope_table [EXTRACTED 1.00]
- **Shared Seams Instead of Four Near-Identical Connectors** — docs_superpowers_plans_2026_08_20_phase_5_watermark_ordering, docs_superpowers_plans_2026_08_20_phase_5_disabled_sources_noop [EXTRACTED 1.00]
- **The SHIPPED fix, tested at three independent levels** — docs_superpowers_plans_2026_08_20_phase_11_dev_agent_terminal_states, docs_superpowers_plans_2026_08_20_phase_11_dev_agent_active_run_excluded_states, docs_superpowers_plans_2026_08_20_phase_11_dev_agent_should_attempt_second_check [EXTRACTED 1.00]
- **Sync session lifecycle: ephemeral tier up, work, backed-up teardown** — docs_setup_iap_tunnel [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks [EXTRACTED 1.00]
- **Keeping v5 Safe While Building v6** — docker_compose_local_port_shift, docker_compose_local_stack [EXTRACTED 1.00]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Ephemeral sync-up/sync-down lifecycle** — docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]

## Communities (246 total, 118 thin omitted)

### Community 0 - "Guardrail Gate Runner"
Cohesion: 0.03
Nodes (80): CommandResult, CommandRunner, Any, Evaluate all seven gates for the PR built in `work_dir`., run_gates(), all_passed(), DiffFacts, evaluate_gates() (+72 more)

### Community 1 - "Doctor Preflight & Secret Rules"
Cohesion: 0.07
Nodes (81): Secret handling rules, No-secrets-in-output guarantee (spike), doctor exit code contract, Injected-probe check design, Leak-canary secret test, Phase 0.6 reproducibility implementation plan, doctor.py check contract, Local compose stack design (+73 more)

### Community 2 - "API Route Tests"
Cohesion: 0.05
Nodes (72): parametrize, Response, _get(), _github_post(), _local(), _post(), Any, Phase 8 — the API. Every route is driven through the real ASGI app.… (+64 more)

### Community 3 - "Pure Core Tests"
Cohesion: 0.03
Nodes (44): Phase 2 — the pure core. No I/O, no network, no database. Every test here runs…, The whole MERGE-not-CREATE strategy rests on this. Same input, same id, forever…, v5's actual boundaries: <= 14 days high, <= 60 medium, beyond that low., The shapes below are copied from live `staged_records.payload` rows. Replaces a…, MIGRATION_FROM_V5.md §4 — Airbyte residue must not be ported., LLM output sometimes gives decisions as bare strings. v5's coercion is load-…, Two or more noise markers return 0.0 immediately, before any positive signal is…, The gate is >= 2. One stray 'unsubscribe' in a genuine thread is not enough to… (+36 more)

### Community 4 - "Terraform Durable Tier"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 5 - "Guardrail Gate Functions"
Cohesion: 0.05
Nodes (58): gate_no_new_deps(), gate_protected_paths(), gate_secret_scan(), Fail if the diff touches secrets, CI, key material, or escapes the repo.…, Dependency/lock files must be unchanged unless the ticket opts in. If opted in,…, Scan ADDED lines only for credential-shaped strings. Added lines rather than…, is_terminal(), Whether a run in this state is finished for good. Reads TERMINAL_STATES, which… (+50 more)

### Community 6 - "Dev Agent API & Poll Job"
Cohesion: 0.06
Nodes (50): settings_dep(), preflight(), Dev agent — manual trigger, preflight, and recent-run visibility. Read routes…, Whether the configured coding backend is ready to run, without starting one., BaseSettings, main(), _run(), get_settings() (+42 more)

### Community 7 - "Source Adapter Protocol"
Cohesion: 0.06
Nodes (28): Adapter, CalendarAdapter, EmailAdapter, MeetAdapter, Any, Protocol, The whole conversation, attributed. A thread is staged as one record carrying…, Nothing. A mail header date is when the MESSAGE was sent, which is often not… (+20 more)

### Community 8 - "Connector Base & Staging"
Cohesion: 0.06
Nodes (36): FetchedRecord, The `Source` protocol and the one staging loop every connector shares. v5 had a…, One raw record, ready to stage. `watermark` is the source's own ordering value…, Fetch what changed since `since`. Capture only — never interpret., Fetch, stage everything, then advance the watermark. **The ordering is a…, Source, stage_all(), StageResult (+28 more)

### Community 9 - "Dev Agent Orchestrator"
Cohesion: 0.07
Nodes (52): AgentRunResult, Pydantic v2 models for the autonomous dev agent. **One `state` field, not v5's…, _advance_state(), _default_dependencies(), _Dependencies, _escalate_to_human(), _evaluate_pr(), _finish_without_pr() (+44 more)

### Community 10 - "GitHub PR Client"
Cohesion: 0.06
Nodes (49): BoundLogger, date, F, find_open_pr(), get_pr_diff(), _github_headers(), Any, with_retry (+41 more)

### Community 11 - "Graph Read Queries"
Cohesion: 0.06
Nodes (46): AsyncDriver, get_action_confidence(), get_actions_needing_review(), get_all_communities(), get_driver(), get_graph_snapshot(), get_influential_nodes(), get_meeting_detail() (+38 more)

### Community 12 - "Coding Backend Preflight"
Cohesion: 0.05
Nodes (46): model_for_run(), preflight_gemini(), PreflightError, RuntimeError, Verify the Gemini backend has a project and model configured. Does not make a…, Raised when the selected backend is not ready to run (actionable message)., Model id to pass to ``gemini --model``, or None for the CLI's default., (owner, repo) for this ticket, from its description. Falls back to… (+38 more)

### Community 13 - "Connector Tests"
Cohesion: 0.05
Nodes (34): adf_to_text(), Flatten an Atlassian Document Format node to plain text. Carried from v5…, _pubsub_message(), Any, Phase 5 — the connectors. No live credentials, no network, no database. Every…, All-day events carry `date`, not `dateTime`. Assuming dateTime is a KeyError on…, Cancelled events still come back from the API. Staging them would put meetings…, Jira sends null descriptions constantly. (+26 more)

### Community 14 - "Drain & Jira Status Sync"
Cohesion: 0.07
Nodes (42): main(), Any, Sync one staged Jira issue's status into the graph. Returns whether an…, sync_one(), One staged row from any source. `payload` is deliberately an opaque dict, and…, StagedRecord, adapter_for(), apply_source_overrides() (+34 more)

### Community 15 - "LLM Seam Tests"
Cohesion: 0.06
Nodes (39): fixture_key(), _loads_lenient(), Stable, filename-safe key for a prompt. Covers the system prompt so editing it…, Parse JSON, tolerating a model that wraps the object in stray prose. Tries a…, Phase 4 — the LLM seam. Runs with no network and no API key. Every backend is…, Observed live: models narrate around the object despite instructions., Local models wrap JSON in ```json fences despite being told not to. CLAUDE.md:…, chat_json promises a dict; a list would break every caller downstream. (+31 more)

### Community 16 - "Graph Intelligence Tests"
Cohesion: 0.06
Nodes (42): _meeting(), Phase 7 — graph intelligence. No live Memgraph, no LLM, no network. Every…, Fast runs per meeting and must stay cheap; Leiden is the more accurate but more…, ASSIGNED_TO has the same order-dependence reresolve_reviews exists for.…, A nightly run must not leave a property the fast run sets, or insight endpoints…, CLAUDE.md: MAGE CALL procedures appear in graph_algorithms.py and nowhere else.…, Regression test for a real v5 bug this port fixes. v5's…, This is what makes it memory rather than a log: the same fact from a second… (+34 more)

### Community 17 - "Fake Graph Driver"
Cohesion: 0.07
Nodes (37): FakeDriver, FakeSession, v5 caught failures per algorithm for exactly this reason: a transient conflict…, Consuming is required: the async driver otherwise defers execution and surfaces…, CLAUDE.md: MAGE CALL procedures live only in this module., A null embedding in the index is worse than none: vector search would return it…, Idempotent by construction: a MERGE-matched item from an earlier meeting must…, email1 < email2 stops the double UNWIND emitting each pair twice. (+29 more)

### Community 18 - "LLM Client & Fixtures"
Cohesion: 0.08
Nodes (40): chat_json(), chat_list(), _default_transport(), _fake_chat_json(), fixture_dir(), FixtureMissError, _gemini_chat_request(), _gemini_text() (+32 more)

### Community 19 - "Access Control Policy"
Cohesion: 0.10
Nodes (39): AccessDeniedError, aggregates_only(), authorize(), load_policy(), parse_scope(), Principal, RuntimeError, Phase 33 (core) — principal → scope access policy. Design stance: hierarchy… (+31 more)

### Community 20 - "FastAPI App & Auth Deps"
Cohesion: 0.08
Nodes (34): principal(), Shared dependencies for the API layer. Auth reuses `access_control` from Phase…, Resolve the caller from a bearer token, or 401/403., create_app(), lifespan(), FastAPI service — Cloud Run, scales to zero. Entrypoint only: every route is a…, actions_open(), decisions() (+26 more)

### Community 21 - "Terraform Ephemeral Tier"
Cohesion: 0.09
Nodes (34): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+26 more)

### Community 22 - "Jira REST Client"
Cohesion: 0.11
Nodes (38): active_sprint_id(), add_comment(), create_issue(), _default_transport(), get_issue(), get_issue_detail(), jira_base_url(), jira_headers() (+30 more)

### Community 23 - "Git Worktree Operations"
Cohesion: 0.07
Nodes (35): authed_remote_url(), create_worktree(), default_branch(), ensure_repo_cloned(), GitError, Any, RuntimeError, Git worktree operations for the dev agent — one worktree per ticket. **One… (+27 more)

### Community 24 - "Jira Ticket Pusher"
Cohesion: 0.10
Nodes (34): _create_ticket(), _default_active_sprint_id(), _default_add_comment(), _default_create_issue(), _default_get_open_actions(), _find_duplicate(), _is_gated(), push_action_items() (+26 more)

### Community 25 - "Pipeline Tests"
Cohesion: 0.10
Nodes (27): _email_payload(), _fake_settings(), Phase 6 — the pipeline. No live services; every dependency is injected. The…, Stands in for graph_client.upsert_meeting_graph., Async stand-in for db.mark_processed., The cheap gate stays cheap: no LLM call for obvious noise., Temperature 0: an identical retry yields identical output, so a parse failure…, v5's process_new_emails used asyncio.gather(..., return_exceptions=True) for… (+19 more)

### Community 26 - "OAuth Token Refresh"
Cohesion: 0.10
Nodes (31): get_access_token(), load_refresh_token(), _post_token(), Path, RuntimeError, with_retry, The refresh token is gone or rejected. Deliberately fatal., The refresh token, preferring configuration over the local file. Settings win… (+23 more)

### Community 27 - "Episodic Memory"
Cohesion: 0.12
Nodes (28): _best_overlap(), decay_relevance(), detect_causality(), _driver(), link_temporal_chain(), log_session(), Any, ExtractedMeeting (+20 more)

### Community 28 - "Vector Embeddings"
Cohesion: 0.12
Nodes (28): _driver(), embed_action_items_for_meeting(), embed_facts_for_meeting(), embed_meeting(), _embed_pending(), embed_text(), Any, Vector memory — 768-dim semantic search over Meeting, Fact and ActionItem. Owns… (+20 more)

### Community 29 - "Fake Transaction Driver"
Cohesion: 0.11
Nodes (21): FakeDriver, FakeTx, _meeting(), Records every Cypher statement instead of running it., CLAUDE.md: one ACID transaction per meeting. Sequential separate driver calls…, CLAUDE.md: DO NOT use CREATE for unique nodes — always MERGE., CLAUDE.md: the Topic MERGE key is lowercased and stripped. Raw case fragmented…, Regression test for MIGRATION_FROM_V5.md bug #1. v5 bound `owner_email =… (+13 more)

### Community 30 - "OAuth Code Exchange"
Cohesion: 0.12
Nodes (27): exchange_code(), load_client_credentials(), pkce_pair(), Exchange an authorization code for tokens., Read the OAuth client id and secret, or explain exactly what's missing., Return a (code_verifier, code_challenge) pair using S256., _mock_client(), AsyncClient (+19 more)

### Community 31 - "Attendee Resolution"
Cohesion: 0.12
Nodes (27): Attendee, Indexed lookup over the roster file, by email and by normalised name., Return (resolved, reviews) for a list of attendees., resolve_attendees(), Roster, _known(), Deterministic resolution first, probabilistic second (CLAUDE.md). An exact…, Attendees are never silently dropped — an unresolved one becomes a PersonReview… (+19 more)

### Community 32 - "Semantic Memory Consolidation"
Cohesion: 0.13
Nodes (25): _chat(), consolidate(), _consolidate_one(), consolidate_preferences(), _driver(), extract_facts(), normalise_topic(), _parse_list() (+17 more)

### Community 33 - "KT Deck Generator"
Cohesion: 0.08
Nodes (18): asks, bugs, built, chain, changes, facts, gaps, gates (+10 more)

### Community 34 - "Postgres Staging Layer"
Cohesion: 0.15
Nodes (24): apply_migrations(), claim_batch(), claim_dev_agent_run(), finish_dev_agent_run(), get_active_dev_agent_run(), get_pool(), list_recent_dev_agent_runs(), list_staged_by_type() (+16 more)

### Community 35 - "Gmail Connector"
Cohesion: 0.12
Nodes (22): _collect_parts(), _decode(), _default_transport(), extract_body(), Any, FetchedRecord, with_retry, Gmail connector — new code; Airbyte did this in v5. Incremental by… (+14 more)

### Community 36 - "Snapshot & Restore Tests"
Cohesion: 0.12
Nodes (22): _ok(), CompletedProcess, `gcloud compute disks snapshot` operates on a zonal resource and 400s with…, `gcloud compute disks snapshot` exits 0 as soon as the snapshot is created,…, First ever run: no snapshots, no exports. Must still succeed. `gcloud storage…, End-to-end: the orphan export must not reach `gcloud sql import`., terraform reports the VM ready as soon as the API says RUNNING, which is well…, A VM that never finishes bootstrapping is a real problem, but the tier IS up… (+14 more)

### Community 37 - "Architecture Rules & ADRs"
Cohesion: 0.10
Nodes (24): No Airbyte Rule, No In-Process Scheduler Rule, Single Owner For Provenance IDs, v6 Target Architecture, Single Definition of TERMINAL_STATES, ADR-001 Fresh Repository, Deliberate Port, ADR-003 Keep Memgraph, Reject Spanner Graph, ADR-004 Memgraph on GCE First, GKE Later (+16 more)

### Community 38 - "Auth Spike Runbook"
Cohesion: 0.21
Nodes (23): Meet transcripts via Workspace Events, Phase 0.5 auth runbook, Hand-rolled OAuth over httpx, Meet: reachable vs transcripts-present, Phase 0.5 auth spike implementation plan, Namespace, build_parser(), _error_of() (+15 more)

### Community 39 - "Dev Agent Lifecycle"
Cohesion: 0.09
Nodes (23): assert_transition(), can_transition(), IllegalTransitionError, RuntimeError, Dev-agent run lifecycle: states, the legal-transition table, deterministic IDs.…, Raised when a run is asked to move between two states with no legal edge., True if ``from_state -> to_state`` is a legal edge., Raise :class:`IllegalTransitionError` unless the edge is legal. (+15 more)

### Community 40 - "Memgraph Client Core"
Cohesion: 0.12
Nodes (23): get_known_people(), get_topic_graph(), _normalise_topic(), with_retry, Memgraph — the ONLY module in this package containing generic Cypher. Ported…, Person + Organization + ATTENDED, one statement per attendee. `tracked` is…, Attendees that could not be resolved are HELD for review, never dropped., The Topic MERGE key is normalised (lowercase + strip) to match the id's… (+15 more)

### Community 41 - "PR Self-Verification"
Cohesion: 0.09
Nodes (21): BaseModel, Self-verification: score a dev-agent PR diff against the ticket intent. Runs…, All three independently: checked AND addresses AND confidence >= threshold. A…, VerifyVerdict, _process(), process_ticket with every dependency stubbed, overridable per test., The whole point of the safety net: a PR that trips a deterministic gate must…, The PR is real work. It goes to review for a human, not back to the backlog --… (+13 more)

### Community 42 - "Google Source Construction"
Cohesion: 0.12
Nodes (21): GmailSource, Fetch messages changed since the watermark and shape them for staging., build_google_source(), Any, Construct a Google-backed source with a fresh access token. Token refresh…, _gmail_transport(), Caught a real bug: the connectors initially invented `calendar_event`,…, A duplicate would make two connectors fight over one watermark. (+13 more)

### Community 43 - "PKCE Loopback Auth Flow"
Cohesion: 0.14
Nodes (21): Loopback redirect and prompt=consent, The four minimal OAuth scopes, Ephemeral-port loopback callback server, PKCE S256 authorization-code flow, HTTPServer, build_auth_url(), CallbackServer, _consent() (+13 more)

### Community 44 - "Meeting Quality Scoring"
Cohesion: 0.15
Nodes (19): composite_quality(), compute_quality(), _per_hour(), percentile_rank(), Any, Phase 31 — meeting quality scoring. The graph doesn't just remember meetings,…, Weighted mean over AVAILABLE (non-None) components, weights renormalized.…, Pure: turn one meeting's raw features into components + composite. ``features``… (+11 more)

### Community 45 - "Person Name Matching"
Cohesion: 0.15
Nodes (19): _given_name_matches(), _name_sim(), _norm_name(), Any, P3 entity resolution: resolve extracted attendees to canonical people. Two…, Resolve one attendee (anything with .name/.email/.role) to a canonical…, Retry the review queue against everyone the graph now knows. Resolution is…, Attach ASSIGNED_TO for action items whose owner is resolvable now. Same order-… (+11 more)

### Community 46 - "Vector Search Tests"
Cohesion: 0.16
Nodes (20): _fake_settings(), Path, Semantic-search tests need vectors that are stable across runs yet still…, The indexes use cosine similarity; unit vectors keep scores comparable., The exit criterion, on the fake backend: a recorded response in, a validated…, The invariant this whole mechanism rests on. CLAUDE.md calls writer/reader id…, The hint changes the system prompt, so it must change the key on both sides…, The single most important test in this file. ADR-014: a miss never falls… (+12 more)

### Community 47 - "Fake Async Result Driver"
Cohesion: 0.13
Nodes (9): _FakeDriver, _FakeResult, _FakeSession, Without exclude_id, an item can match itself at similarity 1.0 — by the time…, jira_sync's matched/unmatched counters must mean something — a silent no-op…, A Jira ticket created outside this pipeline is real signal, not a bug — the…, test_get_open_actions_for_owner_excludes_the_given_id(), test_update_action_jira_status_reports_false_for_an_unknown_key() (+1 more)

### Community 48 - "SKIP LOCKED Claiming"
Cohesion: 0.11
Nodes (18): _norm(), ADR-006. Without SKIP LOCKED two overlapping Cloud Run Jobs either block each…, Unordered claiming lets a steadily-arriving source keep jumping the queue and…, ADR-018: one table with a JSONB payload., MIGRATION_FROM_V5.md §4 — no table discovery, no _airbyte_ columns., The claim runs every drain; an unindexed processed flag turns it into a…, Re-running a connector must stage no duplicates (PHASE_PLAN Phase 5). Scoped…, Phase 5's connectors need it. The table ships now because adding it later would… (+10 more)

### Community 49 - "Fake Subprocess Runner"
Cohesion: 0.18
Nodes (14): _fake_spawn(), _FakeProc, `auto_edit` auto-approves EDIT tools only. The agent is told to commit, push…, Observed live: the CLI edited the file correctly and STILL emitted {"error":…, stderr is frequently just terminal warnings; the useful message is in the JSON…, A zero exit with non-JSON stdout must not crash the run., The CLI's field is `response`; Claude Code's was `result`. A silent mismatch…, _runner_settings() (+6 more)

### Community 50 - "Community 50"
Cohesion: 0.21
Nodes (15): get(), loadActions(), LOADERS tab dispatch table, loadMeetings(), loadOverview(), loadReview(), loadWorkstreams(), openMeeting() (+7 more)

### Community 51 - "Community 51"
Cohesion: 0.14
Nodes (15): Whether a NEW attempt on this ticket is allowed. The second, independent half…, should_attempt_dev_agent_run(), DevAgentRun, Any, BaseModel, field_validator, The second half of the ADR-020 fix, exercised directly against the function…, The end-to-end proof, not just the unit-level lifecycle/db tests. A SHIPPED run… (+7 more)

### Community 52 - "Community 52"
Cohesion: 0.15
Nodes (16): Persist what this attempt learned, for the next one to read., set_dev_agent_session_memory(), build_memory(), load_resume_context(), Any, Resumable session memory: a record of each dev-agent run, kept across attempts.…, Build and persist the session memory (best-effort). Returns the memory dict., The prior attempt's resume_context for injection into a retry, or None. (+8 more)

### Community 53 - "Community 53"
Cohesion: 0.23
Nodes (16): Runner, build_parser(), main(), CompletedProcess, Default runner. Captures output so failures can be reported with context., Raise unless the command succeeded. Every destructive step in sync_down is…, Back up, verify the backup, then destroy the ephemeral tier. Ordering is a…, Block until the Memgraph stack is actually serving, or give up. Terraform… (+8 more)

### Community 54 - "Community 54"
Cohesion: 0.18
Nodes (13): FakeSource, FetchedRecord, No records means nothing new; moving the watermark would be a lie., Stands in for db.stage_record + db.set_watermark., Ordering is a correctness property, not a preference. Advancing first means a…, Re-running a connector must stage no duplicates (exit criterion)., RecordingStager, test_an_empty_fetch_leaves_the_watermark_untouched() (+5 more)

### Community 55 - "Community 55"
Cohesion: 0.18
Nodes (16): MonkeyPatch, load_env_file(), load_token(), Path, Write the token 0600.      The mode is set at open time. A write-then-chmod woul, Load a stored token, or None if there isn't one., Load .env into os.environ if it exists. Returns whether a file was found.      A, save_token() (+8 more)

### Community 56 - "Community 56"
Cohesion: 0.20
Nodes (14): ArgumentParser, RuntimeError, build_parser(), fetch_one(), load_corpus(), main(), prompts_for(), Any (+6 more)

### Community 57 - "Community 57"
Cohesion: 0.17
Nodes (12): main(), _run(), close_driver(), Close the shared Bolt driver. Cloud Run recycles instances freely, and a leaked…, main(), Any, ExtractedMeeting, _rebuild() (+4 more)

### Community 58 - "Community 58"
Cohesion: 0.13
Nodes (15): Any, Interpret one finished CLI run. Pure, so the awkward cases are testable. Three…, Total API requests across models — the CLI's nearest thing to a turn count., _result_from_output(), _turns_from_stats(), Seen live: the CLI wrote the file correctly, then emitted {"error": {"type":…, stderr is usually just warnings; the useful message is on stdout., The run may well have done the work -- the PR check is what decides. (+7 more)

### Community 59 - "Community 59"
Cohesion: 0.14
Nodes (14): memory_person(), memory_query(), memory_sessions(), MemoryQuery, Any, BaseModel, post, Answer a natural-language question from the graph. Semantic search is passed in… (+6 more)

### Community 60 - "Community 60"
Cohesion: 0.20
Nodes (13): _close_agent_run_on_merge(), Any, BackgroundTasks, post, Webhooks — the one public surface. HMAC-verified, never token-authed., GitHub merge/push events. Verified before anything else touches the payload.…, # NOTE: `github_event=`, never `event=`. structlog reserves `event` for the, Jira issue events — status syncing back into the graph. Jira Cloud webhooks… (+5 more)

### Community 61 - "Community 61"
Cohesion: 0.20
Nodes (12): ExtractedMeeting, build_system_prompt(), extract_meeting(), _is_null_like(), Any, LLM extraction — v5's tuned prompt, v6's swappable client. The system prompt…, Extract one meeting. Returns None if the model output cannot be used. Retry…, True for None/empty AND for a model that emits the literal string "null"… (+4 more)

### Community 62 - "Community 62"
Cohesion: 0.21
Nodes (13): integration, build_dsn(), Plain-Postgres DSN. Only used when the Cloud SQL connector is not., _local_settings(), Phase 3 — the data layer. Runs with no Postgres and no Memgraph. The claiming…, Point at the local compose Postgres regardless of the developer's .env., The ADR-006 guarantee, proven against a real Postgres. SKIP LOCKED is server-…, A connector re-run must stage no duplicates (PHASE_PLAN Phase 5). (+5 more)

### Community 63 - "Community 63"
Cohesion: 0.22
Nodes (12): main(), check(), Token health — proactive checking, so expiry is never a silent surprise. On the…, Refresh the token to prove it still works., render(), TokenHealth, A quiet log line is how a 7-day expiry becomes a three-week outage., test_a_dead_token_reports_unhealthy_with_a_remediation() (+4 more)

### Community 64 - "Community 64"
Cohesion: 0.16
Nodes (11): load_roster(), normalize_email(), Load the canonical roster from `path` (a JSON list), or an empty roster. v5…, Lowercase, trim, and drop any ``+tag`` from the local part., One known person from the operator-supplied roster file. The roster is the only…, RosterEntry, alice+jira@corp.com and alice@corp.com are one person. Not collapsing them is…, test_load_roster_with_no_path_is_empty_not_an_error() (+3 more)

### Community 65 - "Community 65"
Cohesion: 0.19
Nodes (11): A refresh token plus the metadata needed to reason about its expiry., Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, render_report(), StoredToken, The single most important test in this file. docs/GOOGLE_AUTH.md §7., test_age_and_expiry_math(), test_report_distinguishes_reachable_from_transcripts_present(), test_report_never_contains_the_token() (+3 more)

### Community 66 - "Community 66"
Cohesion: 0.14
Nodes (14): Choose the export and snapshot to restore the ephemeral tier from. `sync_down`…, The shared timestamp in an export object path or a snapshot name., RestorePlan, select_restore_pair(), stamp_of(), The bug this exists to prevent. A sync-down that writes its export and then…, No matched pair must NOT mean discarding usable data — an export can outlive…, Nothing to restore is a legitimate, consistent state — not a mismatch. (+6 more)

### Community 67 - "Community 67"
Cohesion: 0.18
Nodes (13): v6 Graph Schema, Person.tracked Governance Gate, structlog event= Kwarg Ban, End-to-end data flow (§5), ADR-008 Defer the Agents, Ship the Provenance Schema in v1, Graph Schema Summary, Bug 1: ASSIGNED_TO never forms, Bug 2: get_active_run resume loop (+5 more)

### Community 68 - "Community 68"
Cohesion: 0.17
Nodes (13): Phase 2 Pure Core Implementation Plan, ExtractedMeeting.kind vs router.TYPES vocabulary collision, Task 10 — verify exit criteria and close the phase, Task 1 — config.py typed settings, Task 2 — utils.py port with uuid5_id pinned, Task 3 — models.py and StagedRecord, Task 4 — classifier.py port plus the tests v5 never had, Task 5 — meeting_type_router.py, vocabularies pinned apart (+5 more)

### Community 69 - "Community 69"
Cohesion: 0.17
Nodes (13): pull_request_node_id(), Deterministic AgentRun id. Keyed on attempt, so a retry is a new node. Writer…, Deterministic Ticket id. Stable across attempts -- one ticket, one node., Deterministic PullRequest id, keyed on the URL. The URL rather than the number:…, run_id(), ticket_node_id(), Record one dev-agent run as an AgentRun node, linked to its Ticket and…, write_run_provenance() (+5 more)

### Community 70 - "Community 70"
Cohesion: 0.19
Nodes (13): RuntimeError, A sync step failed. Raised rather than returned so no caller can accidentally…, SyncError, _fail(), The single most important test in this file. A failed export followed by a…, gcloud sql export can exit 0 having written nothing usable. Verify the object,…, Only the specific 'matched no objects' message is tolerated. Any other storage…, The console is not readable in the first seconds after boot. A failed read is… (+5 more)

### Community 71 - "Community 71"
Cohesion: 0.15
Nodes (13): A timeout or 5xx is transient — retry it., At temperature 0 an identical retry yields identical output, so retrying a…, CLAUDE.md: temperature is 0.0 for extraction. Always., The pipeline marks the record processed and moves on; it must not crash the…, Unrepairable output is still not a crash., test_a_correct_length_embedding_passes_through(), test_a_parse_failure_returns_none_rather_than_raising(), test_a_transport_error_that_recovers_returns_the_result() (+5 more)

### Community 72 - "Community 72"
Cohesion: 0.17
Nodes (12): Intent-to-skill map, Project context digest for agents, Module Boundary Rules, Lowercased Topic MERGE Key, ADR-011 config.py Is the Only Reader of os.environ, Workspace admin third-party app block, Phase 0 — Documentation, Phase 7 — Graph Intelligence (+4 more)

### Community 73 - "Community 73"
Cohesion: 0.20
Nodes (11): digest_weekly(), Rollup over a window: meetings, decisions, and action items by state.…, Any, Weekly digest — a rollup over the last seven days. Pure shaping over one graph…, Turn raw period activity into the digest. Pure — no I/O. `period` describes the…, shape(), weekly_digest(), Open vs closed vs high-priority is the whole point of the rollup. (+3 more)

### Community 74 - "Community 74"
Cohesion: 0.30
Nodes (12): dev_agent Scope Rules, ADR-020 dev_agent Moves From v2 to v1, ADR-021 dev_agent Runs Gemini CLI on Vertex, ADR-022 Gates Run in the Orchestrator, Failure Escalates to NEEDS_HUMAN, ADR-024 The LLM Reviewer Ships; Both LLM Layers Were Dead, Built vs Pending, Cross-Source Duplicate Meetings, Missing Scope Gate (+4 more)

### Community 75 - "Community 75"
Cohesion: 0.17
Nodes (12): Every schema statement, in application order. Returned rather than executed so…, statements(), CLAUDE.md's schema: every node has a unique id. A label with no constraint…, ADR-008: provenance cannot be backfilled. A merge that happens before the…, CLAUDE.md: 768 in both backends because the indexes are built for 768.…, If someone migrates the indexes, the setting is the single knob., Memgraph takes one statement per run(); a semicolon-joined blob fails., test_both_vector_indexes_use_the_configured_dimension() (+4 more)

### Community 76 - "Community 76"
Cohesion: 0.23
Nodes (11): backup_uri(), Name of the most recent item, or None if there are none. None is a legitimate…, select_latest(), Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016. Every test runs with…, The first-ever sync-up has no snapshot and no export. Not an error., A missing timestamp means gcloud changed its output shape. Fail loudly rather…, test_backup_uri_builds_a_gs_url(), test_select_latest_picks_the_most_recent() (+3 more)

### Community 77 - "Community 77"
Cohesion: 0.18
Nodes (11): bridges(), communities(), community_members(), influential(), node_insights(), Any, Top nodes by PageRank. **Governance:** for `Person`, only `tracked = true`…, Clusters the graph found on its own, each named by the topics inside it. (+3 more)

### Community 78 - "Community 78"
Cohesion: 0.18
Nodes (11): actions(), blockers(), people(), Any, Items held back from Jira for being below the confidence threshold., Attendees that could not be resolved. Held, never silently dropped., Open blockers raised in meetings, with who raised each., app() (+3 more)

### Community 79 - "Community 79"
Cohesion: 0.25
Nodes (11): datetime, export_object_name(), Compact UTC timestamp. Lowercase so it is legal in a GCE resource name, and…, GCS object path for a Cloud SQL export., GCE snapshot name for the Memgraph data disk. Must match…, snapshot_name(), _stamp(), GCE names must match [a-z]([-a-z0-9]*[a-z0-9])? and be <= 63 chars. (+3 more)

### Community 80 - "Community 80"
Cohesion: 0.18
Nodes (11): get_watermark(), Stage one raw record. Returns its id, or None if already staged. The ON…, The last watermark this source reached, or None if it has never run., stage_record(), FetchedRecord, Fetch from one source and stage what it returns., run_source(), _stage() (+3 more)

### Community 81 - "Community 81"
Cohesion: 0.22
Nodes (10): Any, Nightly graph maintenance — the orchestration, not the entrypoint. Sits…, Score every meeting and write the result back. Runs last: `action_completion`…, Run one named step. Imports are local so a single step does not drag in every…, run_step(), _score_quality(), One unscoreable meeting must not cost the whole nightly pass., test_an_unknown_step_is_rejected() (+2 more)

### Community 82 - "Community 82"
Cohesion: 0.33
Nodes (9): LLM Client Seam, ADR-002 Vertex AI Gemini Behind a Swappable Seam, ADR-013 Three-Tier Reproducibility Contract, ADR-014 fake and gemini LLM Backends, ADR-015 db.py Selects Its Connection Mode on Configuration, Phase 0.6 — Reproducibility Skeleton, Phase 4 — LLM Seam, Standing Exit Criterion (Phases 1–9) (+1 more)

### Community 83 - "Community 83"
Cohesion: 0.20
Nodes (10): _default_embed(), embed(), _fake_vector(), A deterministic unit vector derived from the text. Stable across runs so…, Embed one string. Always `embedding_dimension` long, in every backend., embed() builds its own URL; the regional/global split must hold there too or…, A short vector would fail at Memgraph insert time, far from the call that…, test_a_wrong_length_embedding_raises_rather_than_being_stored() (+2 more)

### Community 84 - "Community 84"
Cohesion: 0.28
Nodes (9): ADR-009 Personal GCP Project, Onix Workspace Data, ADR-012 Auth Spike Passed, No Admin Allowlisting Needed, ADR-016 Ephemeral Compute, Durable Storage, ADR-017 Phase 1 Validated Live: ~11 Minutes to Start, Phase 0.5 — Auth Spike, Phase 1 — Terraform Foundation, Phase 10 — Onix Migration, Personal-Then-Onix Deployment Context (+1 more)

### Community 85 - "Community 85"
Cohesion: 0.31
Nodes (8): Swap a set of staged rows for a different set, in ONE transaction. Deleting…, replace_staged_records(), consolidate(), group_by_thread(), Any, A lexically sortable timestamp from the message's Date header. Falls back to…, Staged rows keyed by thread. A row with no thread_id is its own thread., _sort_key()

### Community 86 - "Community 86"
Cohesion: 0.25
Nodes (7): BaseException, LiveModelCallAttempted, _no_live_model_calls(), fixture, Shared test guards. CLAUDE.md: "Tests are mocked — the suite must run with no…, Raised when a test reaches the real model CLI. Deliberately a `BaseException`,…, Fail loudly if a test reaches a real coding-model subprocess. Every dev_agent…

### Community 87 - "Community 87"
Cohesion: 0.25
Nodes (8): make doctor — tier-aware preflight, IAP tunnel to Memgraph Bolt, Measured sync timings in the tier-2 walkthrough, The 7-day clock in the tier-2 runbook, sync-down session end (~3 min), sync-up session start (~11 min), Troubleshooting — Cloud SQL Proxy v2 not found in PATH, Troubleshooting — worked yesterday, fails today

### Community 88 - "Community 88"
Cohesion: 0.25
Nodes (8): build_prompt must never instruct the agent to merge, Cloud Run ephemeral filesystem: always fresh-clone, delete the 'already exists' branch, dev_agent/git_ops.py - one git worktree per ticket, dev_agent/orchestrator.py - triage, process_ticket, poll_and_process, jobs/dev_agent_poll.py - thin Cloud Run Job entrypoint, dev_agent/self_verify.py - diff-vs-ticket scoring that flags, never blocks, dev_agent/session_memory.py - resumable per-ticket memory, should_attempt() as an independent second check before resuming

### Community 89 - "Community 89"
Cohesion: 0.39
Nodes (3): One ingestion run, wired end to end. This exists so `jobs/*` stay thin.…, Entrypoint body shared by every ingest job., run_job()

### Community 90 - "Community 90"
Cohesion: 0.39
Nodes (7): best_match(), cosine(), _norm(), Any, P5 dedup decision: is a new action item a duplicate of an existing open one?…, Return the best candidate above ``threshold`` (with its ``score``), or None., similarity()

### Community 91 - "Community 91"
Cohesion: 0.25
Nodes (8): _loads_lenient_list(), Parse a JSON ARRAY, tolerating prose around it. `chat_json` deliberately…, The bug: several prompts say "respond ONLY with a JSON array", and routing them…, Models wrap the array in an object despite being told not to., test_a_bare_array_parses_through_the_list_path(), test_the_list_path_returns_none_for_a_plain_object(), test_the_list_path_salvages_an_array_wrapped_in_prose(), test_the_list_path_unwraps_a_single_key_object()

### Community 93 - "Community 93"
Cohesion: 0.29
Nodes (7): Any, post, Recent dev-agent runs, newest first, with the PR each produced., Run one poll cycle now instead of waiting for Cloud Scheduler. Returns what the…, runs(), trigger(), BackgroundTasks

### Community 94 - "Community 94"
Cohesion: 0.43
Nodes (6): drawGraph(), Inline force-directed layout (no CDN), layout(), loadGraph(), radiusOf(), wireGraphCanvas()

### Community 95 - "Community 95"
Cohesion: 0.29
Nodes (4): BaseHTTPRequestHandler, _CallbackHandler, CallbackResult, Silence the default stderr access log.          It would echo the query string,

### Community 96 - "Community 96"
Cohesion: 0.29
Nodes (7): Durable-tier one-time apply, The part nobody can automate — OAuth console setup, Tier 0 — local, no credentials, Tier 1 — real LLM, Tier 2 — deploy to your own GCP, Troubleshooting — Error 401 invalid_client during consent, Troubleshooting — local port already in use

### Community 97 - "Community 97"
Cohesion: 0.40
Nodes (6): get_dev_agent_run(), get_dev_agent_session_memory(), Any, This ticket's run, whatever state it is in, or None if never attempted., The resumable record a retry reads, or None. Lives in Postgres rather than on…, _row_to_dev_agent_run()

### Community 98 - "Community 98"
Cohesion: 0.33
Nodes (6): get_bridge_nodes(), get_community_members(), Everything inside one community — the workstream drill-down. Untracked people…, Nodes connecting otherwise separate clusters, by betweenness. Untracked people…, The behaviour, not just the source: an untracked Person must not appear., test_an_untracked_person_is_absent_from_bridges_and_communities()

### Community 99 - "Community 99"
Cohesion: 0.40
Nodes (4): Jira status syncing back into the graph. Returns whether a node matched.…, update_action_jira_status(), _default_update_status(), Jira status -> graph. The reverse direction from jira_pusher. Ported from v5's…

### Community 100 - "Community 100"
Cohesion: 0.33
Nodes (5): prompt_hint(), P6 meeting-type routing: a cheap classifier between classify() and…, Return the meeting type for `title`/`text`. Email sources are always…, Return the type-specific instruction appended to the extractor system prompt., route()

### Community 101 - "Community 101"
Cohesion: 0.40
Nodes (4): Any, field_validator, Backward-compat: decisions are sometimes a list of plain strings in LLM output…, Same leniency `decisions` needs: a bare string becomes {"text": ...}.

### Community 103 - "Community 103"
Cohesion: 0.33
Nodes (6): _person_gating_source(), The function's own body, not a fixed character window. A window ran past the…, CLAUDE.md names centrality explicitly: "Per-person analytics -- PageRank,…, The workstream drill-down lists a cluster's members by name. That is still…, test_bridge_nodes_gate_untracked_people(), test_community_members_gate_untracked_people()

### Community 104 - "Community 104"
Cohesion: 0.33
Nodes (6): _fake_driver_returning(), Minimal async driver returning fixed rows, for exercising the REAL graph_client…, Community 1, size 63" tells a reader nothing. Named by its top topics it reads…, Never render a blank cell., test_a_community_with_no_topics_still_gets_a_label(), test_communities_are_named_not_just_numbered()

### Community 105 - "Community 105"
Cohesion: 0.40
Nodes (5): Bug 8: sync_jira_issue always returned True, Bug 10: test-stub pollution, v5 to v6 port map, StagedRecord normalisation question, db.py dual-mode connection

### Community 106 - "Community 106"
Cohesion: 0.40
Nodes (5): header(), Case-insensitive header lookup. RFC 5322 does not fix the casing., Gmail returns 'Subject', RFC 5322 does not guarantee the casing., test_header_lookup_is_case_insensitive(), test_missing_header_returns_empty_string()

### Community 107 - "Community 107"
Cohesion: 0.50
Nodes (4): Bug 4: literal 'null' strings from the LLM, Hash-keyed fixture replay, Four LLM backends behind one protocol, Reproducibility risks

### Community 108 - "Community 108"
Cohesion: 0.50
Nodes (3): classify(), Any, Rules-based "is this worth processing" score. No LLM. Ported from v5…

### Community 109 - "Community 109"
Cohesion: 0.50
Nodes (4): Run one shell command in `cwd`, returning (exit_code, combined output). A…, run_command(), `ruff`/`mypy`/`pytest` are not on PATH in a bare worktree -- they live in the…, test_gate_commands_run_under_the_jobs_own_interpreter()

### Community 110 - "Community 110"
Cohesion: 0.50
Nodes (4): enrich_step_names(), The enrichment layers `enrich()` runs, in order., `/graph/search/facts` queries the Fact vector index, so a Fact with no…, test_facts_are_embedded_or_fact_search_can_never_return_anything()

### Community 111 - "Community 111"
Cohesion: 0.67
Nodes (3): Durable resource tier, GCP resource inventory (§4), terraform/durable module

### Community 112 - "Community 112"
Cohesion: 1.00
Nodes (3): OAuth user type follows the project/account split, Migration to the Onix project, The 7-day refresh token problem

### Community 113 - "Community 113"
Cohesion: 0.67
Nodes (3): Bug 6: provenance id drift, Bug 7: get_ticket_provenance missing c.message, Bug 5: Topic case fragmentation

### Community 114 - "Community 114"
Cohesion: 0.67
Nodes (3): Export/snapshot verification before destroy, sync_down(), SyncError exception

### Community 115 - "Community 115"
Cohesion: 0.67
Nodes (3): ACTIVE_RUN_EXCLUDED_STATES derived from TERMINAL_STATES, dev_agent/lifecycle.py - state machine with SHIPPED terminal, TERMINAL_STATES as the single definition of 'terminal'

### Community 116 - "Community 116"
Cohesion: 0.67
Nodes (3): api/routers/dev_agent.py - trigger, preflight, run listing, dev_agent/backend.py - coding-model routing and preflight, Every route driven through the real ASGI app via httpx.ASGITransport

### Community 117 - "Community 117"
Cohesion: 0.67
Nodes (3): /webhook/github pull_request.merged writes CLOSED and RESOLVED_BY, github_webhook.verify_signature - constant-time HMAC-SHA256, An unset webhook secret accepts locally but rejects when deployed

### Community 118 - "Community 118"
Cohesion: 0.67
Nodes (3): Phase 5 Connectors Implementation Plan, Disabled Sources Are No-Ops, Not Errors, Watermark Advances Only After Staging Succeeds

### Community 119 - "Community 119"
Cohesion: 0.67
Nodes (3): Fast algorithms per meeting, full algorithms nightly, Per-CALL retry for Memgraph 'Cannot resolve conflicting transactions', Every algorithm result consumed before the next CALL (async driver misattribution)

### Community 120 - "Community 120"
Cohesion: 0.67
Nodes (3): link_action_mentioned_in(), Recurring mention of an existing item — link it rather than duplicating., _default_link_mentioned_in()

### Community 121 - "Community 121"
Cohesion: 0.67
Nodes (3): Record the filed ticket on the ActionItem, marking it `created`. The id must…, update_action_jira_key(), _default_update_jira_key()

### Community 122 - "Community 122"
Cohesion: 0.67
Nodes (3): _deployed(), v5 accepted any payload with no secret set. Deployed, that turns the endpoint…, test_an_unset_secret_REJECTS_when_deployed()

## Knowledge Gaps
- **90 isolated node(s):** `var.billing_account_id`, `var.budget_alert_threshold_ratio`, `var.budget_amount_usd`, `var.vertex_chat_model`, `var.vertex_embedding_model` (+85 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **118 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Dev Agent API & Poll Job` to `Guardrail Gate Runner`, `API Route Tests`, `Pure Core Tests`, `Guardrail Gate Functions`, `Dev Agent Orchestrator`, `Graph Read Queries`, `Coding Backend Preflight`, `Connector Tests`, `Drain & Jira Status Sync`, `LLM Seam Tests`, `Graph Intelligence Tests`, `Fake Graph Driver`, `LLM Client & Fixtures`, `FastAPI App & Auth Deps`, `Jira REST Client`, `Jira Ticket Pusher`, `Community 153`, `OAuth Token Refresh`, `Episodic Memory`, `Vector Embeddings`, `Community 157`, `Pipeline Tests`, `Semantic Memory Consolidation`, `Community 160`, `Postgres Staging Layer`, `Community 162`, `Memgraph Client Core`, `Google Source Construction`, `Vector Search Tests`, `Community 56`, `Community 61`, `Community 62`, `Community 63`, `Community 71`, `Community 80`, `Community 83`, `Community 89`, `Community 122`?**
  _High betweenness centrality (0.213) - this node is a cross-community bridge._
- **Why does `Workspace admin third-party app block` connect `Community 72` to `PKCE Loopback Auth Flow`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `The four minimal OAuth scopes` connect `PKCE Loopback Auth Flow` to `Community 72`, `Auth Spike Runbook`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 76 inferred relationships involving `Settings` (e.g. with `settings_dep()` and `extract_meeting()`) actually correct?**
  _`Settings` has 76 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `Principal` (e.g. with `principal()` and `preflight()`) actually correct?**
  _`Principal` has 31 INFERRED edges - model-reasoned connections that need verification._
- **What connects `var.billing_account_id`, `var.budget_alert_threshold_ratio`, `var.budget_amount_usd` to the rest of the system?**
  _90 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Guardrail Gate Runner` be split into smaller, more focused modules?**
  _Cohesion score 0.03277310924369748 - nodes in this community are weakly interconnected._