# Phase 2 Pure Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port every module with no I/O from v5 into `meeting_notes/`, introduce `config.py` as the single environment reader, and land the `StagedRecord` shape — so the suite is green and the data model is settled before `db.py` or any connector exists.

**Architecture:** Nine modules, all pure functions and Pydantic models. `config.py` is new and is the only thing in the package that touches `os.environ`; the two v5 modules that read env directly (`person_resolver`, `access_control`) are refactored to take their configuration as a parameter, which also makes them trivially testable. `models.py` gains `StagedRecord` (ADR-018) and loses `AirbyteWebhookPayload`. Everything else ports close to unchanged — the value here is a green suite and a settled data model, not new design.

**Tech Stack:** Python 3.11+ · Pydantic v2 · `pydantic-settings` · `structlog` · `pytest`

## Global Constraints

Copied verbatim from `CLAUDE.md`.

- Python 3.11+, type hints on **all** function signatures (`mypy --disallow-untyped-defs`).
- Pydantic v2, `model_config = ConfigDict(extra="ignore")`.
- `ruff` line-length **110**, target `py311`.
- **DO NOT read `os.environ` outside `meeting_notes/config.py`.** Everything else imports settings.
- Structured logging with `structlog`. **Never pass `event=` as a kwarg** — it collides with structlog's reserved message field and raises `TypeError` at call time. Use `github_event=`, `source_event=`.
- `uuid5_id(namespace, value)` for every deterministic id. Re-derive identically everywhere.
- Tests are mocked — the suite must run with no live GCP, no database, no LLM. A test requiring live credentials is a broken test.
- One test file per phase, named for what it proves: `tests/test_phase02_pure_core.py`.
- DO NOT write to the v5 repo (`~/Desktop/airbyte-lm-studio-memgraph`). It is read-only reference.

## Scope note

This phase is **pure core only** — no I/O, no network, no database. `db.py`, `graph_client.py`,
and `llm_client.py` are Phases 3 and 4 and are not built here, even though `config.py` defines
the settings they will read.

`meeting_quality.py` is included because its scoring functions are pure, but note that v5's
`compute_quality` and `top_and_bottom` take already-fetched data — they do no I/O themselves.
Port them as pure functions; whatever fetches their input lands in Phase 7.

### On the exit criterion "config.py is the only module referencing os.environ"

`scripts/auth_spike.py`, `scripts/doctor.py`, and `scripts/sync.py` all read `os.environ`. They
predate `config.py` and each carries a documented exception in its module docstring: they are
standalone operational tools that must run on a clone with no package installed and no `.env`.
**That exception stands.** The exit criterion is scoped to the `meeting_notes/` package, and
Task 10 verifies it there. Migrating the scripts would add risk and coupling for no benefit —
`doctor.py` in particular must work when configuration is broken, which is exactly when a
typed settings object would refuse to construct.

---

## File Structure

| File | Responsibility |
|---|---|
| `meeting_notes/config.py` | Typed settings. The ONLY `os.environ` reader in the package. |
| `meeting_notes/models.py` | Pydantic models: extraction shapes + `StagedRecord` (ADR-018). |
| `meeting_notes/utils.py` | `uuid5_id`, `with_retry`, logging, JSON fence stripping, ticket keys. |
| `meeting_notes/classifier.py` | Rules-based "is this worth processing" score. No LLM. |
| `meeting_notes/meeting_type_router.py` | Picks a meeting type and its extraction prompt hint. |
| `meeting_notes/person_resolver.py` | Canonical person resolution. Roster now injected. |
| `meeting_notes/dedup.py` | Cosine similarity and best-match for action-item dedup. |
| `meeting_notes/meeting_quality.py` | Pure scoring functions for meeting quality. |
| `meeting_notes/access_control.py` | Scope/role authorization. Policy now injected. |
| `tests/test_phase02_pure_core.py` | One test file for the phase, per `CLAUDE.md`. |
| `Makefile` | Modify: `lint`/`typecheck` must now include `meeting_notes`. |

v5 source of truth for every port: `~/Desktop/airbyte-lm-studio-memgraph/transform_service/`.

---

### Task 1: `config.py` — typed settings

Everything else imports this, so it lands first. It is also the module the exit criterion
names explicitly.

**Files:**
- Create: `meeting_notes/config.py`
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings `BaseSettings`), `get_settings() -> Settings`

- [ ] **Step 1: Write the failing tests**

