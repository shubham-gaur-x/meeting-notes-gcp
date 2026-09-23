# Graph Report - meeting-notes-gcp  (2026-09-23)

## Corpus Check
- 6 files · ~185,756 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3058 nodes · 5783 edges · 252 communities (126 shown, 126 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 261 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Dev Agent Lifecycle Tests
- JSON Salvage & Ticket Keys
- Dev Agent Backend & API Deps
- Jira Client & ADF Formatting
- LLM Seam & Embeddings
- Classifier & A/B Tooling
- Terraform Infrastructure
- Cloud SQL Staging Layer
- Dev Agent Guardrails
- OAuth Spike & Test Guards
- Jira Issue Creation
- API Route Tests
- Dev Agent Orchestration
- Pipeline Source Adapters
- Memgraph Graph Client
- Preflight Doctor
- Meeting Graph Writes
- Graph Intelligence Tests
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
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
- Community 127
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
- Community 166
- Community 167
- Community 169
- Community 170
- Community 171
- Community 172
- Community 173
- Community 174
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
- Community 192
- Community 193
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
- Community 231
- Community 232
- Community 233
- Community 234
- Community 235
- Community 236
- Community 237
- Community 238
- Community 239
- Community 241
- Community 242
- Community 243
- Community 246
- Community 247
- Community 248
- Community 249
- Community 250
- Community 251

## God Nodes (most connected - your core abstractions)
1. `Settings` - 135 edges
2. `get_settings()` - 86 edges
3. `get_driver()` - 59 edges
4. `_get()` - 49 edges
5. `FakeSession` - 40 edges
6. `FakeDriver` - 37 edges
7. `Status` - 36 edges
8. `upsert_meeting_graph()` - 34 edges
9. `_settings()` - 33 edges
10. `chat_json()` - 29 edges

## Surprising Connections (you probably didn't know these)
- `probe_meet()` --conceptually_related_to--> `Meet transcripts via Workspace Events`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `render_report()` --conceptually_related_to--> `Secret handling rules`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `pytest step` --semantically_similar_to--> `Deterministic guardrail gates; a gate that cannot run is a failure`  [INFERRED] [semantically similar]
  .github/workflows/ci.yml → CLAUDE.md
- `save_token()` --references--> `Phase 0.5 auth runbook`  [INFERRED]
  scripts/auth_spike.py → docs/GOOGLE_AUTH.md
- `save_token()` --references--> `No-secrets-in-output guarantee (spike)`  [EXTRACTED]
  scripts/auth_spike.py → docs/superpowers/plans/2026-08-13-phase-0.5-auth-spike.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **The credential-free CI quality gate (ruff, mypy, pytest)** — _github_workflows_ci_ruff_step, _github_workflows_ci_mypy_step, _github_workflows_ci_pytest_step, _github_workflows_ci_no_credentials_ci_contract, claude_tests_need_no_credentials [EXTRACTED 1.00]
- **ADR-011's config rule enforced by two refactors and an AST check** — docs_superpowers_plans_2026_08_20_phase_2_pure_core_scripts_env_exception [EXTRACTED 1.00]
- **Seven lazily-loaded dashboard panels behind one dispatch table** — api_static_dashboard_loaders, api_static_dashboard_loadoverview, api_static_dashboard_loadmeetings, api_static_dashboard_loadactions, api_static_dashboard_loadworkstreams, api_static_dashboard_loadgraph, api_static_dashboard_renderexamples, api_static_dashboard_loadreview, api_static_dashboard_get [EXTRACTED 1.00]
- **Deferrals Recorded Rather Than Assumed** — docs_superpowers_plans_2026_08_20_phase_3_data_layer_scope_table [EXTRACTED 1.00]
- **The dev_agent PR safety net, built across four ADRs** — docs_decisions_adr_020, docs_decisions_adr_022, docs_decisions_adr_024, docs_decisions_adr_025, claude_guardrail_gates, docs_decisions_gate_vs_reviewer_asymmetry, docs_knowledge_transfer_two_layer_pr_defence, claude_never_auto_merge_a_pr [EXTRACTED 1.00]
- **Shared Seams Instead of Four Near-Identical Connectors** — docs_superpowers_plans_2026_08_20_phase_5_watermark_ordering, docs_superpowers_plans_2026_08_20_phase_5_disabled_sources_noop [EXTRACTED 1.00]
- **The reproducibility contract (tiers, fake backend, dual-mode db)** — docs_phase_plan_phase06 [EXTRACTED 1.00]
- **The SHIPPED fix, tested at three independent levels** — docs_superpowers_plans_2026_08_20_phase_11_dev_agent_terminal_states, docs_superpowers_plans_2026_08_20_phase_11_dev_agent_active_run_excluded_states, docs_superpowers_plans_2026_08_20_phase_11_dev_agent_should_attempt_second_check [EXTRACTED 1.00]
- **Sync session lifecycle: ephemeral tier up, work, backed-up teardown** — docs_setup_iap_tunnel [EXTRACTED 1.00]
- **Three-tier reproducibility contract** — docs_superpowers_specs_2026_08_13_clone_and_run_design_three_tier_contract, scripts_doctor_run_checks [EXTRACTED 1.00]
- **Keeping v5 Safe While Building v6** — docker_compose_local_port_shift, docker_compose_local_stack [EXTRACTED 1.00]
- **Removal of Airbyte and APScheduler — the core v5→v6 rearchitecture** — docs_architecture_apscheduler_removal, docs_architecture_airbyte_removal [INFERRED 0.85]
- **Ephemeral sync-up/sync-down lifecycle** — docs_setup_tier2, docs_superpowers_plans_2026_08_19_phase_1_terraform_foundation_sync_py [INFERRED 0.85]

## Communities (252 total, 126 thin omitted)

### Community 0 - "Dev Agent Lifecycle Tests"
Cohesion: 0.02
Nodes (72): _norm(), Phase 11 — the autonomous dev agent (ADR-020). Runs with no live services…, A retry must not collide with the run it is retrying., `ruff`/`mypy`/`pytest` are not on PATH in a bare worktree -- they live in the…, The other half of the ADR-020 fix. If this equality ever fails, someone…, The reviewer is the second layer of the safety net, not a second advisory…, A nit must not hold up a PR a human is going to read anyway., Asymmetry with the deterministic gates, and deliberate: an unrunnable GATE is a… (+64 more)

### Community 1 - "JSON Salvage & Ticket Keys"
Cohesion: 0.04
Nodes (87): AsyncDriver, _adjacent_dates(), close_agent_run_on_merge(), _find_repeat_action(), get_action_confidence(), get_actions_needing_review(), get_all_actions(), get_all_communities() (+79 more)

### Community 2 - "Dev Agent Backend & API Deps"
Cohesion: 0.06
Nodes (83): Secret handling rules, No-secrets-in-output guarantee (spike), doctor exit code contract, Injected-probe check design, Leak-canary secret test, Phase 0.6 reproducibility implementation plan, doctor.py check contract, Local compose stack design (+75 more)

### Community 3 - "Jira Client & ADF Formatting"
Cohesion: 0.06
Nodes (66): Intent-to-skill map, Project context digest for agents, BaseHTTPRequestHandler, Loopback redirect and prompt=consent, Meet transcripts via Workspace Events, OAuth user type follows the project/account split, Migration to the Onix project, Phase 0.5 auth runbook (+58 more)

### Community 4 - "LLM Seam & Embeddings"
Cohesion: 0.05
Nodes (66): apply_migrations(), build_dsn(), claim_batch(), claim_dev_agent_run(), finish_dev_agent_run(), get_active_dev_agent_run(), get_dev_agent_run(), get_dev_agent_session_memory() (+58 more)

### Community 5 - "Classifier & A/B Tooling"
Cohesion: 0.06
Nodes (65): Attendee, get_known_people(), _given_name(), Canonical email for an action item's owner, or None. This is the fix for bug…, Existing Person nodes, for probabilistic resolution (email, name, tracked)., First whitespace-separated token of a name, normalised. '' if there is none.…, _resolve_owner_email(), Any (+57 more)

### Community 6 - "Terraform Infrastructure"
Cohesion: 0.06
Nodes (49): data.google_project.this, google_artifact_registry_repository.images, google_billing_budget.monthly, google_compute_firewall.allow_iap, google_compute_firewall.allow_internal, google_compute_network.vpc, google_compute_subnetwork.subnet, google_monitoring_notification_channel.budget_email (+41 more)

### Community 7 - "Cloud SQL Staging Layer"
Cohesion: 0.04
Nodes (54): _meeting(), ExtractedMeeting, Phase 7 — graph intelligence. No live Memgraph, no LLM, no network. Every…, One unscoreable meeting must not cost the whole nightly pass., Fast runs per meeting and must stay cheap; Leiden is the more accurate but more…, Driving enrich() with a stubbed llm_client.embed and limit of 2 must strictly…, A nightly run must not leave a property the fast run sets, or insight endpoints…, The behaviour, not just the source: an untracked Person must not appear. (+46 more)

### Community 8 - "Dev Agent Guardrails"
Cohesion: 0.08
Nodes (51): MERGE a whole meeting into the graph in ONE transaction. Meeting, People,…, upsert_meeting_graph(), FakeDriver, FakeTx, _meeting(), Phase 3 — the data layer. Runs with no Postgres and no Memgraph. The claiming…, Records every Cypher statement instead of running it. `run` returns an async-…, CLAUDE.md: one ACID transaction per meeting. Sequential separate driver calls… (+43 more)

### Community 9 - "OAuth Spike & Test Guards"
Cohesion: 0.04
Nodes (56): _deployed(), _fake_driver_returning(), _local(), Phase 8 — the API. Every route is driven through the real ASGI app.…, A route added later without the dependency is the failure this catches.…, A project id, region or account email in source is a portability defect…, The second, independent check: the clause is spliced, not parameterised., The governance promise itself, against the real function with a fake driver --… (+48 more)

### Community 10 - "Jira Issue Creation"
Cohesion: 0.05
Nodes (54): CommandResult, Any, Evaluate all seven gates for the PR built in `work_dir`., Read the changed Python files from the worktree for the boundary gate. Only…, read_changed_files(), run_gates(), all_passed(), DiffFacts (+46 more)

### Community 11 - "API Route Tests"
Cohesion: 0.06
Nodes (53): memory_person(), memory_query(), memory_sessions(), MemoryQuery, Any, BaseModel, post, Principal (+45 more)

### Community 12 - "Dev Agent Orchestration"
Cohesion: 0.05
Nodes (41): AsyncClient, BaseException, MonkeyPatch, skipif, StoredToken, LiveModelCallAttempted, _no_live_model_calls(), fixture (+33 more)

### Community 13 - "Pipeline Source Adapters"
Cohesion: 0.04
Nodes (39): _b64(), _pubsub_message(), Any, Phase 5 — the connectors. No live credentials, no network, no database. Every…, Real Gmail nests: multipart/mixed > multipart/alternative > text/plain. A…, Calendar invites and attachment-only mail have no text part at all., Gmail returns 'Subject', RFC 5322 does not guarantee the casing., All-day events carry `date`, not `dateTime`. Assuming dateTime is a KeyError on… (+31 more)

### Community 14 - "Memgraph Graph Client"
Cohesion: 0.06
Nodes (52): _jira_settings(), _meeting(), ExtractedMeeting, Phase 6 — the pipeline. No live services; every dependency is injected. The…, Defence in depth for the failure above: `resolve` accepts Any, and a dict…, enrich() must produce outcomes for all ENRICH_STEPS and remain resilient if an…, v5 left engineering tasks unlabelled and this test pinned that. It is the bug:…, The issue already exists and is more valuable un-sprinted than lost. (+44 more)

### Community 15 - "Preflight Doctor"
Cohesion: 0.06
Nodes (43): FakeDriver, FakeSession, v5 caught failures per algorithm for exactly this reason: a transient conflict…, Consuming is required: the async driver otherwise defers execution and surfaces…, CLAUDE.md: MAGE CALL procedures live only in this module., A null embedding in the index is worse than none: vector search would return it…, Idempotent by construction: a MERGE-matched item from an earlier meeting must…, Regression test for a real v5 bug this port fixes. v5's… (+35 more)

### Community 16 - "Meeting Graph Writes"
Cohesion: 0.06
Nodes (41): settings_dep(), preflight(), Any, Dev agent — manual trigger, preflight, and recent-run visibility. Read routes…, Whether the configured coding backend is ready to run, without starting one., Recent dev-agent runs, newest first, with the PR each produced., runs(), get_settings() (+33 more)

### Community 17 - "Graph Intelligence Tests"
Cohesion: 0.06
Nodes (39): fixture_key(), _loads_lenient(), Stable, filename-safe key for a prompt. Covers the system prompt so editing it…, Parse JSON, tolerating a model that wraps the object in stray prose. Tries a…, Phase 4 — the LLM seam. Runs with no network and no API key. Every backend is…, Observed live: models narrate around the object despite instructions., Local models wrap JSON in ```json fences despite being told not to. CLAUDE.md:…, chat_json promises a dict; a list would break every caller downstream. (+31 more)

### Community 18 - "Community 18"
Cohesion: 0.06
Nodes (40): bridges(), communities(), community_members(), influential(), node_insights(), Any, Top nodes by PageRank. **Governance:** for `Person`, only `tracked = true`…, Clusters the graph found on its own, each named by the topics inside it. (+32 more)

### Community 19 - "Community 19"
Cohesion: 0.09
Nodes (34): data.google_compute_network.vpc, data.google_compute_subnetwork.subnet, data.google_service_account.memgraph, data.google_storage_bucket.backups, google_compute_disk.memgraph_data, google_compute_instance.memgraph, google_sql_database_instance.postgres, google_sql_database.meeting_memory (+26 more)

### Community 20 - "Community 20"
Cohesion: 0.10
Nodes (39): Whether a NEW attempt on this ticket is allowed. The second, independent half…, should_attempt_dev_agent_run(), model_for_run(), Model id to pass to ``gemini --model``, or None for the CLI's default., _advance_state(), build_prompt(), _default_dependencies(), _Dependencies (+31 more)

### Community 21 - "Community 21"
Cohesion: 0.07
Nodes (36): _parse_result(), Any, Headless Gemini CLI runner for the dev agent. Spawns the `gemini` CLI as a…, Run the coding agent to completion on a real task, in `work_dir`. ``--approval-…, Interpret one finished CLI run. Pure, so the awkward cases are testable. Three…, Total API requests across models — the CLI's nearest thing to a turn count., _result_from_output(), run_agent() (+28 more)

### Community 22 - "Community 22"
Cohesion: 0.05
Nodes (30): Phase 2 — the pure core. No I/O, no network, no database. Every test here runs…, A field on the model that the prompt never requests stays empty forever --…, A chat model is stateless, so bumping it costs nothing stored — but the two…, A typo'd source must fail loudly here, not silently skip the drain., LLM output sometimes gives decisions as bare strings. v5's coercion is load-…, CLAUDE.md mandates extra='ignore' — an LLM adding a field must not fail the…, Source type wins over any keyword in the subject., A type missing from _HINTS would silently extract with no type-specific… (+22 more)

### Community 23 - "Community 23"
Cohesion: 0.05
Nodes (39): If a default shells out to a bare `ruff`, it breaks the moment the worktree has…, The CLI reads `<GEMINI_CLI_HOME>/.gemini/settings.json`, not…, One agent serves many repos, so the target cannot be a single global setting.…, `.git`, a trailing slash, or a deep link must not become part of the name., find_sprint_candidates selects on the `dev-agent` label, and create_issue…, `sprint in openSprints()` matches nothing on a Kanban board, so the agent could…, On a Scrum board the sprint is the point: it is what stops the agent picking up…, ADR-021 removed local/vertex/claude. They must fail loudly rather than silently… (+31 more)

### Community 24 - "Community 24"
Cohesion: 0.13
Nodes (37): BaseSettings, F, Settings, active_sprint_id(), add_comment(), create_issue(), create_subtask(), _default_transport() (+29 more)

### Community 25 - "Community 25"
Cohesion: 0.09
Nodes (34): chat_list(), _default_transport(), embed(), _fake_chat_json(), _fake_vector(), fixture_dir(), FixtureMissError, _gemini_chat_request() (+26 more)

### Community 26 - "Community 26"
Cohesion: 0.09
Nodes (36): _github_post(), _post(), Any, Response, An unconfigured token in a deployed project fails loudly, never openly., Writing optimistically shows a done item that is still open in Jira, and the…, Without this the Jira hierarchy exists and the graph one does not, so the…, Also proves the route's own structlog call runs -- the exact thing v5 never… (+28 more)

### Community 27 - "Community 27"
Cohesion: 0.09
Nodes (28): Any, Weekly digest — a rollup over the last seven days. Pure shaping over one graph…, Turn raw period activity into the digest. Pure — no I/O. `period` describes the…, shape(), weekly_digest(), _collect_parts(), _decode(), _default_transport() (+20 more)

### Community 28 - "Community 28"
Cohesion: 0.11
Nodes (15): CalendarAdapter, MeetAdapter, Any, Enrich extracted attendees with verified RFC-2822 header recipient addresses.…, Google Calendar. The most structured source, and the most trusted. An invite…, `start` and the invitee list are ground truth for a calendar event. The…, Invitees carrying a real address. An entry without one (a room, a resource) is…, Google Meet conference records, with a transcript when one exists. A real… (+7 more)

### Community 29 - "Community 29"
Cohesion: 0.09
Nodes (29): main(), _run(), main(), _run(), close_pool(), Close the pool. Cloud Run Jobs are short-lived; leaking it holds server slots., authed_remote_url(), create_worktree() (+21 more)

### Community 30 - "Community 30"
Cohesion: 0.11
Nodes (23): principal(), Shared dependencies for the API layer. Auth reuses `access_control` from Phase…, Resolve the caller from a bearer token, or 401/403., create_app(), lifespan(), FastAPI service — Cloud Run, scales to zero. Entrypoint only: every route is a…, Graph read endpoints. Thin wrappers over `graph_client` (CLAUDE.md)., Graph algorithm insights — influence, communities, bridges. (+15 more)

### Community 31 - "Community 31"
Cohesion: 0.10
Nodes (27): post, Run one poll cycle now instead of waiting for Cloud Scheduler. Returns what the…, trigger(), _close_agent_run_on_merge(), Any, post, Request, Webhooks — the one public surface, so nothing here trusts its own request body.… (+19 more)

### Community 32 - "Community 32"
Cohesion: 0.14
Nodes (29): _driver(), embed_action_items_for_meeting(), embed_facts_for_meeting(), embed_meeting(), _embed_pending(), embed_text(), Any, Settings (+21 more)

### Community 33 - "Community 33"
Cohesion: 0.11
Nodes (27): ActionItem, get_open_actions_for_owner(), Same-owner open items, the dedup candidate set jira_pusher scores against.…, _create_ticket(), _default_active_sprint_id(), _default_add_comment(), _default_create_issue(), _default_embed() (+19 more)

### Community 34 - "Community 34"
Cohesion: 0.10
Nodes (28): actions_list(), actions_open(), decisions(), digest_weekly(), meeting_detail(), meeting_provenance(), meetings_quality(), meetings_recent() (+20 more)

### Community 35 - "Community 35"
Cohesion: 0.12
Nodes (26): _driver(), get_jaccard_similarity(), Any, with_retry, MAGE algorithms — the ONLY module where `CALL <module>.<procedure>()` appears.…, Per-meeting path. Cheap enough to run after every processed record., Nightly path. Leiden over the whole graph., Jaccard similarity between two nodes by shared neighbours.… (+18 more)

### Community 36 - "Community 36"
Cohesion: 0.13
Nodes (25): _chat(), consolidate(), _consolidate_one(), consolidate_preferences(), _driver(), extract_facts(), normalise_topic(), _parse_list() (+17 more)

### Community 37 - "Community 37"
Cohesion: 0.09
Nodes (28): _gates_pass(), _ok(), _process(), The finally block: cleanup must run regardless of outcome. create_worktree is…, process_ticket with every dependency stubbed, overridable per test., The whole point of the safety net: a PR that trips a deterministic gate must…, The PR is real work. It goes to review for a human, not back to the backlog --…, End-to-end through the REAL gate evaluation -- only the shell commands are… (+20 more)

### Community 38 - "Community 38"
Cohesion: 0.08
Nodes (26): classify(), Any, Two or more noise markers return 0.0 immediately, before any positive signal is…, The gate is >= 2 unless from an automated sender. One stray 'unsubscribe' in a…, 2FA codes and sign-in alerts must score 0.0 even when meeting-like signal is…, A single weak-tier noise hit from an automated (no-reply) sender must score…, Out of office, password resets, and invoices must score 0.0 even when the body…, The mirror of the noise tests above, and the one they were missing. Every noise… (+18 more)

### Community 39 - "Community 39"
Cohesion: 0.09
Nodes (26): chat_json(), Ask the model for a JSON OBJECT. Returns None if it does not parse. A bare…, A timeout or 5xx is transient — retry it., At temperature 0 an identical retry yields identical output, so retrying a…, CLAUDE.md: temperature is 0.0 for extraction. Always., PHASE_PLAN Phase 4 task 3: model names are env vars, never literals., `global` is not a region: there is no global-aiplatform.googleapis.com and…, The global special-case must not break every ordinary region. (+18 more)

### Community 40 - "Community 40"
Cohesion: 0.08
Nodes (18): asks, bugs, built, chain, changes, facts, gaps, gates (+10 more)

### Community 41 - "Community 41"
Cohesion: 0.08
Nodes (19): apply_source_overrides(), _attach_header_emails(), EmailAdapter, ExtractedMeeting, Gmail. One record is a whole thread, not a single message. The hardest thing…, The whole conversation, attributed. A thread is staged as one record carrying…, Apply source-authoritative fields, re-validating the result.…, Fill in missing attendee emails from verified message headers, in place. A… (+11 more)

### Community 42 - "Community 42"
Cohesion: 0.12
Nodes (22): _ok(), CompletedProcess, `gcloud compute disks snapshot` operates on a zonal resource and 400s with…, `gcloud compute disks snapshot` exits 0 as soon as the snapshot is created,…, First ever run: no snapshots, no exports. Must still succeed. `gcloud storage…, End-to-end: the orphan export must not reach `gcloud sql import`., terraform reports the VM ready as soon as the API says RUNNING, which is well…, A VM that never finishes bootstrapping is a real problem, but the tier IS up… (+14 more)

### Community 43 - "Community 43"
Cohesion: 0.14
Nodes (22): AccessDeniedError, aggregates_only(), authorize(), load_policy(), parse_scope(), Principal, RuntimeError, Phase 33 (core) — principal → scope access policy. Design stance: hierarchy… (+14 more)

### Community 44 - "Community 44"
Cohesion: 0.12
Nodes (18): _email_payload(), _fake_settings(), Settings, StagedRecord, Stands in for graph_client.upsert_meeting_graph., Async stand-in for db.mark_processed., The cheap gate stays cheap: no LLM call for obvious noise., Temperature 0: an identical retry yields identical output, so a parse failure… (+10 more)

### Community 45 - "Community 45"
Cohesion: 0.09
Nodes (23): _google_settings(), _Path, Exit criterion: a deliberately expired token produces a visible alert, not…, docs/GOOGLE_AUTH.md §7 — the token value is never emitted, and an exception…, token_path is injected so this proves the no-token path regardless of whether…, A 500 is transient; calling it "expired" would send someone to re-consent a…, CLAUDE.md: jobs/ contains entrypoints only; past ~50 lines the logic belongs in…, A thin job wires; it does not branch, loop, or query. (+15 more)

### Community 46 - "Community 46"
Cohesion: 0.14
Nodes (18): main(), get_access_token(), load_refresh_token(), _post_token(), Path, RuntimeError, with_retry, Google OAuth for the connectors: refresh token in, access token out.… (+10 more)

### Community 47 - "Community 47"
Cohesion: 0.09
Nodes (22): adapter_for(), The adapter for one source type. Raises rather than returning a default: a…, The shapes below are copied from live `staged_records.payload` rows. Replaces a…, test_every_adapter_handles_the_real_staged_payload_shape(), The extractor must see every reply, not just the first message., Records staged before this change carry `body` and no `messages`., test_a_single_message_payload_still_works(), test_the_email_adapter_renders_the_whole_thread() (+14 more)

### Community 48 - "Community 48"
Cohesion: 0.16
Nodes (20): check job, CI workflow (GitHub Actions), mypy step, pytest step, Every check runs even after an earlier failure, ruff check step, dev_agent — autonomous ticket implementer (Phase 11), dev_agent coding backend is deliberately separate from llm_client (+12 more)

### Community 49 - "Community 49"
Cohesion: 0.14
Nodes (18): drawGraph() — canvas renderer, get() — fetch-and-parse helper, GRAPH — shared nodes/edges/viewport state, layout() — force-directed graph layout, LOADERS — lazy per-panel dispatch table, loadGraph(), loadMeetings(), loadOverview() (+10 more)

### Community 50 - "Community 50"
Cohesion: 0.14
Nodes (20): CLAUDE.md — authoritative project spec, No in-process scheduler — Cloud Scheduler triggers Cloud Run Jobs, Phase 0.5 auth spike gates everything, Never pass event= to structlog, Portability to the Onix project as a first-class constraint, v6 GCP-native deliberate port, ADR-001 — Fresh repository, deliberate port, ADR-009 — Personal GCP project now, Onix Workspace data throughout (+12 more)

### Community 51 - "Community 51"
Cohesion: 0.12
Nodes (19): best_match(), _norm(), Any, P5 dedup decision: is a new action item a duplicate of an existing open one?…, Overlap of the significant words in two task strings, 0.0 to 1.0. Public…, Return the best candidate above ``threshold`` (with its ``score``), or None., similarity(), token_jaccard() (+11 more)

### Community 52 - "Community 52"
Cohesion: 0.15
Nodes (19): composite_quality(), compute_quality(), _per_hour(), percentile_rank(), Any, Phase 31 — meeting quality scoring. The graph doesn't just remember meetings,…, Weighted mean over AVAILABLE (non-None) components, weights renormalized.…, Pure: turn one meeting's raw features into components + composite. ``features``… (+11 more)

### Community 53 - "Community 53"
Cohesion: 0.16
Nodes (20): _fake_settings(), Path, Semantic-search tests need vectors that are stable across runs yet still…, The indexes use cosine similarity; unit vectors keep scores comparable., The exit criterion, on the fake backend: a recorded response in, a validated…, The invariant this whole mechanism rests on. CLAUDE.md calls writer/reader id…, The hint changes the system prompt, so it must change the key on both sides…, The single most important test in this file. ADR-014: a miss never falls… (+12 more)

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (18): comment(), CommentRequest, _is_done(), link(), LinkRequest, Any, BaseModel, post (+10 more)

### Community 55 - "Community 55"
Cohesion: 0.16
Nodes (12): decode_event(), _default_transport(), entries_to_text(), MeetSource, Any, Transport, with_retry, Google Meet transcripts — ported from v5's `meet_ingest.py`. The one connector… (+4 more)

### Community 56 - "Community 56"
Cohesion: 0.13
Nodes (9): _FakeDriver, _FakeResult, _FakeSession, Without exclude_id, an item can match itself at similarity 1.0 — by the time…, jira_sync's matched/unmatched counters must mean something — a silent no-op…, A Jira ticket created outside this pipeline is real signal, not a bug — the…, test_get_open_actions_for_owner_excludes_the_given_id(), test_update_action_jira_status_reports_false_for_an_unknown_key() (+1 more)

### Community 57 - "Community 57"
Cohesion: 0.15
Nodes (18): StagedRecord, Score every record with both revisions, through the real adapter., Narrow the corpus. Split out from `main` so it is testable without a database., score_records(), select_records(), _classifier(), ModuleType, StagedRecord (+10 more)

### Community 58 - "Community 58"
Cohesion: 0.11
Nodes (18): _norm(), ADR-006. Without SKIP LOCKED two overlapping Cloud Run Jobs either block each…, Unordered claiming lets a steadily-arriving source keep jumping the queue and…, ADR-018: one table with a JSONB payload., MIGRATION_FROM_V5.md §4 — no table discovery, no _airbyte_ columns., The claim runs every drain; an unindexed processed flag turns it into a…, Re-running a connector must stage no duplicates (PHASE_PLAN Phase 5). Scoped…, Phase 5's connectors need it. The table ships now because adding it later would… (+10 more)

### Community 59 - "Community 59"
Cohesion: 0.18
Nodes (14): _fake_spawn(), _FakeProc, `auto_edit` auto-approves EDIT tools only. The agent is told to commit, push…, Observed live: the CLI edited the file correctly and STILL emitted {"error":…, stderr is frequently just terminal warnings; the useful message is in the JSON…, A zero exit with non-JSON stdout must not crash the run., The CLI's field is `response`; Claude Code's was `result`. A silent mismatch…, _runner_settings() (+6 more)

### Community 60 - "Community 60"
Cohesion: 0.18
Nodes (13): FetchedRecord, FakeSource, No records means nothing new; moving the watermark would be a lie., Stands in for db.stage_record + db.set_watermark., Ordering is a correctness property, not a preference. Advancing first means a…, Re-running a connector must stage no duplicates (exit criterion)., RecordingStager, test_an_empty_fetch_leaves_the_watermark_untouched() (+5 more)

### Community 61 - "Community 61"
Cohesion: 0.15
Nodes (12): build_google_source(), Any, FetchedRecord, One ingestion run, wired end to end. This exists so `jobs/*` stay thin.…, Fetch from one source and stage what it returns., Construct a Google-backed source with a fresh access token. Token refresh…, Entrypoint body shared by every ingest job., run_job() (+4 more)

### Community 62 - "Community 62"
Cohesion: 0.18
Nodes (15): main(), _default_process(), _default_sync_jira(), drain_batch(), DrainResult, Any, StagedRecord, Drain one claimed batch: route each record to the pipeline or jira_sync. Exists… (+7 more)

### Community 63 - "Community 63"
Cohesion: 0.23
Nodes (16): Runner, build_parser(), main(), CompletedProcess, Default runner. Captures output so failures can be reported with context., Raise unless the command succeeded. Every destructive step in sync_down is…, Back up, verify the backup, then destroy the ephemeral tier. Ordering is a…, Block until the Memgraph stack is actually serving, or give up. Terraform… (+8 more)

### Community 64 - "Community 64"
Cohesion: 0.18
Nodes (15): ArgumentParser, build_parser(), load_classifier_at_revision(), ModuleType, Import `classifier.py` as it existed at `revision`, without checking it out.…, test_parser_supports_reconsent(), The classifier A/B tool. Not a phase deliverable, so it sits outside the…, Loaded under a private name so the head-side import stays untouched. (+7 more)

### Community 65 - "Community 65"
Cohesion: 0.18
Nodes (11): FetchedRecord, One raw record, ready to stage. `watermark` is the source's own ordering value…, CalendarSource, _default_transport(), event_time(), Any, Transport, with_retry (+3 more)

### Community 66 - "Community 66"
Cohesion: 0.14
Nodes (14): loadActions(), renderActions(), Responsibility filters — mine, shared queue, everyone, setActionDone() — POST /jira/transition, ADR-017 — Phase 1 validated live: the sync lifecycle works, ADR-026 — Jira writes get an authenticated router; PARENT_OF gets a writer, Documented contract with nothing behind it — the recurring audit finding, A mock encoded a wrong assumption and certified the bug (+6 more)

### Community 67 - "Community 67"
Cohesion: 0.13
Nodes (15): gate_module_boundaries(), Flag boundary-marker strings appearing in a file not allowed to hold them.…, Concatenate string literals (best-effort AST) so markers in code strings are…, _string_and_comment_text(), CLAUDE.md: DO NOT put SQL outside meeting_notes/db.py., CLAUDE.md: generic Cypher lives only in graph_client.py., CLAUDE.md: MAGE CALL procedures live only in graph_algorithms.py., A variable literally named `merge` must not trip the Cypher check. (+7 more)

### Community 68 - "Community 68"
Cohesion: 0.17
Nodes (12): One issue the LLM reviewer raised against a diff. Only `severity == "high"`…, ReviewFinding, _format_gates(), Any, BaseModel, The independent LLM reviewer — layer 2 of the PR safety net (ADR-020). Layer 1…, Review one PR. Never raises — degrades to `checked=False`, which never blocks., The reviewer's judgement on one PR. (+4 more)

### Community 69 - "Community 69"
Cohesion: 0.15
Nodes (11): adf_to_text(), Flatten an Atlassian Document Format node to plain text. Carried from v5…, JiraSource, Settings, Transport, Jira connector — new code over a ported client. Incremental by JQL `updated >=…, Jira sends null descriptions constantly., test_adf_flattens_a_simple_paragraph() (+3 more)

### Community 70 - "Community 70"
Cohesion: 0.13
Nodes (8): Adapter, True when the classifier's score should not gate this record., What one source contributes to the pipeline. Everything else is shared., The text handed to the classifier and, prefixed, to the extractor., Signals classify() uses beyond the text itself., meeting_type_router's prompt hint for this payload., Fallback values for null-like extractor fields (date, platform)., Fields where the SOURCE is authoritative and the model is not. A calendar…

### Community 71 - "Community 71"
Cohesion: 0.16
Nodes (14): CI runs with no live GCP, database or LLM, askMemory() — POST /graph/memory/query, Dashboard single-file UI (seven tabs, no build step), No build step and no CDN — the whole UI is one file, renderMarkdown() — hand-rolled Markdown renderer, config.py is the only reader of os.environ, One module owns each external system, dev_agent writes no SQL of its own — db.py stays the one SQL owner (+6 more)

### Community 72 - "Community 72"
Cohesion: 0.25
Nodes (14): CaptureFixture, render(), A rule that lets more mail through is the expensive direction, so the report…, A record belongs to exactly one of the three headline buckets. `moved` overlaps…, The interesting near-miss case: a pattern fired but changed nothing. This is…, _scored(), test_flipped_is_true_only_when_the_gate_decision_changes(), test_moved_catches_a_score_change_that_leaves_the_decision_alone() (+6 more)

### Community 73 - "Community 73"
Cohesion: 0.14
Nodes (14): action_agent deferred to v2 and may not survive, Airbyte removed; ingestion is our own connectors, Graph schema (core, memory, governance, provenance), Edge vocabulary aligned with Matteo's engagement ontology, Provenance node and edge types (Ticket, PullRequest, AgentRun, Commit, FileChange), Topic MERGE key is lowercased and stripped, End-to-end data flow (§5), ADR-007 — Build our own connectors; remove Airbyte (+6 more)

### Community 74 - "Community 74"
Cohesion: 0.20
Nodes (12): ExtractedMeeting, build_system_prompt(), extract_meeting(), _is_null_like(), Any, LLM extraction — v5's tuned prompt, v6's swappable client. The system prompt…, Extract one meeting. Returns None if the model output cannot be used. Retry…, True for None/empty AND for a model that emits the literal string "null"… (+4 more)

### Community 75 - "Community 75"
Cohesion: 0.14
Nodes (14): Choose the export and snapshot to restore the ephemeral tier from. `sync_down`…, The shared timestamp in an export object path or a snapshot name., RestorePlan, select_restore_pair(), stamp_of(), The bug this exists to prevent. A sync-down that writes its export and then…, No matched pair must NOT mean discarding usable data — an export can outlive…, Nothing to restore is a legitimate, consistent state — not a mismatch. (+6 more)

### Community 76 - "Community 76"
Cohesion: 0.17
Nodes (13): Phase 2 Pure Core Implementation Plan, ExtractedMeeting.kind vs router.TYPES vocabulary collision, Task 10 — verify exit criteria and close the phase, Task 1 — config.py typed settings, Task 2 — utils.py port with uuid5_id pinned, Task 3 — models.py and StagedRecord, Task 4 — classifier.py port plus the tests v5 never had, Task 5 — meeting_type_router.py, vocabularies pinned apart (+5 more)

### Community 77 - "Community 77"
Cohesion: 0.24
Nodes (12): build_parser(), fetch_one(), load_corpus(), main(), prompts_for(), Any, Path, Every meeting in the corpus, sorted for a stable recording order. (+4 more)

### Community 78 - "Community 78"
Cohesion: 0.19
Nodes (13): RuntimeError, A sync step failed. Raised rather than returned so no caller can accidentally…, SyncError, _fail(), The single most important test in this file. A failed export followed by a…, gcloud sql export can exit 0 having written nothing usable. Verify the object,…, Only the specific 'matched no objects' message is tolerated. Any other storage…, The console is not readable in the first seconds after boot. A failed read is… (+5 more)

### Community 79 - "Community 79"
Cohesion: 0.15
Nodes (3): _AsyncRows, FakeSession, Stand-in for a driver result: async-iterable over dict rows.

### Community 80 - "Community 80"
Cohesion: 0.23
Nodes (12): MERGE never CREATE, one ACID transaction, Writer/reader provenance id drift — known v5 bug class, Deterministic uuid5_id for every node, ADR-005 — Replace APScheduler with Cloud Scheduler + Cloud Run Jobs, ADR-006 — Claim rows with SELECT ... FOR UPDATE SKIP LOCKED, ADR-010 — Collapse the three duplicated pipeline paths into one, ADR-018 — One StagedRecord with a JSONB payload, ADR-023 — Blockers are extracted, and the Raw* models are removed (+4 more)

### Community 81 - "Community 81"
Cohesion: 0.18
Nodes (9): Rules-based "is this worth processing" score. No LLM. Ported from v5…, enrich_step_names(), PipelineResult, The pipeline — one `process(record, adapter)`, not three copies (ADR-010). v5's…, The enrichment layers `enrich()` runs, in order., What one staged record turned into. All three outcomes are normal and none is…, main(), `/graph/search/facts` queries the Fact vector index, so a Fact with no… (+1 more)

### Community 82 - "Community 82"
Cohesion: 0.20
Nodes (9): The `Source` protocol and the one staging loop every connector shares. v5 had a…, Fetch what changed since `since`. Capture only — never interpret., Fetch, stage everything, then advance the watermark. **The ordering is a…, Source, stage_all(), StageResult, Protocol, StageFn (+1 more)

### Community 83 - "Community 83"
Cohesion: 0.23
Nodes (11): backup_uri(), Name of the most recent item, or None if there are none. None is a legitimate…, select_latest(), Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016. Every test runs with…, The first-ever sync-up has no snapshot and no export. Not an error., A missing timestamp means gcloud changed its output shape. Fail loudly rather…, test_backup_uri_builds_a_gs_url(), test_select_latest_picks_the_most_recent() (+3 more)

### Community 84 - "Community 84"
Cohesion: 0.27
Nodes (12): _policy(), Principal, Failing open here would hand a stranger whatever the default role is., The governance promise: aggregates are the default and naming individuals is…, test_a_lead_gets_aggregates_not_row_level_detail_at_org_scope(), test_a_member_can_reach_their_own_team(), test_a_member_cannot_reach_another_team(), test_a_member_cannot_reach_org_level() (+4 more)

### Community 85 - "Community 85"
Cohesion: 0.25
Nodes (11): datetime, export_object_name(), Compact UTC timestamp. Lowercase so it is legal in a GCE resource name, and…, GCS object path for a Cloud SQL export., GCE snapshot name for the Memgraph data disk. Must match…, snapshot_name(), _stamp(), GCE names must match [a-z]([-a-z0-9]*[a-z0-9])? and be <= 63 chars. (+3 more)

### Community 86 - "Community 86"
Cohesion: 0.22
Nodes (11): _gmail_transport(), Three replies on one thread, delivered out of order by the API., Three messages in one conversation were three staged records, so the pipeline…, Order matters: the last word on a thread is usually the decision, and the API…, A thread is re-fetched when any message in it is new, so the watermark has to…, test_a_fetched_message_becomes_a_staged_record(), test_a_thread_becomes_one_record_not_one_per_message(), test_no_messages_yields_no_records() (+3 more)

### Community 87 - "Community 87"
Cohesion: 0.20
Nodes (10): CommandRunner, gate_lint_type_clean(), gate_tests_green(), The project's own test suite, run inside the agent's worktree. A runner that…, ruff and mypy together, as one gate. Both run even when the first fails, so a…, test_lint_type_clean_fails_when_mypy_is_dirty(), test_lint_type_clean_fails_when_ruff_is_dirty(), test_lint_type_clean_passes_when_both_are_clean() (+2 more)

### Community 88 - "Community 88"
Cohesion: 0.20
Nodes (10): build_prompt must never instruct the agent to merge, Cloud Run ephemeral filesystem: always fresh-clone, delete the 'already exists' branch, dev_agent/git_ops.py - one git worktree per ticket, dev_agent/guardrails.py - seven deterministic gates, dev_agent/orchestrator.py - triage, process_ticket, poll_and_process, Planted-violation testing: a gate proving only the happy path proves nothing, jobs/dev_agent_poll.py - thin Cloud Run Job entrypoint, dev_agent/self_verify.py - diff-vs-ticket scoring that flags, never blocks (+2 more)

### Community 89 - "Community 89"
Cohesion: 0.20
Nodes (8): parametrize, _CapturingDriver, Records the Cypher a real graph_client function generates., One Cypher query for both, so the two cannot drift apart., Drives the REAL ASGI app. v5's tests called handler functions directly, so a…, test_every_read_route_responds(), test_get_all_actions_filters_on_done(), test_get_open_actions_is_the_undone_slice_of_get_all_actions()

### Community 90 - "Community 90"
Cohesion: 0.36
Nodes (9): 768-dimensional embeddings in every backend, A fake fixture miss raises, never falls through, Fence stripping and _is_null_like LLM defences, llm_client backend seam (vertex | gemini | fake), Privacy claim: meeting data never leaves our GCP tenancy, ADR-002 — Vertex AI Gemini default behind a swappable seam, ADR-014 — A fake fixture-replay backend and a gemini backend for tier 1, ADR-027 — The embedding model default is pinned; the chat model default is not (+1 more)

### Community 91 - "Community 91"
Cohesion: 0.31
Nodes (8): find_open_pr(), get_pr_diff(), _github_headers(), Any, with_retry, GitHub API client — read-only PR verification. The dev agent never opens a PR…, Return {number, html_url} for the first open PR on this branch, or None., The unified diff for a PR (truncated to `max_bytes`), or "" if unavailable.…

### Community 92 - "Community 92"
Cohesion: 0.22
Nodes (9): gate_protected_paths(), Fail if the diff touches secrets, CI, key material, or escapes the repo.…, .env.example holds no secrets -- it is the committed template., test_protected_paths_allows_env_example(), test_protected_paths_fails_on_ci_config(), test_protected_paths_fails_on_key_material(), test_protected_paths_fails_on_paths_escaping_the_repo(), test_protected_paths_fails_when_touching_env() (+1 more)

### Community 93 - "Community 93"
Cohesion: 0.25
Nodes (7): Any, BaseModel, Self-verification: score a dev-agent PR diff against the ticket intent. Runs…, All three independently: checked AND addresses AND confidence >= threshold. A…, Score one PR diff against its ticket. Never raises — degrades to unchecked., verify_pr(), VerifyVerdict

### Community 94 - "Community 94"
Cohesion: 0.28
Nodes (9): _noop_push(), _noop_upsert(), StagedRecord, A Meet transcript: it skips the classifier gate by design, so this fixture…, The graph write has already committed by the time enrichment runs, so a failing…, No point embedding something the classifier already rejected., _record(), test_a_failing_enrichment_still_leaves_the_record_processed() (+1 more)

### Community 95 - "Community 95"
Cohesion: 0.25
Nodes (8): make doctor — tier-aware preflight, IAP tunnel to Memgraph Bolt, Measured sync timings in the tier-2 walkthrough, The 7-day clock in the tier-2 runbook, sync-down session end (~3 min), sync-up session start (~11 min), Troubleshooting — Cloud SQL Proxy v2 not found in PATH, Troubleshooting — worked yesterday, fails today

### Community 96 - "Community 96"
Cohesion: 0.25
Nodes (8): _loads_lenient_list(), Parse a JSON ARRAY, tolerating prose around it. `chat_json` deliberately…, The bug: several prompts say "respond ONLY with a JSON array", and routing them…, Models wrap the array in an object despite being told not to., test_a_bare_array_parses_through_the_list_path(), test_the_list_path_returns_none_for_a_plain_object(), test_the_list_path_salvages_an_array_wrapped_in_prose(), test_the_list_path_unwraps_a_single_key_object()

### Community 97 - "Community 97"
Cohesion: 0.25
Nodes (6): label(), Identify a record without leaking mail contents by default., One staged record scored by both revisions., Scored, test_label_shows_the_subject_when_explicitly_asked(), test_label_withholds_the_subject_by_default()

### Community 99 - "Community 99"
Cohesion: 0.29
Nodes (7): date, priority_from_due(), Map a due date to a Jira priority. No due date is 'low', not 'medium'., v5's actual boundaries: <= 14 days high, <= 60 medium, beyond that low., Deliberately 'low', not 'medium' — an item with no due date is not urgent.…, test_priority_from_due_escalates_as_the_date_approaches(), test_priority_from_due_with_no_date_is_low()

### Community 100 - "Community 100"
Cohesion: 0.29
Nodes (7): Durable-tier one-time apply, The part nobody can automate — OAuth console setup, Tier 0 — local, no credentials, Tier 1 — real LLM, Tier 2 — deploy to your own GCP, Troubleshooting — Error 401 invalid_client during consent, Troubleshooting — local port already in use

### Community 101 - "Community 101"
Cohesion: 0.33
Nodes (7): integration, _local_settings(), Point at the local compose Postgres regardless of the developer's .env., The ADR-006 guarantee, proven against a real Postgres. SKIP LOCKED is server-…, A connector re-run must stage no duplicates (PHASE_PLAN Phase 5)., test_restaging_the_same_source_id_does_not_duplicate(), test_two_concurrent_claims_take_disjoint_batches()

### Community 102 - "Community 102"
Cohesion: 0.29
Nodes (7): cosine(), An all-zero embedding is what a failed embed() call looks like. It must return…, A dimension change (768 vs anything else) must not crash the pipeline., test_cosine_handles_a_zero_vector_without_dividing_by_zero(), test_cosine_handles_mismatched_lengths(), test_cosine_of_identical_vectors_is_one(), test_cosine_of_orthogonal_vectors_is_zero()

### Community 103 - "Community 103"
Cohesion: 0.33
Nodes (6): gate_secret_scan(), Scan ADDED lines only for credential-shaped strings. Added lines rather than…, test_secret_scan_catches_a_github_token(), test_secret_scan_catches_a_private_key_header(), test_secret_scan_catches_an_anthropic_style_key(), test_secret_scan_passes_on_clean_lines()

### Community 104 - "Community 104"
Cohesion: 0.33
Nodes (5): prompt_hint(), P6 meeting-type routing: a cheap classifier between classify() and…, Return the meeting type for `title`/`text`. Email sources are always…, Return the type-specific instruction appended to the extractor system prompt., route()

### Community 105 - "Community 105"
Cohesion: 0.33
Nodes (6): Local models often wrap JSON responses in ```json ... ``` fences despite being…, strip_json_fences(), Local models wrap JSON in ```json fences despite being told not to. Found by…, test_strip_json_fences_leaves_bare_json_alone(), test_strip_json_fences_on_empty_input(), test_strip_json_fences_removes_a_fenced_block()

### Community 106 - "Community 106"
Cohesion: 0.33
Nodes (6): _person_gating_source(), The function's own body, not a fixed character window. A window ran past the…, CLAUDE.md names centrality explicitly: "Per-person analytics -- PageRank,…, The workstream drill-down lists a cluster's members by name. That is still…, test_bridge_nodes_gate_untracked_people(), test_community_members_gate_untracked_people()

### Community 107 - "Community 107"
Cohesion: 0.40
Nodes (5): Bug 8: sync_jira_issue always returned True, Bug 10: test-stub pollution, v5 to v6 port map, StagedRecord normalisation question, db.py dual-mode connection

### Community 108 - "Community 108"
Cohesion: 0.40
Nodes (5): is_recap_title(), ExtractedMeeting, Whether a title announces itself as a recap of some other meeting., _write_meeting(), test_recap_titles_are_told_apart_from_the_meetings_they_recap()

### Community 109 - "Community 109"
Cohesion: 0.40
Nodes (5): extract_ticket_keys(), Return de-duplicated Jira ticket keys found in free text, order-preserving., test_extract_ticket_keys_dedupes_preserving_order(), test_extract_ticket_keys_finds_jira_style_keys(), test_extract_ticket_keys_on_none_is_empty()

### Community 110 - "Community 110"
Cohesion: 0.50
Nodes (4): Bug 4: literal 'null' strings from the LLM, Hash-keyed fixture replay, Four LLM backends behind one protocol, Reproducibility risks

### Community 111 - "Community 111"
Cohesion: 0.50
Nodes (4): fixture, app(), Replace every graph read with a shaped stub, so routes are driven for real…, stub_graph()

### Community 112 - "Community 112"
Cohesion: 0.67
Nodes (3): Durable resource tier, GCP resource inventory (§4), terraform/durable module

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

## Ambiguous Edges - Review These
- `Nothing is deployed — no Terraform applied, no Cloud Run resource exists` → `ADR-017 — Phase 1 validated live: the sync lifecycle works`  [AMBIGUOUS]
  docs/KNOWLEDGE_TRANSFER.html · relation: conceptually_related_to

## Knowledge Gaps
- **114 isolated node(s):** `tf_bootstrap.sh script`, `startup.sh script`, `var.billing_account_id`, `var.budget_alert_threshold_ratio`, `var.budget_amount_usd` (+109 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **126 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Nothing is deployed — no Terraform applied, no Cloud Run resource exists` and `ADR-017 — Phase 1 validated live: the sync lifecycle works`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Settings` connect `Community 24` to `Dev Agent Lifecycle Tests`, `JSON Salvage & Ticket Keys`, `LLM Seam & Embeddings`, `Dev Agent Guardrails`, `OAuth Spike & Test Guards`, `Jira Issue Creation`, `API Route Tests`, `Community 140`, `Community 141`, `Pipeline Source Adapters`, `Meeting Graph Writes`, `Graph Intelligence Tests`, `Community 20`, `Community 21`, `Community 22`, `Community 23`, `Community 25`, `Community 153`, `Community 26`, `Community 30`, `Community 31`, `Community 158`, `Community 33`, `Community 34`, `Community 36`, `Community 39`, `Community 45`, `Community 46`, `Community 53`, `Community 61`, `Community 74`, `Community 77`, `Community 101`?**
  _High betweenness centrality (0.165) - this node is a cross-community bridge._
- **Why does `Project context digest for agents` connect `Jira Client & ADF Formatting` to `Community 71`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Are the 72 inferred relationships involving `Settings` (e.g. with `settings_dep()` and `actions_list()`) actually correct?**
  _`Settings` has 72 INFERRED edges - model-reasoned connections that need verification._
- **What connects `tf_bootstrap.sh script`, `startup.sh script`, `var.billing_account_id` to the rest of the system?**
  _114 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Dev Agent Lifecycle Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.01940700808625337 - nodes in this community are weakly interconnected._
- **Should `JSON Salvage & Ticket Keys` be split into smaller, more focused modules?**
  _Cohesion score 0.04362591431556949 - nodes in this community are weakly interconnected._