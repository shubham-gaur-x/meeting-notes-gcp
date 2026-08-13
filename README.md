# meeting-notes-gcp

> Meeting memory pipeline — v6. GCP-native. Cloud Run + Cloud SQL + Vertex AI + Memgraph.

**Status: Phase 0 — documentation complete, implementation not started.**
Start at [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md).

## What this is

Meeting content from a Google Workspace account — Gmail, Calendar, Meet transcripts — plus Jira
is ingested by our own connectors, extracted into structured form by an LLM, and stored as a
property graph. The graph then does more than store: it computes influence, remembers durable
facts, decays stale context, recognises recurring meeting workflows, answers natural-language
questions, and semantically searches its own history.

This is a GCP-native rebuild of [`airbyte-lm-studio-memgraph`](../airbyte-lm-studio-memgraph)
(v5), which ran entirely on a laptop via Docker Compose. Two things change fundamentally:
**Airbyte is replaced by our own Cloud Run Job connectors**, and **in-process scheduling is
replaced by Cloud Scheduler**. The open-source core — Memgraph + MAGE, FastAPI, the extraction
prompts, the Cypher, the test suite — is carried across deliberately rather than rewritten.

## Architecture

```
Gmail · Calendar · Meet · Jira
   │  Cloud Run Jobs (our connectors)  ← no Airbyte
   ▼
Cloud SQL Postgres          staging, processed flag, SKIP LOCKED claiming
   │  Cloud Run Job, every 5 min
   ▼
classify → route → extract (Vertex AI Gemini) → resolve → dedup
   │
   ▼
Memgraph + MAGE             one ACID transaction per meeting
   │                        + algorithms, 4 memory layers, vector search
   │                        + MCP server for Claude Desktop
   ▼
Cloud Run Service           FastAPI query layer + dashboard, scales to zero
```

Full detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Documentation

| File | What it's for |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | **Authoritative.** Rules, module boundaries, graph schema, conventions. Read first. |
| [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md) | The build order. Execute in sequence. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Target architecture, GCP resources, and the reasoning behind both |
| [`docs/MIGRATION_FROM_V5.md`](docs/MIGRATION_FROM_V5.md) | Module-by-module port map, plus ten bugs that must not be reintroduced |
| [`docs/GOOGLE_AUTH.md`](docs/GOOGLE_AUTH.md) | OAuth setup, the 7-day token problem, the Onix migration path |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | ADR log. Append, never rewrite. |

## Getting started

```bash
# 1. Phase 0.5 — the auth spike. Nothing else works until this does.
cp .env.example .env      # fill in yourself, never commit
python scripts/auth_spike.py

# 2. Phase 1 — infrastructure
make tf-plan ENV=personal
make tf-apply ENV=personal

# 3. Onward — follow docs/PHASE_PLAN.md
```

**Phase 0.5 gates everything.** If the Onix Workspace admin blocks unverified third-party apps,
the ingestion design changes and anything built beforehand is wasted work.

## Stack

| Component | Choice |
|---|---|
| Ingestion | Cloud Run Jobs, our own connectors |
| Scheduling | Cloud Scheduler |
| Staging | Cloud SQL PostgreSQL 15 |
| LLM (chat + embeddings) | Vertex AI Gemini · LM Studio for local dev |
| Graph | Memgraph + MAGE on GCE, GKE later |
| Graph MCP | Memgraph MCP server |
| Ticketing | Jira, bidirectional |
| API | FastAPI on Cloud Run, scales to zero |
| IaC | Terraform |
| Secrets | Secret Manager |

## Deployment context

Personal GCP project now, Onix GCP project later. Data comes from the Onix Workspace account in
both cases. Portability is a design constraint: everything in Terraform, no hardcoded project
IDs, all secrets in Secret Manager. See [ADR-009](docs/DECISIONS.md).

## Related

- v5 (local): `~/Desktop/airbyte-lm-studio-memgraph` — reference only, **do not modify**
- v3 (cloud): `shubham-gaur-x/airbyte-meeting` — **do not modify**
