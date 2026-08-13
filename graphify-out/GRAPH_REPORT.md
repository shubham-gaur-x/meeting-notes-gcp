# Graph Report - .  (2026-08-13)

## Corpus Check
- Corpus is ~21,578 words - fits in a single context window. You may not need a graph.

## Summary
- 220 nodes · 416 edges · 15 communities (14 shown, 1 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 16 edges (avg confidence: 0.82)
- Token cost: 160,925 input · 0 output

## Community Hubs (Navigation)
- Workspace Auth & Project Governance
- Graph Schema & Data Invariants
- Memgraph Hosting & Ingestion
- LLM Seam & Configuration
- Token Exchange & Refresh
- Loopback Callback Server
- Cloud Run Jobs Rearchitecture
- PKCE & Credential Loading
- Refresh Token Store
- Outcome Report Rendering
- Consent Flow & Auth URL
- Gmail Calendar Meet Probes
- Command-Line Entrypoint
- Project Root

## God Nodes (most connected - your core abstractions)
1. `_mock_client()` - 14 edges
2. `StoredToken` - 11 edges
3. `ProbeResult` - 11 edges
4. `_run()` - 11 edges
5. `render_report()` - 10 edges
6. `_consent()` - 10 edges
7. `start_callback_server()` - 9 edges
8. `probe_gmail()` - 9 edges
9. `run_probes()` - 9 edges
10. `_token()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Rules-based classifier as the cheap pre-LLM gate` --semantically_similar_to--> `Confidence gating on Jira side effects`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → CLAUDE.md
- `Phase 0.5 Auth Spike Implementation Plan` --cites--> `structlog reserved event= kwarg rule`  [EXTRACTED]
  docs/superpowers/plans/2026-08-13-phase-0.5-auth-spike.md → CLAUDE.md
- `test_pkce_challenge_is_s256_of_verifier()` --calls--> `pkce_pair()`  [EXTRACTED]
  tests/test_phase05_auth_spike.py → scripts/auth_spike.py
- `test_pkce_pair_is_random_each_call()` --calls--> `pkce_pair()`  [EXTRACTED]
  tests/test_phase05_auth_spike.py → scripts/auth_spike.py
- `test_pkce_verifier_length_is_rfc7636_compliant()` --calls--> `pkce_pair()`  [EXTRACTED]
  tests/test_phase05_auth_spike.py → scripts/auth_spike.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Airbyte removal spans rule, rationale, ADR and residue cleanup** — claude_no_airbyte_rule, docs_architecture_airbyte_removal, docs_decisions_adr_007, docs_migration_from_v5_airbyte_residue, docs_migration_from_v5_source_protocol [EXTRACTED 1.00]
- **Exactly-once processing under overlapping Cloud Run Jobs** — docs_architecture_skip_locked_claiming, claude_deterministic_uuid5_id, claude_merge_not_create, claude_jira_confidence_gating, docs_decisions_adr_006 [EXTRACTED 1.00]
- **Phase 0.5 loopback OAuth consent flow end to end** — docs_superpowers_plans_2026_08_13_phase_0_5_auth_spike_pkce_pair, docs_superpowers_plans_2026_08_13_phase_0_5_auth_spike_build_auth_url, docs_superpowers_plans_2026_08_13_phase_0_5_auth_spike_callback_server, docs_superpowers_plans_2026_08_13_phase_0_5_auth_spike_exchange_code, docs_superpowers_plans_2026_08_13_phase_0_5_auth_spike_stored_token, docs_superpowers_plans_2026_08_13_phase_0_5_auth_spike_refresh_access_token, docs_superpowers_plans_2026_08_13_phase_0_5_auth_spike_api_probes [EXTRACTED 1.00]

## Communities (15 total, 1 thin omitted)

### Community 0 - "Workspace Auth & Project Governance"
Cohesion: 0.11
Nodes (30): Intent-to-skill map for non-Claude-Code agents, meeting-notes-gcp (v6), Fully mocked test suite invariant (363 tests), Portability to Onix as a design constraint, v5 airbyte-lm-studio-memgraph read-only reference, Known risks register, ADR-001 Fresh repository, deliberate port, ADR-009 Personal GCP project, Onix Workspace data (+22 more)

### Community 1 - "Graph Schema & Data Invariants"
Cohesion: 0.11
Nodes (29): dev_agent and action_agent deferred to v2, Deterministic uuid5_id node ids, Property Graph Schema (core + memory + governance), Confidence gating on Jira side effects, MERGE never CREATE, one ACID transaction, Edge vocabulary aligned to engagement ontology, Person.tracked governance gate, Provenance Schema (schema v1, writers v2) (+21 more)

### Community 2 - "Memgraph Hosting & Ingestion"
Cohesion: 0.08
Nodes (27): Cost posture and levers, GCP resource inventory (all Terraform), GKE Autopilot deferred, GCE VM first, Memgraph MAGE on a GCE VM with persistent disk, Spanner Graph rejected, ADR-003 Keep Memgraph; reject Spanner Graph, ADR-004 Memgraph on GCE VM first, GKE later, Meet transcripts via Workspace Events → Pub/Sub pull (+19 more)

### Community 3 - "LLM Seam & Configuration"
Cohesion: 0.14
Nodes (20): 768-dimensional embedding invariant, config.py is the only os.environ reader, Privacy claim: never leaves our GCP tenancy, llm_client swappable LLM seam, Module Boundary Rules, Retry semantics: transport retries, JSON parse does not, ADR-002 Vertex AI Gemini default behind a swappable seam, ADR-011 config.py is the only reader of os.environ (+12 more)

### Community 4 - "Token Exchange & Refresh"
Cohesion: 0.12
Nodes (19): Request, _error_of(), exchange_code(), Response, Pull Google's error string out of a response body.      Only the error/message f, Exchange an authorization code for tokens., Mint a fresh access token from a stored refresh token., refresh_access_token() (+11 more)

### Community 5 - "Loopback Callback Server"
Cohesion: 0.13
Nodes (15): BaseHTTPRequestHandler, HTTPServer, _CallbackHandler, CallbackResult, CallbackServer, An HTTPServer that captures a single OAuth callback., Silence the default stderr access log.          It would echo the query string,, Bind an ephemeral loopback port and return the server and its redirect URI. (+7 more)

### Community 6 - "Cloud Run Jobs Rearchitecture"
Cohesion: 0.15
Nodes (17): Rule: no Airbyte, Rule: no in-process scheduler, Target Architecture (v6), Airbyte removal and tunnel elimination, APScheduler removal — the biggest structural change, BigQuery as staging layer rejected, Cloud Run Jobs + Cloud Scheduler execution model, Dataflow / Datastream ingestion rejected (+9 more)

### Community 7 - "PKCE & Credential Loading"
Cohesion: 0.19
Nodes (14): load_client_credentials(), pkce_pair(), Read the OAuth client id and secret, or explain exactly what's missing., Return a (code_verifier, code_challenge) pair using S256., Phase 0.5 — the auth spike.  Everything here runs with no live GCP, no Google cr, test_blank_credentials_are_treated_as_missing(), test_credentials_come_from_env(), test_gmail_probe_passes_and_counts() (+6 more)

### Community 8 - "Refresh Token Store"
Cohesion: 0.19
Nodes (11): load_token(), Path, A refresh token plus the metadata needed to reason about its expiry., Write the token 0600.      The mode is set at open time. A write-then-chmod woul, Load a stored token, or None if there isn't one., save_token(), StoredToken, Path (+3 more)

### Community 9 - "Outcome Report Rendering"
Cohesion: 0.31
Nodes (9): Render the human-readable outcome.      Carries every fact the Phase 0.5 outcome, render_report(), The single most important test in this file. docs/GOOGLE_AUTH.md §7., test_age_and_expiry_math(), test_report_distinguishes_reachable_from_transcripts_present(), test_report_never_contains_the_token(), test_report_shows_pass_and_fail(), test_report_states_issue_date_and_expiry() (+1 more)

### Community 10 - "Consent Flow & Auth URL"
Cohesion: 0.25
Nodes (8): Namespace, build_auth_url(), _consent(), Run the interactive loopback consent flow.      wait_for_code blocks on a thread, Build the Google consent URL.      access_type=offline and prompt=consent are bo, _run(), test_auth_url_carries_offline_and_consent(), test_auth_url_requests_exactly_the_four_scopes()

### Community 11 - "Gmail Calendar Meet Probes"
Cohesion: 0.79
Nodes (7): _probe(), probe_calendar(), probe_gmail(), probe_meet(), ProbeResult, AsyncClient, run_probes()

### Community 12 - "Command-Line Entrypoint"
Cohesion: 0.50
Nodes (4): ArgumentParser, build_parser(), main(), test_parser_supports_reconsent()

## Ambiguous Edges - Review These
- `Bug 9 — Leiden community detection collapses to singletons` → `docker-compose.local.yml local stack`  [AMBIGUOUS]
  docs/superpowers/specs/2026-08-13-clone-and-run-design.md · relation: conceptually_related_to

## Knowledge Gaps
- **5 isolated node(s):** `meeting-notes-gcp`, `Bug 10 — test stub pollution and the conftest _REAL_HTTPX fix`, `build_auth_url (access_type=offline, prompt=consent)`, `State validation against CSRF in wait_for_code`, `gemini AI Studio API-key backend`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Bug 9 — Leiden community detection collapses to singletons` and `docker-compose.local.yml local stack`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `README project overview and stack table` connect `Workspace Auth & Project Governance` to `Cloud Run Jobs Rearchitecture`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `v5 → v6 port map (Lift/Adapt/Rewrite/Drop)` connect `Cloud Run Jobs Rearchitecture` to `Workspace Auth & Project Governance`, `Graph Schema & Data Invariants`, `LLM Seam & Configuration`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `jobs/refresh_tokens.py scheduled refresh + loud alert` connect `Memgraph Hosting & Ingestion` to `Workspace Auth & Project Governance`, `Cloud Run Jobs Rearchitecture`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **What connects `meeting-notes-gcp`, `Bug 10 — test stub pollution and the conftest _REAL_HTTPX fix`, `build_auth_url (access_type=offline, prompt=consent)` to the rest of the system?**
  _5 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Workspace Auth & Project Governance` be split into smaller, more focused modules?**
  _Cohesion score 0.11494252873563218 - nodes in this community are weakly interconnected._
- **Should `Graph Schema & Data Invariants` be split into smaller, more focused modules?**
  _Cohesion score 0.10591133004926108 - nodes in this community are weakly interconnected._