# meeting-notes-gcp

> Meeting memory pipeline — v6. GCP-native. Cloud Run + Cloud SQL + Vertex AI + Memgraph.

**Status: Phases 0–8 and 11 built and running.** 665 tests, no live credentials required.
Phase 9 (hardening) and Phase 10 (Onix migration) remain — see
[`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md).

Validated end to end on a real corpus: 144 staged records → 96 meetings, 263 facts (all
embedded), 67 people across 6 organisations, plus PageRank, community detection and quality
scores from the nightly pass. The dev agent has taken a Jira ticket through to an open pull
request without a human touching the keyboard.

## What this is

Meeting content from a Google Workspace account — Gmail, Calendar, Meet transcripts — plus Jira
is ingested by our own connectors, extracted into structured form by an LLM, and stored as a
property graph. The graph then does more than store: it computes influence, remembers durable
facts, decays stale context, recognises recurring meeting workflows, answers natural-language
questions, and semantically searches its own history.

Engineering work it finds gets filed to Jira, and an autonomous agent picks those tickets up,
implements them in an isolated worktree, and opens a pull request against the repository the
ticket names — behind seven deterministic gates and an independent reviewer. It never merges;
that stays human.

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
   │
   ▼
Cloud Run Job               dev agent: Jira ticket → worktree → gates → PR
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
| [`docs/SETUP.md`](docs/SETUP.md) | Runbook for all three tiers |
| [`docs/KNOWLEDGE_TRANSFER.html`](docs/KNOWLEDGE_TRANSFER.html) | Onboarding reference — architecture, file-by-file module map, built vs pending. Open in a browser |
| [`docs/meeting-notes-gcp-KT.pptx`](docs/meeting-notes-gcp-KT.pptx) | 16-slide handover deck, speaker notes included. Regenerate with `npm i pptxgenjs && node docs/kt-deck.js` |

## Getting started

```bash
git clone <this repo> && cd meeting-notes-gcp
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env
make doctor
```

`make doctor` tells you exactly what is missing and how to fix it. Full runbook:
**[`docs/SETUP.md`](docs/SETUP.md)**.

Three tiers, each additive, each honest about what it proves:

| Tier | Command | Credentials | Proves |
|---|---|---|---|
| 0 | `make demo` | none | pipeline, graph, memory layers, API, dashboard |
| 1 | `make demo LLM=gemini` | one free API key | genuine LLM extraction |
| 2 | `make sync-up` … `make sync-down` | GCP + Workspace + Jira | the deployed product |

Tier 0 runs entirely on local Docker with replayed LLM fixtures, so a fresh clone
works offline with no account anywhere. Tiers 0 and 1 cost nothing. Tier 2 splits
its resources into a durable tier that costs cents a month and a billable tier
that exists **only while you are syncing** — `make sync-up` creates it and
restores your data, `make sync-down` backs it up and destroys it. Idle cost
between sessions is $0. A budget alert ships from the first apply either way.

One step is genuinely manual and always will be: Google exposes no API for
creating an OAuth consent screen or Desktop client, so tier 2 needs a one-time
console visit. `docs/GOOGLE_AUTH.md` §5 walks through it, and `make doctor TIER=2`
tells you if it is outstanding.

## The dashboard

`make demo` brings up the stack; the dashboard is at **http://localhost:8080/dashboard**.
To run just the API against an already-running stack:

```bash
.venv/bin/python -m uvicorn api.main:app --port 8080
```

Seven tabs, each answering a question someone actually asks:

| Tab | Answers |
|---|---|
| Overview | What happened? Counters over a selectable window, latest decisions, open commitments |
| Meetings | What was decided, who was there, what came out of it — click any row |
| Action Items | What do I owe? Filterable by owner, with Jira links |
| Workstreams | What is this project made of? Clusters the graph found, named by their topics |
| Graph | The graph itself — force-directed, filterable, hover for names |
| Ask | Anything else, in natural language, answered from the graph |
| Needs You | What the system chose to ask about rather than guess |

Interactive API docs are at `/docs`.

**Naming people is opt-in.** Per-person analytics — PageRank, centrality, community
membership, the graph view — filter on `Person.tracked`, which only the roster file can set.
Aggregates are the default, so "Most connected people" reads as empty until someone opts in.
That is the governance gate working, not a bug.

## Stack

| Component | Choice |
|---|---|
| Ingestion | Cloud Run Jobs, our own connectors |
| Scheduling | Cloud Scheduler |
| Staging | Cloud SQL PostgreSQL 15 |
| LLM (chat + embeddings) | Vertex AI Gemini |
| Graph | Memgraph + MAGE on GCE, GKE later |
| Graph MCP | Memgraph MCP server |
| Ticketing | Jira, bidirectional |
| API | FastAPI on Cloud Run, scales to zero |
| IaC | Terraform |
| Secrets | Secret Manager |
| Dev agent | Gemini CLI, headless, on Vertex (ADR-021) |

## Deployment context

Personal GCP project now, Onix GCP project later. Data comes from the Onix Workspace account in
both cases. Portability is a design constraint: everything in Terraform, no hardcoded project
IDs, all secrets in Secret Manager. See [ADR-009](docs/DECISIONS.md).

## Related

- v5 (local): `~/Desktop/airbyte-lm-studio-memgraph` — reference only, **do not modify**
- v3 (cloud): `shubham-gaur-x/airbyte-meeting` — **do not modify**