```python
"""Phase 2 — the pure core. No I/O, no network, no database.

Every test here runs with no GCP, no Postgres, no Memgraph and no LLM.
"""

from __future__ import annotations

import pytest

from meeting_notes.config import Settings


def test_settings_read_from_an_explicit_mapping_not_the_process_env() -> None:
    """Settings must be constructible from an explicit dict so tests never
    depend on the ambient environment."""
    s = Settings(GCP_PROJECT_ID="proj", LLM_BACKEND="fake")
    assert s.gcp_project_id == "proj"
    assert s.llm_backend == "fake"


def test_settings_default_to_the_tier_zero_backend() -> None:
    """A clone with no .env at all must default to the offline backend —
    that is what makes `make demo` work with no credentials (ADR-014)."""
    assert Settings().llm_backend == "fake"


def test_settings_reject_an_unknown_llm_backend() -> None:
    with pytest.raises(ValueError):
        Settings(LLM_BACKEND="not-a-backend")


def test_embedding_dimension_is_768() -> None:
    """Both Memgraph vector indexes are built for 768. Changing this without
    migrating them silently breaks semantic search (CLAUDE.md)."""
    assert Settings().embedding_dimension == 768


def test_jira_is_disabled_by_default() -> None:
    """Tier 0 and tier 1 must run the pipeline fully and create no tickets."""
    assert Settings().jira_enabled is False


def test_cloud_sql_connection_name_blank_means_local() -> None:
    """ADR-015: db.py branches on this to pick its connection mode."""
    assert Settings().cloud_sql_connection_name == ""
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_phase02_pure_core.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'meeting_notes.config'`

- [ ] **Step 3: Implement**

Create `meeting_notes/config.py`:

```python
"""Typed settings — the ONLY module in this package that reads os.environ.

Every other module imports `get_settings()` rather than reaching for the
environment itself (CLAUDE.md). That rule is what makes the rest of the
package testable without a .env file: a test constructs `Settings(...)`
with explicit values and never touches the process environment.

Deployed environments get these from Secret Manager, injected by Cloud Run.
Locally they come from .env. Either way this is the single seam.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMBackend = Literal["fake", "gemini", "lmstudio", "vertex"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── GCP ──────────────────────────────────────────────────────────────
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"
    gcp_zone: str = "us-central1-a"

    # ─── LLM (ADR-002, ADR-014) ───────────────────────────────────────────
    # `fake` replays recorded fixtures: no credentials, no network. It is the
    # tier-0 default and the test suite's backend.
    llm_backend: LLMBackend = "fake"
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    vertex_chat_model: str = ""
    vertex_embedding_model: str = "text-embedding-005"
    vertex_location: str = "us-central1"
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = ""
    lm_studio_embedding_model: str = "text-embedding-nomic-embed-text-v1.5"

    # Both Memgraph vector indexes are configured for 768. Changing this means
    # migrating both indexes, so it is not a knob to turn casually.
    embedding_dimension: int = 768

    # ─── Postgres (ADR-015) ───────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "meeting_memory"
    postgres_user: str = "meeting_notes"
    postgres_password: str = ""
    # Blank means local Postgres; set means the Cloud SQL connector.
    cloud_sql_connection_name: str = ""

    # ─── Memgraph ─────────────────────────────────────────────────────────
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    memgraph_user: str = ""
    memgraph_password: str = ""

    # ─── Google Workspace OAuth ───────────────────────────────────────────
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_refresh_token: str = ""
    google_workspace_user: str = ""
    meet_pubsub_subscription: str = ""

    # ─── Jira ─────────────────────────────────────────────────────────────
    # False by default so tiers 0 and 1 run the pipeline fully and write no
    # tickets to a real Jira.
    jira_enabled: bool = False
    jira_domain: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "SCRUM"
    jira_board_id: int = 1
    jira_issue_type: str = "Task"
    jira_confidence_threshold: float = 0.6
    jira_dedup_enabled: bool = True
    jira_dedup_threshold: float = 0.9

    # ─── Governance ───────────────────────────────────────────────────────
    fact_min_confidence: float = 0.5
    person_roster_path: str = ""
    access_policy_file: str = ""

    # ─── Pipeline tuning ──────────────────────────────────────────────────
    classifier_score_threshold: float = 0.40
    pipeline_batch_size: int = 50
    graph_write_concurrency: int = 3

    # ─── Service ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    github_webhook_secret: str = ""
    api_url: str = ""
    gcs_backup_bucket: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached so the .env file is read once.

    Tests should construct `Settings(...)` directly rather than calling this,
    so they never depend on the ambient environment or the cache.
    """
    return Settings()
```

