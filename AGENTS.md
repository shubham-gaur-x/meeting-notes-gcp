# AGENTS.md — meeting-notes-gcp

Intent-to-skill map for non-Claude-Code agents (Codex, Gemini CLI, Cursor).
Claude Code users: read `CLAUDE.md` and use `/architect`, `/plan`, `/build`, `/review`, `/ship`.

## Intent → skill

| Intent | Skill | Notes |
|---|---|---|
| Starting a phase | brainstorming → writing-plans | Spec into `docs/superpowers/specs/` before code |
| Implementing a task | subagent-driven-development | One task at a time |
| Writing a test | test-driven-development | RED first, always |
| Bug investigation | systematic-debugging | 4-phase root cause |
| Code review | requesting-code-review | Before any merge |
| Finishing a branch | finishing-a-development-branch | Tests green first |
| Enterprise business queries | antigravity-swarm personas | Parallel 20+ persona queries (`antigravity-swarm/personas/personas.yaml`) |
| Pre-flight ship gate | ship-check | Verification checklist before PR creation |
| Prompt query sharpening | sharpen-query | Spec-driven, bounded, verifiable prompt restructuring |
| Architecture planning | plan-before-code | Formal spec into `docs/superpowers/specs/` before edits |

## Project context

Read `CLAUDE.md` before any task, then `docs/PHASE_PLAN.md` and `docs/superpowers/specs/ONIX_PRODUCTION_SPEC.md`. The short version:

- **GCP-native.** Cloud Run + Cloud SQL + Vertex AI + Memgraph on GCE/GKE. All Terraform.
- **No Airbyte.** Ingestion is our own Cloud Run Job connectors.
- **No in-process scheduler.** Cloud Scheduler triggers Cloud Run Jobs. Never APScheduler.
- **`config.py` is the only reader of `os.environ`.**
- **SQL only in `db.py`. Cypher only in `graph_client.py`. MAGE `CALL` only in
  `graph_algorithms.py`. Jira REST only in `jira_client.py`. LLM clients only in
  `llm_client.py`.**
- **All graph writes use `MERGE`, in a single ACID transaction.**
- **No hardcoded project IDs, regions, or account emails.** The project moves from a personal
  GCP account to an Onix one (`docs/superpowers/specs/ONIX_PRODUCTION_SPEC.md`); portability is a design constraint.
- **Voice contract enforcement.** All agentic outputs, reports, and pull request summaries must adhere to the Klarix Voice Contract (zero AI filler words, high signal-to-noise ratio).
- **Zero external RAG / Neon DB.** Vector search and graph memory are strictly native Memgraph (768-dim vector index) + Postgres (`meeting_memory`). Zero third-party external cloud database dependencies.
- v5 (`~/Desktop/airbyte-lm-studio-memgraph`) and v3 (`shubham-gaur-x/airbyte-meeting`) are
  read-only reference. Never modify either.

## Before you start

Phase 0.5 (the OAuth spike) gates every other phase. Do not build infrastructure or connectors
until a real Workspace token has been held in hand — see `docs/GOOGLE_AUTH.md`. For the Onix enterprise production roadmap, refer to `docs/superpowers/specs/ONIX_PRODUCTION_SPEC.md`.

