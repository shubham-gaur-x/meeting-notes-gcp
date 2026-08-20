# Phase 4 LLM Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One protocol, four backends, and an extractor that keeps v5's tuned prompt verbatim — so tier 0 runs offline on replayed fixtures and tier 1 runs real extraction on a free API key.

**Architecture:** `llm_client.py` is the only module that constructs an LLM client. It exposes exactly two coroutines — `chat_json()` and `embed()` — and selects a backend from configuration. `extractor.py` calls that seam and owns only schema-shaped concerns: the system prompt, null-like field repair, and validation into `ExtractedMeeting`.

**Tech Stack:** Python 3.11+ · `httpx` · `openai` (LM Studio's OpenAI-compatible API only) · `google-cloud-aiplatform` · `pytest`

## Global Constraints

Copied verbatim from `CLAUDE.md` and ADR-014.

- **DO NOT instantiate an LLM client outside `meeting_notes/llm_client.py`.** Every caller — extractor, memory modules, retrieval — goes through it.
- **Temperature is 0.0 for extraction. Always.**
- **Embeddings are 768-dimensional in every backend**, `fake` included, because both Memgraph vector indexes are configured for 768.
- **A `fake` fixture miss raises.** Never `None`, never a default, never an empty extraction.
- **DO NOT use synchronous `requests`** — always `httpx.AsyncClient`.
- DO NOT read `os.environ` outside `config.py`.
- `@with_retry(max_attempts=3, base_delay=2.0)` on every external call.
- Keep v5's `_SYSTEM_PROMPT` **verbatim** — it is tuned.
- Keep `_is_null_like` and `_loads_lenient` **exactly as they are** — both were found by live testing, not unit tests.
- Type hints on all signatures; tests run with no live GCP, no database, no LLM.
- One test file for the phase: `tests/test_phase04_llm_seam.py`.

---

## Where v5's parsing helpers land, and why they move

`PHASE_PLAN` says to keep `_is_null_like` and `_loads_lenient` exactly as they are. Their
*content* is unchanged. One of them changes **file**, and that follows directly from the
protocol `CLAUDE.md` mandates:

```python
async def chat_json(system: str, user: str, *, temperature: float = 0.0) -> dict | None
```

`chat_json` returns a **dict**, so getting from raw model text to a dict is the seam's job:

| Helper | Lives in | Why |
|---|---|---|
| `strip_json_fences` | `utils.py` (already ported) | Local models wrap JSON in ```` ```json ```` fences despite instructions |
| `_loads_lenient` | **`llm_client.py`** | "Turn model output into a dict" is precisely what `chat_json` promises |
| `_is_null_like` | **`extractor.py`** | Repairs fields against *our* schema — meaningless to a generic JSON call |

This is a file move, not a rewrite. Both function bodies are carried across unchanged.

---

## File Structure

| File | Responsibility |
|---|---|
| `meeting_notes/llm_client.py` | The ONLY module constructing an LLM client. Four backends, two coroutines. |
| `meeting_notes/extractor.py` | v5's prompt verbatim + null-like repair + validation. |
| `scripts/record_fixtures.py` | Regenerate `fake` fixtures against a real backend (ADR-014). |
| `sample_data/llm_fixtures/` | Recorded responses, committed. |
| `tests/test_phase04_llm_seam.py` | One test file for the phase. |

---

### Task 1: The protocol and the `fake` backend

**Files:**
- Create: `meeting_notes/llm_client.py`
- Test: `tests/test_phase04_llm_seam.py`

**Interfaces:**
- Produces: `chat_json(system, user, *, temperature=0.0)`, `embed(text)`, `fixture_key(system, user, temperature)`, `FixtureMiss`, `_loads_lenient(text)`, `select_backend(settings)`

`fake` is built first because it is the tier-0 default and the suite's mock — everything
later in the phase is tested through it.

Fixture key is a SHA-256 over `system + user + temperature`, so a prompt edit changes the key
and produces a **loud** miss rather than a stale replay.

- [ ] **Step 1: Write the failing tests**

```python
def test_fixture_key_is_stable_for_identical_input() -> None:
    assert fixture_key("s", "u", 0.0) == fixture_key("s", "u", 0.0)


def test_fixture_key_changes_when_the_prompt_changes() -> None:
    """ADR-014: a prompt edit must invalidate the fixture, not replay a stale one."""
    assert fixture_key("s", "u", 0.0) != fixture_key("s EDITED", "u", 0.0)


def test_fixture_key_changes_with_temperature() -> None:
    assert fixture_key("s", "u", 0.0) != fixture_key("s", "u", 0.7)


async def test_a_fixture_miss_raises_rather_than_returning_none() -> None:
    """The single most important test in this file. ADR-014: a silently-wrong
    extraction is the worst outcome available, so a miss is loud."""
    with pytest.raises(FixtureMiss) as exc:
        await chat_json("unrecorded", "prompt", settings=fake_settings(tmp_path))
    assert "record_fixtures" in str(exc.value), "the error must say how to fix it"


async def test_fake_embed_returns_the_configured_dimension() -> None:
    """768 in EVERY backend, fake included — the vector indexes are built for it."""
    vector = await embed("anything", settings=fake_settings(tmp_path))
    assert len(vector) == 768


async def test_fake_embeddings_are_deterministic_but_differ_by_text() -> None:
    """Semantic search tests need stable vectors that still discriminate."""
    a1 = await embed("alpha", settings=...)
    a2 = await embed("alpha", settings=...)
    b = await embed("beta", settings=...)
    assert a1 == a2
    assert a1 != b
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError`
- [ ] **Step 3: Implement** the protocol, `select_backend`, and the `fake` backend.
- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit**

---

### Task 2: Lenient parsing and retry semantics

**Files:**
- Modify: `meeting_notes/llm_client.py`
- Test: `tests/test_phase04_llm_seam.py`

The retry policy is an explicit exit criterion and is easy to get backwards.

- [ ] **Step 1: Write the failing tests**

```python
def test_parses_a_clean_json_object() -> None:
    assert _loads_lenient('{"a": 1}') == {"a": 1}


def test_salvages_json_wrapped_in_prose() -> None:
    """Observed live: models narrate around the object despite instructions."""
    assert _loads_lenient('Sure! Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}


def test_strips_markdown_fences() -> None:
    """Local models wrap JSON in ```json fences despite being told not to."""
    assert _loads_lenient('```json\n{"a": 1}\n```') == {"a": 1}


def test_returns_none_when_nothing_parses() -> None:
    assert _loads_lenient("no json here at all") is None


def test_a_bare_array_is_not_accepted_as_an_object() -> None:
    assert _loads_lenient("[1, 2, 3]") is None


async def test_transport_errors_retry() -> None:
    """A timeout or 5xx is transient — retry it."""
    calls = []
    ...
    assert len(calls) == 3


async def test_parse_failures_do_NOT_retry() -> None:
    """At temperature 0 an identical retry yields identical output, so retrying
    a parse failure just burns quota to fail the same way."""
    calls = []
    result = await chat_json(..., transport=returns_garbage(calls))
    assert result is None
    assert len(calls) == 1, "a parse failure must not be retried"
```

- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 3: `gemini`, `lmstudio` and `vertex` backends

**Files:**
- Modify: `meeting_notes/llm_client.py`
- Test: `tests/test_phase04_llm_seam.py`

All three are exercised through an injected transport, so the suite still needs no network.

**Model names are env vars, never literals** (`PHASE_PLAN` task 3). The defaults in
`.env.example` are a starting point to confirm at build time, not a guarantee.

- [ ] **Step 1: Write the failing tests** — backend selection is env-driven; each backend
  posts to the right endpoint with temperature 0.0; `gemini` and `vertex` read their model
  from settings rather than a literal; every backend's `embed` returns 768.
- [ ] **Step 2-5:** run-fail → implement → run-pass → commit.

---

### Task 4: `extractor.py`

**Files:**
- Create: `meeting_notes/extractor.py`
- Test: `tests/test_phase04_llm_seam.py`

Port from v5. The prompt is copied **byte for byte**; `_is_null_like` is copied unchanged. The
only structural change is that it calls `llm_client.chat_json` instead of building an
`openai.AsyncOpenAI` itself.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_system_prompt_is_v5s_verbatim() -> None:
    """It is tuned. Diffing it against v5's file is the point of this test."""
    v5 = Path.home() / "Desktop/airbyte-lm-studio-memgraph/transform_service/extractor.py"
    if not v5.exists():
        pytest.skip("v5 reference repo not present")
    assert _extract_prompt_literal(v5.read_text()) == _SYSTEM_PROMPT


def test_literal_string_null_is_treated_as_null() -> None:
    """MIGRATION_FROM_V5.md #4 — gemma3-12b emits the literal string "null"
    for optional fields. A plain `if not value` misses it: "null" is truthy."""
    for value in (None, "", "null", "NULL", " none ", "n/a"):
        assert _is_null_like(value) is True
    for value in ("meeting", 0, False, []):
        assert _is_null_like(value) in (False, True)  # only strings/None are null-like
    assert _is_null_like("meeting") is False


async def test_a_null_string_platform_is_replaced_from_context() -> None:
    """The exact live failure: platform came back as "null" and validation blew up."""
    meeting = await extract_meeting(..., context={"platform": "Google Meet"})
    assert meeting.platform == "Google Meet"


async def test_action_items_with_null_owner_are_repaired_not_dropped() -> None:
    meeting = await extract_meeting(...)
    assert meeting.action_items[0].owner == "Unknown"


async def test_type_hint_is_appended_to_the_system_prompt() -> None:
    """meeting_type_router's hint must actually reach the model."""
    ...


async def test_a_parse_failure_returns_none_rather_than_raising() -> None:
    ...
```

- [ ] **Step 2-5:** run-fail → port → run-pass → commit.

---

### Task 5: `scripts/record_fixtures.py` and the corpus

**Files:**
- Create: `scripts/record_fixtures.py`, `sample_data/llm_fixtures/`

ADR-014 promises a deliberate prompt change is "one command rather than hand-authored JSON".

- [ ] **Step 1: Implement the recorder** — runs a real backend over `sample_data/meetings/`
  and writes one fixture per prompt, keyed identically to `fixture_key`.
- [ ] **Step 2: Record fixtures** against whichever real backend has credentials.
- [ ] **Step 3: Verify tier 0 replays them** — `LLM_BACKEND=fake` produces a valid
  `ExtractedMeeting` with no network.
- [ ] **Step 4: Commit** the fixtures.

**Blocked without a credential.** No `GEMINI_API_KEY` is configured and `LLM_BACKEND` is
unset, so there is currently no real backend to record *from*. Tasks 1-4 are fully testable
without one; this task and the two live exit criteria below are not. Get a free key at
https://aistudio.google.com/apikey — no GCP project, no billing.

---

### Task 6: Live verification and model-name confirmation

These need credentials and are explicitly deferred until one exists, rather than quietly
skipped.

- [ ] **Confirm the current Vertex and Gemini model names** against the live API. `PHASE_PLAN`
  task 3 says do not assume — they change. `.env.example` currently suggests
  `gemini-2.5-flash` and `text-embedding-005`.
- [ ] **Verify `text-embedding-005` really returns 768 dimensions** against the live API
  before relying on it (`PHASE_PLAN` task 4). If it does not, both vector indexes and
  `embedding_dimension` must change together.
- [ ] **Both backends produce a valid `ExtractedMeeting` from the same fixture input.**
- [ ] Mark Phase 4 done in `docs/PHASE_PLAN.md` and run `graphify . --update`.

---

## Self-review notes

- **Phase plan coverage:** task 1 → Tasks 1-3, task 2 → Task 4, tasks 3 and 4 → Task 6.
  Exit criteria: fixture-input equivalence → Task 6; env-driven selection → Task 3; retry
  semantics → Task 2; the literal-`"null"` bug → Task 4.
- **The helper move is justified, not incidental** — it falls out of the `chat_json -> dict`
  signature `CLAUDE.md` mandates, and both bodies carry across unchanged.
- **The credential gap is stated, not hidden.** Tasks 1-4 deliver a fully tested seam offline;
  Tasks 5-6 are honestly blocked on a free API key.