- [ ] **Step 4: Run to verify pass**

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add meeting_notes/config.py tests/test_phase02_pure_core.py
git commit -m "Phase 2: typed settings, the only os.environ reader in the package"
```

---

### Task 2: `utils.py`

No dependencies, and everything else uses `uuid5_id`. Ports essentially unchanged.

**Files:**
- Create: `meeting_notes/utils.py` (port of `transform_service/utils.py`, 104 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `uuid5_id(namespace: str, value: str) -> str`, `extract_ticket_keys(text: str | None) -> list[str]`, `strip_json_fences(raw: str) -> str`, `configure_logging() -> structlog.BoundLogger`, `with_retry(max_attempts: int = 3, base_delay: float = 2.0)`, `priority_from_due(due: date | None) -> str`

**Port deltas from v5:** modernise typing (`List` → `list`, `Optional[X]` → `X | None`) and add
return-type hints where v5 omitted them. Behaviour is unchanged — `uuid5_id` in particular must
produce **byte-identical** ids to v5, because a changed id silently forks every MERGE.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date, timedelta

from meeting_notes.utils import (
    extract_ticket_keys,
    priority_from_due,
    strip_json_fences,
    uuid5_id,
)


def test_uuid5_id_is_deterministic() -> None:
    """The whole MERGE-not-CREATE strategy rests on this. Same input, same id,
    forever — including across processes and machines."""
    assert uuid5_id("meeting", "abc") == uuid5_id("meeting", "abc")


def test_uuid5_id_separates_namespaces() -> None:
    assert uuid5_id("meeting", "abc") != uuid5_id("person", "abc")


def test_uuid5_id_matches_the_value_v5_produces() -> None:
    """Pinned against v5's output. If this changes, every id in a restored
    graph forks and MERGE starts creating duplicates instead of matching."""
    import uuid

    expected = str(uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), "meeting:abc"))
    assert uuid5_id("meeting", "abc") == expected


def test_strip_json_fences_removes_a_fenced_block() -> None:
    """Local models wrap JSON in ```json fences despite being told not to.
    Found by live testing in v5, not by unit tests (CLAUDE.md)."""
    assert strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_json_fences_leaves_bare_json_alone() -> None:
    assert strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_extract_ticket_keys_finds_jira_style_keys() -> None:
    assert extract_ticket_keys("fixes SCRUM-12 and PROJ-3") == ["SCRUM-12", "PROJ-3"]


def test_extract_ticket_keys_on_none_is_empty() -> None:
    assert extract_ticket_keys(None) == []


def test_priority_from_due_escalates_as_the_date_approaches() -> None:
    soon = date.today() + timedelta(days=1)
    far = date.today() + timedelta(days=60)
    assert priority_from_due(soon) == "high"
    assert priority_from_due(far) == "low"
    assert priority_from_due(None) == "medium"
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: No module named 'meeting_notes.utils'`

- [ ] **Step 3: Implement**

Copy `~/Desktop/airbyte-lm-studio-memgraph/transform_service/utils.py` to
`meeting_notes/utils.py`, then apply the port deltas above. Keep `_NAMESPACE` and the
`uuid5_id` body **byte-identical** — the pinned test above exists to catch any drift.

Confirm `priority_from_due`'s thresholds against v5 lines 96-104 rather than assuming; adjust
the test's `soon`/`far` values to match v5's actual boundaries if they differ.

- [ ] **Step 4: Run to verify pass**

- [ ] **Step 5: Commit**

```bash
git add meeting_notes/utils.py tests/test_phase02_pure_core.py
git commit -m "Phase 2: port utils, with uuid5_id pinned against v5's output"
```

---

### Task 3: `models.py` and `StagedRecord`

**Files:**
- Create: `meeting_notes/models.py` (port of `transform_service/models.py`, 137 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `Attendee`, `ActionItem`, `Decision`, `ExtractedMeeting`, `RawEmail`, `RawCalendarEvent`, `RawMeetTranscript`, `RawJiraIssue`, `StagedRecord`, `SourceType`

**Changes from v5:**
1. **Add `StagedRecord`** (ADR-018) — the single staging shape.
2. **Delete `AirbyteWebhookPayload`** — Airbyte residue (`MIGRATION_FROM_V5.md` §4).
3. **Drop the `source_table` field** from the four Raw models. They are no longer tables;
   they are adapter parse targets, and `StagedRecord.source_type` carries the discriminator.
4. Keep `_coerce_decisions` exactly as it is. It exists because LLM output sometimes gives
   `decisions` as a list of plain strings, and it is load-bearing.

- [ ] **Step 1: Write the failing tests**

```python
from meeting_notes.models import (
    ActionItem,
    Decision,
    ExtractedMeeting,
    RawEmail,
    StagedRecord,
)


def test_staged_record_carries_an_opaque_payload() -> None:
    """ADR-018: one table, JSONB payload, source_type as the discriminator."""
    rec = StagedRecord(
        id="1",
        source_id="gmail-abc",
        source_type="email",
        payload={"subject": "hi", "body": "there"},
        fetched_at="2026-08-20T00:00:00Z",
    )
    assert rec.processed is False
    assert rec.payload["subject"] == "hi"


def test_staged_record_rejects_an_unknown_source_type() -> None:
    """A typo'd source must fail loudly here, not silently skip the drain."""
    import pytest

    with pytest.raises(ValueError):
        StagedRecord(
            id="1", source_id="x", source_type="carrier-pigeon",
            payload={}, fetched_at="2026-08-20T00:00:00Z",
        )


