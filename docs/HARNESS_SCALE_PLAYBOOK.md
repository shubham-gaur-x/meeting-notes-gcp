# Production Scaling Playbook & Scientific Evidence Guidelines

> _Distilled from Agent Harness architecture, high-throughput pipeline engineering, and empirical data pipeline research._

---

## 1. Architectural Tenets & Internal Scale Ideology

1. **Transactional Isolation & Head-of-Line Blocking Prevention**:
   - Staged records are claimed using `FOR UPDATE SKIP LOCKED`, allowing horizontally autoscaling drain workers without lock serialization.
   - Corrupted or unprocessable records ("poison pills") are isolated to `dead_letter` status after **3 failed attempts**, preventing queue stall and unbounded compute burn.

2. **Bounded Concurrency (`asyncio.gather` + `Semaphore`)**:
   - Never iterate sequentially when processing independent database records or graph updates.
   - Bounded concurrent operations (defaulting to `settings.graph_write_concurrency = 3`) deliver a **3x throughput boost** without saturating Memgraph or Cloud SQL connection pools.

3. **Batched Vectorization with Bounded Concurrency**:
   - Embeddings are chunked into batches of up to **50 items per network request** across Vertex AI and Gemini clients.
   - Bounded by the PR #2 shared concurrency ceiling, batching drastically amortizes HTTP/TLS handshake and API connection overhead with a >90% reduction in network round trips without saturating provider quotas.

4. **Multi-Tracker Autonomous Dev Agent Support**:
   - Seamlessly searches and transitions tasks across both Jira and Linear trackers.
   - Enforces the strict 7-gate verification pipeline (Branch creation -> Diff generation -> Ruff lint -> Mypy typecheck -> Pytest verification -> Git commit -> Pull Request creation).

---

## 2. Scientific Evidence & Research Isolation Policy

- **Ideological Adoption Only**: Advanced scientific research (e.g. retrieval benchmark papers, RAG routing, semantic graph topologies) is evaluated conceptually to build lightweight, zero-dependency algorithms into our core codebase.
- **Strict Dependency Quarantine**: Heavy external research databases (such as Neon DB, Doppler vector stores) are **strictly prohibited** from deployment in `meeting-notes-gcp`. Neon DB remains exclusively on the user's private local environment.
- Only markdown documentation, instructions, skills, and configuration specifications are committed to this repository.