def test_raw_models_survive_as_adapter_parse_targets() -> None:
    """ADR-018 is a storage change, not a loss of typing. The typed models
    still validate a payload as strictly as v5 did."""
    email = RawEmail.model_validate(
        {
            "id": "1", "source_id": "abc", "subject": "s", "from_email": "a@b.c",
            "to_emails": ["d@e.f"], "body": "b", "received_at": "2026-08-20T00:00:00Z",
        }
    )
    assert email.subject == "s"


def test_raw_models_no_longer_carry_source_table() -> None:
    """StagedRecord.source_type is the discriminator now. A lingering
    source_table field would be a second source of truth."""
    assert "source_table" not in RawEmail.model_fields


def test_airbyte_webhook_payload_is_gone() -> None:
    """MIGRATION_FROM_V5.md §4 — Airbyte residue must not be ported."""
    import meeting_notes.models as m

    assert not hasattr(m, "AirbyteWebhookPayload")


def test_decisions_accept_plain_strings() -> None:
    """LLM output sometimes gives decisions as bare strings. v5's coercion is
    load-bearing; dropping it would start raising on real extractions."""
    meeting = ExtractedMeeting.model_validate(
        {
            "title": "t", "kind": "meeting", "platform": "meet",
            "date": "2026-08-20", "summary": "s",
            "decisions": ["we shipped it"],
        }
    )
    assert meeting.decisions[0].text == "we shipped it"
    assert meeting.decisions[0].confidence == 1.0


def test_confidence_defaults_do_not_gate_unscored_items() -> None:
    """ActionItem/Decision default to 1.0 so items the model did not score are
    not silently dropped below JIRA_CONFIDENCE_THRESHOLD."""
    assert ActionItem(owner="a", task="t").confidence == 1.0
    assert Decision(text="d").confidence == 1.0


def test_extracted_meeting_ignores_unknown_fields() -> None:
    """CLAUDE.md mandates extra='ignore' — an LLM adding a field must not
    fail the whole extraction."""
    meeting = ExtractedMeeting.model_validate(
        {
            "title": "t", "kind": "meeting", "platform": "meet",
            "date": "2026-08-20", "summary": "s", "invented_field": "???",
        }
    )
    assert not hasattr(meeting, "invented_field")
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement**

Port `transform_service/models.py`, applying changes 1-4 above. The new type and model:

```python
SourceType = Literal["email", "calendar", "meet", "jira"]


class StagedRecord(BaseModel):
    """One staged row from any source (ADR-018).

    `payload` is opaque here on purpose: a per-source adapter parses it into
    the matching typed model above, so validation stays as strict as v5's
    while staging keeps a single table, a single SKIP LOCKED claiming query
    (ADR-006), and a single drain path (ADR-010).
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    source_id: str
    source_type: SourceType
    payload: dict[str, Any]
    fetched_at: str
    processed: bool = False
```

- [ ] **Step 4: Run to verify pass**

- [ ] **Step 5: Commit**

```bash
git add meeting_notes/models.py tests/test_phase02_pure_core.py
git commit -m "Phase 2: models with StagedRecord (ADR-018), Airbyte payload removed"
```

---

### Task 4: `classifier.py` — port, and write the tests v5 never had

**v5 has zero tests for this module.** It is the cheap gate that decides whether the LLM is
called at all, so a bug here either burns inference spend on newsletters or silently drops
real meetings. `PHASE_PLAN.md`'s exit criterion — every ported test passes or has a written
reason for being dropped — is trivially satisfied here because there is nothing to port. That
is precisely why it needs tests written now.

**Files:**
- Create: `meeting_notes/classifier.py` (port of `transform_service/classifier.py`, 96 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `classify(text: str, metadata: dict[str, Any]) -> float`

- [ ] **Step 1: Write the failing tests**

```python
from meeting_notes.classifier import classify


def test_marketing_noise_short_circuits_to_zero() -> None:
    """Two or more noise markers return 0.0 immediately, before any positive
    signal is counted — a newsletter that happens to say 'meeting' and list
    attendees must not score its way past the threshold."""
    text = "Unsubscribe from our newsletter. Marketing meeting agenda, action item, deadline."
    assert classify(text, {"attendees": ["a@b.c"], "start_time": "10:00"}) == 0.0


def test_a_single_noise_marker_does_not_short_circuit() -> None:
    """The gate is >= 2. One stray 'unsubscribe' in a genuine thread is not
    enough to discard it."""
    assert classify("Standup agenda. Unsubscribe link at the bottom.", {}) > 0.0


def test_a_real_meeting_scores_above_the_default_threshold() -> None:
    """CLASSIFIER_SCORE_THRESHOLD defaults to 0.40."""
    text = (
        "Sprint planning meeting agenda. We decided to ship on Friday. "
        "Action item: alice@corp.com to review by the deadline. Duration 60 minutes."
    )
    score = classify(text, {"attendees": ["alice@corp.com", "bob@corp.com"], "start_time": "10:00"})
    assert score > 0.40


def test_unrelated_text_scores_below_the_threshold() -> None:
    assert classify("The parcel was delivered to your porch.", {}) < 0.40


def test_empty_text_scores_zero() -> None:
    assert classify("", {}) == 0.0


def test_score_never_exceeds_one() -> None:
    """Every signal is individually capped and the total is clamped. Without
    the clamp a keyword-dense email could exceed 1.0 and break any caller
    treating this as a probability."""
    text = (
        "meeting call standup sync review demo interview discussion workshop agenda "
        "action item todo deadline owner assigned to next step "
        "we decided we agreed approved going forward we will "
        "10:00 am duration 60 minutes hours "
        "a@b.com c@d.com e@f.com"
    )
    assert classify(text, {"attendees": ["x"], "start_time": "t", "end_time": "u"}) <= 1.0


def test_calendar_metadata_raises_the_score() -> None:
    """Signal 7: a record with real calendar times is more likely a meeting."""
    bare = classify("weekly sync", {})
    with_times = classify("weekly sync", {"start_time": "10:00", "end_time": "11:00"})
    assert with_times > bare


def test_attendees_raise_the_score() -> None:
    """Signal 2 accepts either a list or a count."""
    assert classify("weekly sync", {"attendees": ["a"]}) > classify("weekly sync", {})
    assert classify("weekly sync", {"attendees_count": 3}) > classify("weekly sync", {})
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement**

Copy `transform_service/classifier.py` to `meeting_notes/classifier.py`. Modernise typing
(`Dict[str, Any]` → `dict[str, Any]`) and add the return hint. **Do not retune the weights** —
they were fitted against real v5 data, and this phase is a port. If a test above fails on a
threshold rather than on behaviour, adjust the *test's* wording to match v5's actual scoring,
and note it; do not adjust the module.

- [ ] **Step 4: Run to verify pass**

- [ ] **Step 5: Commit**

```bash
git add meeting_notes/classifier.py tests/test_phase02_pure_core.py
git commit -m "Phase 2: port classifier and give it the tests v5 never had"
```

---

### Task 5: `meeting_type_router.py` — and pin the two vocabularies apart

**Files:**
- Create: `meeting_notes/meeting_type_router.py` (port of the v5 module, 72 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `TYPES: list[str]`, `route(title: str, text: str = "", source_type: str = "") -> str`, `prompt_hint(meeting_type: str) -> str`

**The landmine this task defuses.** `ExtractedMeeting.kind` and `router.TYPES` are two
different vocabularies:

| | values |
|---|---|
| `ExtractedMeeting.kind` | `meeting` · `email_thread` · `call` · `standup` · `review` · `other` |
| `router.TYPES` | `standup` · `planning` · `review` · `one_on_one` · `email_thread` · `general` |

`route()` can return `planning`, `one_on_one`, or `general` — **none of which are valid
`kind` values.** They never meet in v5 (`kind` is what the LLM says the meeting was;
`route()` picks which prompt to extract with), and that separation is correct. But they look
interchangeable, so the first person to write `meeting.kind = route(...)` gets a Pydantic
validation error at runtime. A test pins the distinction so an edit that "helpfully" unifies
them fails loudly at build time instead.

- [ ] **Step 1: Write the failing tests**

```python
from meeting_notes.meeting_type_router import TYPES, prompt_hint, route


def test_email_source_always_routes_to_email_thread() -> None:
    """Source type wins over any keyword in the subject."""
    assert route("sprint planning", source_type="email") == "email_thread"


def test_standup_is_matched_before_the_generic_review_keywords() -> None:
    """Order matters: 'session' lives in review's keywords and would otherwise
    swallow titles that are really standups."""
    assert route("daily standup session") == "standup"


def test_unmatched_titles_fall_back_to_general() -> None:
    assert route("misc") == "general"


def test_every_type_has_a_prompt_hint() -> None:
    """A type with no hint would silently extract with the wrong prompt."""
    for meeting_type in TYPES:
        assert prompt_hint(meeting_type).strip()


def test_prompt_hint_is_safe_for_an_unknown_type() -> None:
    assert isinstance(prompt_hint("not-a-type"), str)


def test_router_types_and_extracted_meeting_kind_are_deliberately_different() -> None:
    """These two vocabularies are NOT interchangeable and must not be merged.

    `ExtractedMeeting.kind` is what the LLM reports the meeting was.
    `route()` picks which extraction prompt to use. route() can return
    'planning', 'one_on_one' or 'general', none of which validate as a kind —
    so `meeting.kind = route(...)` raises. This test exists to make that
    failure appear here rather than in production.
    """
    import typing

    from meeting_notes.models import ExtractedMeeting

    kinds = set(typing.get_args(ExtractedMeeting.model_fields["kind"].annotation))
    router_only = set(TYPES) - kinds

    assert router_only, "the vocabularies have been merged — see this test's docstring"
    assert {"planning", "one_on_one", "general"} <= router_only
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement**

Port the v5 module unchanged apart from typing modernisation. Keep the ordering comment on
the `for mtype in (...)` loop — it documents why `review` is checked last.

- [ ] **Step 4: Run to verify pass**

- [ ] **Step 5: Commit**

```bash
git add meeting_notes/meeting_type_router.py tests/test_phase02_pure_core.py
git commit -m "Phase 2: port the meeting type router, pin its vocabulary apart from kind"
```

---

### Task 6: `dedup.py`

**Files:**
- Create: `meeting_notes/dedup.py` (port of the v5 module, 53 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `cosine(a: list[float], b: list[float]) -> float`, `similarity(new_text: str, new_embedding: list[float] | None, candidate: dict[str, Any]) -> float`, `best_match(...)`

Read v5's `best_match` signature at `transform_service/dedup.py:38` and reproduce it exactly;
`jira_pusher` in Phase 6 calls it.

- [ ] **Step 1: Write the failing tests**

```python
from meeting_notes.dedup import cosine, similarity


def test_cosine_of_identical_vectors_is_one() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_of_orthogonal_vectors_is_zero() -> None:
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_handles_a_zero_vector_without_dividing_by_zero() -> None:
    """An all-zero embedding is what a failed embed() call looks like. It must
    return 0.0, not raise ZeroDivisionError inside the drain."""
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_handles_mismatched_lengths() -> None:
    """A dimension change (768 vs something else) must not crash the pipeline."""
    assert isinstance(cosine([1.0, 0.0], [1.0]), float)


def test_identical_text_is_maximally_similar_without_embeddings() -> None:
    """Dedup must still work when embeddings are unavailable — the text path
    is the fallback, not an optimisation."""
    assert similarity("deploy the api", None, {"text": "deploy the api"}) > 0.9


def test_unrelated_text_is_not_similar() -> None:
    assert similarity("deploy the api", None, {"text": "order more coffee"}) < 0.9
```

- [ ] **Step 2-5:** run-fail → port → run-pass → commit.

---

### Task 7: `person_resolver.py` — roster injected, not read from env

**Files:**
- Create: `meeting_notes/person_resolver.py` (port of the v5 module, 161 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `FUZZY_THRESHOLD`, `normalize_email`, `RosterEntry`, `Resolution`, `Roster`, `load_roster(path: str | None = None) -> Roster`, `resolve(...)`, `resolve_attendees(...)`

**The one real change.** v5's `load_roster()` reads `os.environ["PERSON_ROSTER_PATH"]`
directly at line 93. That violates `CLAUDE.md`'s config rule and makes the function
untestable without monkeypatching the environment. `load_roster` now takes an explicit
`path: str | None`, defaulting to `None` for "no roster". Callers pass
`get_settings().person_roster_path`.

- [ ] **Step 1: Write the failing tests**

```python
from meeting_notes.person_resolver import Roster, normalize_email, resolve


def test_normalize_email_lowercases_and_strips() -> None:
    assert normalize_email("  Alice@Corp.COM ") == "alice@corp.com"


def test_normalize_email_on_none_is_empty() -> None:
    assert normalize_email(None) == ""


def test_email_match_beats_fuzzy_name_match() -> None:
    """Deterministic resolution first, probabilistic second (CLAUDE.md).
    An exact email must never lose to a similar-looking name."""
    roster = Roster.from_entries(
        [
            {"canonical_name": "Alice Smith", "emails": ["alice@corp.com"]},
            {"canonical_name": "Alicia Smyth", "emails": ["alicia@corp.com"]},
        ]
    )
    res = resolve(name="Alicia Smyth", email="alice@corp.com", roster=roster)
    assert res.canonical_name == "Alice Smith"
    assert res.method == "email"


def test_an_unresolvable_attendee_is_flagged_not_dropped() -> None:
    """Attendees are never silently dropped — an unresolved one becomes a
    PersonReview node downstream (CLAUDE.md)."""
    res = resolve(name="Nobody Known", email=None, roster=Roster.from_entries([]))
    assert res.needs_review is True


def test_load_roster_takes_an_explicit_path_not_the_environment() -> None:
    """CLAUDE.md: nothing outside config.py reads os.environ. v5 read
    PERSON_ROSTER_PATH here directly."""
    import inspect

    from meeting_notes import person_resolver

    assert "path" in inspect.signature(person_resolver.load_roster).parameters
    assert "os.environ" not in inspect.getsource(person_resolver)
```

Adjust `Roster.from_entries` / `Resolution` field names to match v5's actual definitions at
`transform_service/person_resolver.py:53-90` — read them before writing, and if v5 has no
`from_entries` constructor, add one rather than making the tests build a `Roster` by hand.

- [ ] **Step 2-5:** run-fail → port with the `load_roster` change → run-pass → commit.

---

### Task 8: `access_control.py` — policy injected, not read from env

**Files:**
- Create: `meeting_notes/access_control.py` (port of the v5 module, 166 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `MEMBER`, `LEAD`, `ADMIN`, `ROLE_ORDER`, `AccessDenied`, `Scope`, `parse_scope`, `Principal`, `load_policy(path: str | None = None)`, `resolve_principal`, `authorize`, `aggregates_only`, `scope_predicate`, `visible_scopes`

**The one real change:** same as Task 7. v5's `load_policy` reads
`os.environ.get("ACCESS_POLICY_FILE")` at line 73; it now takes an explicit path.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from meeting_notes.access_control import (
    ADMIN,
    LEAD,
    MEMBER,
    AccessDenied,
    Principal,
    authorize,
)


def test_a_member_cannot_reach_another_team() -> None:
    policy = {"bob": Principal(name="bob", role=MEMBER, team="platform")}
    with pytest.raises(AccessDenied):
        authorize("bob", "team:payments", policy=policy)


def test_a_member_can_reach_their_own_team() -> None:
    policy = {"bob": Principal(name="bob", role=MEMBER, team="platform")}
    assert authorize("bob", "team:platform", policy=policy)


def test_an_admin_can_reach_everything() -> None:
    policy = {"root": Principal(name="root", role=ADMIN, team="platform")}
    assert authorize("root", "team:payments", policy=policy)


def test_a_lead_gets_aggregates_not_another_teams_detail() -> None:
    """The governance promise: aggregates are the default, naming individuals
    is opt-in (CLAUDE.md, Person.tracked)."""
    from meeting_notes.access_control import aggregates_only

    policy = {"lead": Principal(name="lead", role=LEAD, team="platform")}
    assert aggregates_only("lead", "org:all", policy=policy) is True


def test_load_policy_takes_an_explicit_path_not_the_environment() -> None:
    import inspect

    from meeting_notes import access_control

    assert "path" in inspect.signature(access_control.load_policy).parameters
    assert "os.environ" not in inspect.getsource(access_control)
```

Read v5's `Principal` and `Scope` definitions at `transform_service/access_control.py:32-70`
before writing — construct them in tests exactly as v5 defines them.

- [ ] **Step 2-5:** run-fail → port with the `load_policy` change → run-pass → commit.

---

### Task 9: `meeting_quality.py`

**Files:**
- Create: `meeting_notes/meeting_quality.py` (port of the v5 module, 187 lines)
- Test: `tests/test_phase02_pure_core.py`

**Interfaces:**
- Produces: `percentile_rank`, `score_attendance_ratio`, `score_yield`, `score_action_completion`, `score_agenda_present`, `score_recurrence_health`, `composite_quality`, `compute_quality`, `top_and_bottom`

All pure. `compute_quality` and `top_and_bottom` take already-fetched data and do no I/O
themselves — whatever fetches their input is Phase 7.

- [ ] **Step 1: Write the failing tests**

```python
from meeting_notes.meeting_quality import (
    percentile_rank,
    score_action_completion,
    score_agenda_present,
    score_attendance_ratio,
)


def test_percentile_rank_of_the_maximum_is_one() -> None:
    assert percentile_rank(10.0, [1.0, 5.0, 10.0]) == 1.0


def test_percentile_rank_on_an_empty_population_is_defined() -> None:
    """A first-ever meeting has no population to rank against. This must not
    divide by zero inside the nightly job."""
    assert isinstance(percentile_rank(1.0, []), float)


def test_missing_inputs_score_none_rather_than_zero() -> None:
    """None means 'not measurable', 0.0 means 'measured and bad'. Collapsing
    the two would drag composite scores down for meetings that simply lack
    attendance data."""
    assert score_attendance_ratio(None, 10) is None
    assert score_attendance_ratio(5, None) is None
    assert score_action_completion(None, None) is None


def test_attendance_ratio_is_a_fraction() -> None:
    assert score_attendance_ratio(5, 10) == 0.5


def test_agenda_detection_finds_a_marker() -> None:
    assert score_agenda_present("Agenda:\n1. budget\n2. hiring") == 1.0


def test_agenda_detection_on_prose_is_zero_not_none() -> None:
    """Text was present and had no agenda — that is a measurement, not a gap."""
    assert score_agenda_present("hey, are we still on for later?") == 0.0
```

Verify the `None`-vs-`0.0` expectations against v5 lines 51-86 before implementing; if v5
returns something different, match v5 and note the discrepancy rather than changing v5's
semantics.

- [ ] **Step 2-5:** run-fail → port → run-pass → commit.

---

### Task 10: Verify the exit criteria and close the phase

- [ ] **Step 1: `config.py` really is the package's only env reader**

```bash
grep -rn "os.environ\|os.getenv" meeting_notes/ | grep -v "^meeting_notes/config.py"
```
Expected: **no output.** Any hit is a failure of the phase's central criterion.

- [ ] **Step 2: Full suite, lint, types**

```bash
make test
make lint
make typecheck
```

`lint` and `typecheck` currently name only `scripts` and `tests` via `SRC`. Update the
Makefile so both cover `meeting_notes` too:

```makefile
SRC := meeting_notes scripts tests
```

and change `typecheck` to run over `meeting_notes scripts`.

- [ ] **Step 3: Account for every v5 test**

The v5 test files covering this phase's modules are:

| v5 test file | Covers | Disposition |
|---|---|---|
| `test_phase31_meeting_quality.py` | `meeting_quality` | port |
| `test_phase33_access_control.py` | `access_control` | port |
| `test_phase39_person_resolver.py` | `person_resolver` | port |
| `test_phase42_dedup.py` | `dedup` | port |
| `test_phase43_meeting_type_router.py` | `meeting_type_router` | port |
| `test_phase40_person_resolution_upsert.py` | person resolution **into the graph** | **defer to Phase 3** — needs `graph_client` |
| — | `classifier` | **none existed**; written in Task 4 |

Write this table into the phase's closing notes. `PHASE_PLAN.md` requires every dropped or
deferred v5 test to have a written reason, and "it needs a module that does not exist yet" is
a reason — but it has to be recorded, not assumed.

- [ ] **Step 4: Mark the phase done**

Update `docs/PHASE_PLAN.md` Phase 2 to `✅ DONE` with a short outcome paragraph in the style
of Phases 0.5, 0.6 and 1, including the test-disposition table above and a pointer to ADR-018.

- [ ] **Step 5: Refresh the graph**

```bash
graphify . --update
```

Dangling-edge count must not regress. Commit `GRAPH_REPORT.md`, `graph.json`, `graph.html`,
`manifest.json`, `cost.json`. **Never** `cache/` or `.graphify_root`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Phase 2 complete: pure core ported, config.py is the only env reader"
```

---

## Self-review notes

- **Phase plan coverage:** all nine named modules have a task (config → Task 1, utils → 2,
  models → 3, classifier → 4, meeting_type_router → 5, dedup → 6, person_resolver → 7,
  access_control → 8, meeting_quality → 9). The `StagedRecord` decision is ADR-018, written
  before this plan and implemented in Task 3. All three exit criteria are verified in Task 10.
- **Two modules change behaviour, not just typing:** `person_resolver.load_roster` and
  `access_control.load_policy` stop reading `os.environ`. Everything else is a port, and the
  plan says so rather than pretending otherwise.
- **Two latent bugs are pinned by tests rather than left to be discovered:** `uuid5_id` drift
  (Task 2, which would silently fork every MERGE) and the `kind` / `TYPES` vocabulary
  collision (Task 5, which would raise the first time someone assigns one to the other).
- **Where the plan defers to v5 rather than guessing:** `priority_from_due` thresholds,
  `best_match`'s signature, `Roster`/`Resolution`/`Principal`/`Scope` field names, and
  `meeting_quality`'s None-vs-0.0 semantics. Each step says to read the v5 source first and
  match it, because inventing a signature here would break the Phase 6 caller.
- **Deliberately not built:** anything touching I/O. `db.py`, `graph_client.py` and
  `llm_client.py` are Phases 3-4, and `test_phase40_person_resolution_upsert.py` defers with
  them.
