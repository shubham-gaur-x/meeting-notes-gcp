"""Phase 4 — the LLM seam. Runs with no network and no API key.

Every backend is exercised through an injected transport, and `fake` replays
recorded fixtures from a tmp_path, so nothing here touches a real model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_notes.config import Settings
from meeting_notes.llm_client import (
    FixtureMissError,
    _loads_lenient,
    chat_json,
    embed,
    fixture_key,
    select_backend,
)


def _fake_settings(fixture_dir: Path) -> Settings:
    return Settings(_env_file=None, LLM_BACKEND="fake", LLM_FIXTURE_DIR=str(fixture_dir))


def _record(fixture_dir: Path, system: str, user: str, payload: dict, temperature: float = 0.0) -> None:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    key = fixture_key(system, user, temperature)
    (fixture_dir / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


# ─── fixture keying (ADR-014) ─────────────────────────────────────────────────


def test_fixture_key_is_stable_for_identical_input() -> None:
    assert fixture_key("s", "u", 0.0) == fixture_key("s", "u", 0.0)


def test_fixture_key_changes_when_the_prompt_changes() -> None:
    """ADR-014: a prompt edit must invalidate the fixture rather than replay a
    stale one, so the key covers the system prompt."""
    assert fixture_key("s", "u", 0.0) != fixture_key("s EDITED", "u", 0.0)


def test_fixture_key_changes_when_the_user_content_changes() -> None:
    assert fixture_key("s", "u", 0.0) != fixture_key("s", "u EDITED", 0.0)


def test_fixture_key_changes_with_temperature() -> None:
    assert fixture_key("s", "u", 0.0) != fixture_key("s", "u", 0.7)


def test_fixture_key_is_filename_safe() -> None:
    key = fixture_key("sys/with:punct", "user\nwith newlines", 0.0)
    assert key.isalnum(), "the key becomes a filename, so it must be path-safe"


# ─── the fake backend ─────────────────────────────────────────────────────────


async def test_fake_replays_a_recorded_fixture(tmp_path: Path) -> None:
    settings = _fake_settings(tmp_path)
    _record(tmp_path, "sys", "usr", {"title": "Recorded meeting"})

    result = await chat_json("sys", "usr", settings=settings)
    assert result == {"title": "Recorded meeting"}


async def test_a_fixture_miss_raises_rather_than_returning_none(tmp_path: Path) -> None:
    """The single most important test in this file.

    ADR-014: a miss never falls through to None, a default, or an empty
    extraction. A silently-wrong extraction is the worst outcome available, so
    the failure is loud and says how to fix itself.
    """
    with pytest.raises(FixtureMissError) as exc:
        await chat_json("unrecorded system", "unrecorded user", settings=_fake_settings(tmp_path))

    message = str(exc.value)
    assert "record_fixtures" in message, "the error must name the command that fixes it"


async def test_a_prompt_edit_produces_a_miss_not_a_stale_replay(tmp_path: Path) -> None:
    """The whole point of keying on the prompt."""
    settings = _fake_settings(tmp_path)
    _record(tmp_path, "original system", "usr", {"title": "old"})

    with pytest.raises(FixtureMissError):
        await chat_json("edited system", "usr", settings=settings)


async def test_fake_embed_returns_the_configured_dimension(tmp_path: Path) -> None:
    """768 in EVERY backend, fake included — both Memgraph vector indexes are
    built for 768 and a shorter vector fails at insert time, far from here."""
    vector = await embed("anything", settings=_fake_settings(tmp_path))
    assert vector is not None
    assert len(vector) == 768


async def test_fake_embed_follows_the_configured_dimension(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, LLM_BACKEND="fake", LLM_FIXTURE_DIR=str(tmp_path), EMBEDDING_DIMENSION=1024
    )
    vector = await embed("anything", settings=settings)
    assert vector is not None and len(vector) == 1024


async def test_fake_embeddings_are_deterministic_but_differ_by_text(tmp_path: Path) -> None:
    """Semantic-search tests need vectors that are stable across runs yet still
    discriminate between different texts."""
    settings = _fake_settings(tmp_path)
    a1 = await embed("alpha", settings=settings)
    a2 = await embed("alpha", settings=settings)
    b = await embed("beta", settings=settings)

    assert a1 == a2, "the same text must embed identically across calls"
    assert a1 != b, "different texts must embed differently"


async def test_fake_embeddings_are_normalised(tmp_path: Path) -> None:
    """The indexes use cosine similarity; unit vectors keep scores comparable."""
    vector = await embed("alpha", settings=_fake_settings(tmp_path))
    assert vector is not None
    magnitude = sum(v * v for v in vector) ** 0.5
    assert magnitude == pytest.approx(1.0, abs=1e-6)


# ─── backend selection ────────────────────────────────────────────────────────


def test_backend_selection_is_env_driven() -> None:
    for name in ("fake", "gemini", "vertex"):
        assert select_backend(Settings(_env_file=None, LLM_BACKEND=name)) == name


def test_fake_is_the_default_backend() -> None:
    """Tier 0 must work on a clean clone with no .env at all."""
    assert select_backend(Settings(_env_file=None)) == "fake"


# ─── lenient parsing (carried from v5) ────────────────────────────────────────


def test_parses_a_clean_json_object() -> None:
    assert _loads_lenient('{"a": 1}') == {"a": 1}


def test_salvages_json_wrapped_in_prose() -> None:
    """Observed live: models narrate around the object despite instructions."""
    assert _loads_lenient('Sure! Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}


def test_strips_markdown_fences() -> None:
    """Local models wrap JSON in ```json fences despite being told not to.
    CLAUDE.md: this defence was found by live testing and must be kept."""
    assert _loads_lenient('```json\n{"a": 1}\n```') == {"a": 1}


def test_returns_none_when_nothing_parses() -> None:
    assert _loads_lenient("no json here at all") is None


def test_returns_none_for_empty_input() -> None:
    assert _loads_lenient("") is None


def test_a_bare_array_is_not_accepted_as_an_object() -> None:
    """chat_json promises a dict; a list would break every caller downstream."""
    assert _loads_lenient("[1, 2, 3]") is None


def test_nested_braces_survive_the_salvage() -> None:
    assert _loads_lenient('noise {"a": {"b": 2}} noise') == {"a": {"b": 2}}


# ─── retry semantics (explicit exit criterion) ────────────────────────────────


def _vertex_settings(**over: object) -> Settings:
    base = dict(
        _env_file=None, LLM_BACKEND="vertex", GCP_PROJECT_ID="proj-x",
        VERTEX_CHAT_MODEL="gemini-3.7-flash", VERTEX_LOCATION="global",
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


async def test_transport_errors_retry() -> None:
    """A timeout or 5xx is transient — retry it."""
    calls: list[str] = []

    async def flaky(url: str, payload: dict, headers: dict) -> str:
        calls.append(url)
        raise TimeoutError("connection reset")

    with pytest.raises(TimeoutError):
        await chat_json("s", "u", settings=_vertex_settings(), transport=flaky)

    assert len(calls) == 3, "with_retry(max_attempts=3) should have tried three times"


async def test_a_transport_error_that_recovers_returns_the_result() -> None:
    calls: list[str] = []

    async def recovers(url: str, payload: dict, headers: dict) -> str:
        calls.append(url)
        if len(calls) < 2:
            raise TimeoutError("first attempt fails")
        return json.dumps({"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})

    result = await chat_json("s", "u", settings=_vertex_settings(), transport=recovers)
    assert result == {"ok": True}
    assert len(calls) == 2


async def test_parse_failures_do_NOT_retry() -> None:
    """At temperature 0 an identical retry yields identical output, so retrying
    a parse failure just burns quota to fail the same way. v5 made this policy
    explicit in a comment; here it is a test."""
    calls: list[str] = []

    async def garbage(url: str, payload: dict, headers: dict) -> str:
        calls.append(url)
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]})

    result = await chat_json("s", "u", settings=_vertex_settings(), transport=garbage)

    assert result is None
    assert len(calls) == 1, "a parse failure must not be retried"


# ─── real backends, exercised offline ─────────────────────────────────────────


async def test_extraction_is_always_temperature_zero() -> None:
    """CLAUDE.md: temperature is 0.0 for extraction. Always."""
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen.update(payload)
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    await chat_json("s", "u", settings=_vertex_settings(), transport=capture)
    assert seen["generationConfig"]["temperature"] == 0.0


async def test_gemini_reads_its_model_from_settings_not_a_literal() -> None:
    """PHASE_PLAN Phase 4 task 3: model names are env vars, never literals."""
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen["url"] = url
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    settings = Settings(
        _env_file=None, LLM_BACKEND="gemini", GEMINI_API_KEY="k",
        GEMINI_CHAT_MODEL="gemini-9.9-turbo",
    )
    await chat_json("s", "u", settings=settings, transport=capture)
    assert "gemini-9.9-turbo" in seen["url"]


async def test_vertex_reads_its_model_and_project_from_settings() -> None:
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen["url"] = url
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    settings = Settings(
        _env_file=None, LLM_BACKEND="vertex", GCP_PROJECT_ID="proj-x",
        VERTEX_CHAT_MODEL="gemini-9.9-flash", VERTEX_LOCATION="europe-west4",
    )
    await chat_json("s", "u", settings=settings, transport=capture)
    assert "proj-x" in seen["url"]
    assert "gemini-9.9-flash" in seen["url"]
    assert "europe-west4" in seen["url"]


async def test_the_global_location_uses_the_unprefixed_vertex_host() -> None:
    """`global` is not a region: there is no global-aiplatform.googleapis.com
    and using one 404s. This matters because the Gemini 3.x models are served
    ONLY from `global` (ADR-021) -- caught live, not by a unit test."""
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen["url"] = url
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    settings = Settings(
        _env_file=None, LLM_BACKEND="vertex", GCP_PROJECT_ID="proj-x",
        VERTEX_CHAT_MODEL="gemini-3.7-flash", VERTEX_LOCATION="global",
    )
    await chat_json("s", "u", settings=settings, transport=capture)
    assert "global-aiplatform.googleapis.com" not in seen["url"]
    assert seen["url"].startswith("https://aiplatform.googleapis.com/")
    assert "/locations/global/" in seen["url"]


async def test_the_global_location_also_applies_to_embeddings() -> None:
    """embed() builds its own URL; the regional/global split must hold there
    too or the vector path 404s while chat works."""
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen["url"] = url
        return json.dumps({"predictions": [{"embeddings": {"values": [0.0] * 768}}]})

    settings = Settings(
        _env_file=None, LLM_BACKEND="vertex", GCP_PROJECT_ID="proj-x",
        VERTEX_EMBEDDING_MODEL="text-embedding-005", VERTEX_LOCATION="global",
    )
    await embed("hello", settings=settings, transport=capture)
    assert "global-aiplatform.googleapis.com" not in seen["url"]
    assert seen["url"].startswith("https://aiplatform.googleapis.com/")


async def test_a_real_region_still_uses_the_regional_vertex_host() -> None:
    """The global special-case must not break every ordinary region."""
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen["url"] = url
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    settings = Settings(
        _env_file=None, LLM_BACKEND="vertex", GCP_PROJECT_ID="proj-x",
        VERTEX_CHAT_MODEL="gemini-2.5-flash", VERTEX_LOCATION="us-central1",
    )
    await chat_json("s", "u", settings=settings, transport=capture)
    assert seen["url"].startswith("https://us-central1-aiplatform.googleapis.com/")


async def test_the_api_key_is_sent_as_a_header_not_a_query_parameter() -> None:
    """A key in the URL leaks into logs, proxies and error messages."""
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen["url"], seen["headers"] = url, headers
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    settings = Settings(_env_file=None, LLM_BACKEND="gemini", GEMINI_API_KEY="secret-leakcanary")
    await chat_json("s", "u", settings=settings, transport=capture)

    assert "leakcanary" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "secret-leakcanary"


async def test_a_wrong_length_embedding_raises_rather_than_being_stored() -> None:
    """A short vector would fail at Memgraph insert time, far from the call
    that produced it. Fail here, where the message can be useful."""
    async def short(url: str, payload: dict, headers: dict) -> str:
        return json.dumps({"predictions": [{"embeddings": {"values": [0.1, 0.2, 0.3]}}]})

    with pytest.raises(ValueError, match="768"):
        await embed("text", settings=_vertex_settings(), transport=short)


async def test_a_correct_length_embedding_passes_through() -> None:
    async def right(url: str, payload: dict, headers: dict) -> str:
        return json.dumps({"predictions": [{"embeddings": {"values": [0.01] * 768}}]})

    vector = await embed("text", settings=_vertex_settings(), transport=right)
    assert vector is not None and len(vector) == 768


# ─── extractor ────────────────────────────────────────────────────────────────

from meeting_notes.extractor import (  # noqa: E402
    _SYSTEM_PROMPT,
    _is_null_like,
    build_system_prompt,
    extract_meeting,
    repair,
)

V5_EXTRACTOR = Path.home() / "Desktop/airbyte-lm-studio-memgraph/transform_service/extractor.py"


# Deliberate, documented additions to v5's tuned prompt. Anything else
# appearing here is drift and fails the test below.
_ALLOWED_PROMPT_ADDITIONS = (
    '"blockers"',       # the Blocker field v5 never extracted -- see ADR-023
    "A blocker is something explicitly stated",
)


def test_every_line_of_v5s_tuned_prompt_survives_verbatim() -> None:
    """It is tuned. Diffing it against v5's file is the entire point.

    A well-meaning reword must fail here rather than quietly degrade every
    extraction in a way nobody notices until the graph looks wrong. Additions
    are allowed but must be declared in `_ALLOWED_PROMPT_ADDITIONS`, so
    extending the schema stays a deliberate act and rewording does not.
    """
    if not V5_EXTRACTOR.exists():
        pytest.skip("v5 reference repo not present on this machine")

    import re

    match = re.search(r'_SYSTEM_PROMPT = """(.*?)"""', V5_EXTRACTOR.read_text(encoding="utf-8"), re.S)
    assert match, "could not locate v5's _SYSTEM_PROMPT"

    ours = _SYSTEM_PROMPT.splitlines()
    dropped = [line for line in match.group(1).splitlines() if line not in ours]
    assert not dropped, f"v5 prompt lines were reworded or lost: {dropped}"

    added = [line for line in ours if line not in match.group(1).splitlines()]
    undeclared = [
        line for line in added
        if not any(token in line for token in _ALLOWED_PROMPT_ADDITIONS)
    ]
    assert not undeclared, f"undeclared prompt additions: {undeclared}"


def test_prompt_still_states_the_is_engineering_task_rule() -> None:
    """A load-bearing sentence: it gates which action items dev_agent may pick
    up in v2, so losing it silently changes downstream behaviour."""
    assert "is_engineering_task is true only if" in _SYSTEM_PROMPT


# ─── the literal "null" bug (MIGRATION_FROM_V5.md #4) ─────────────────────────


def test_literal_string_null_is_treated_as_null() -> None:
    """gemma3-12b emits the literal string "null" for optional fields. A plain
    `if not value` misses it: "null" is a non-empty string, therefore truthy."""
    for value in (None, "", "null", "NULL", " none ", "n/a", "N/A", "  "):
        assert _is_null_like(value) is True, f"{value!r} should be null-like"


def test_real_values_are_not_treated_as_null() -> None:
    for value in ("meeting", "Google Meet", "2026-08-20", "0"):
        assert _is_null_like(value) is False, f"{value!r} should NOT be null-like"


def test_a_null_string_platform_is_replaced_from_context() -> None:
    """The exact live failure: platform came back as "null" and validation blew up."""
    repaired = repair({"platform": "null"}, context={"platform": "Google Meet"})
    assert repaired["platform"] == "Google Meet"


def test_a_null_string_date_falls_back_rather_than_failing_validation() -> None:
    repaired = repair({"date": "null"}, context={"date": "2026-08-20"})
    assert repaired["date"] == "2026-08-20"


def test_summary_falls_back_to_the_title() -> None:
    repaired = repair({"summary": "null", "title": "Weekly sync"})
    assert repaired["summary"] == "Weekly sync"


def test_action_items_with_null_owner_are_repaired_not_dropped() -> None:
    """A nameless task is still a real task — dropping it loses information."""
    repaired = repair({"action_items": [{"owner": "null", "task": "null"}]})
    item = repaired["action_items"][0]
    assert item["owner"] == "Unknown"
    assert item["task"] == "Follow-up required"
    assert item["is_engineering_task"] is False
    assert item["confidence"] == 1.0


def test_repair_leaves_good_data_alone() -> None:
    original = {
        "platform": "Zoom",
        "date": "2026-08-20",
        "summary": "a real summary",
        "action_items": [{"owner": "alice@corp.com", "task": "ship it", "confidence": 0.8}],
    }
    repaired = repair(dict(original), context={"platform": "SHOULD NOT BE USED"})
    assert repaired["platform"] == "Zoom"
    assert repaired["action_items"][0]["confidence"] == 0.8


# ─── prompt assembly and the end-to-end path ──────────────────────────────────


def test_type_hint_is_appended_to_the_system_prompt() -> None:
    """meeting_type_router's hint must actually reach the model, or routing is
    decorative."""
    assembled = build_system_prompt("Standups are terse; expect many small items.")
    assert assembled.startswith(_SYSTEM_PROMPT)
    assert "Standups are terse" in assembled


def test_no_type_hint_leaves_the_prompt_untouched() -> None:
    assert build_system_prompt(None) == _SYSTEM_PROMPT


async def test_extract_meeting_produces_a_valid_meeting_from_a_fixture(tmp_path: Path) -> None:
    """The exit criterion, on the fake backend: a recorded response in, a
    validated ExtractedMeeting out."""
    settings = _fake_settings(tmp_path)
    system = build_system_prompt(None)
    user = "Extract meeting information from this email:\n\nsome text"
    _record(
        tmp_path, system, user,
        {
            "title": "Budget sync", "kind": "meeting", "platform": "null",
            "date": "null", "summary": "null",
            "action_items": [{"owner": "null", "task": "null"}],
        },
    )

    meeting = await extract_meeting("some text", "email", context={"platform": "Google Meet"},
                                    settings=settings)

    assert meeting is not None
    assert meeting.title == "Budget sync"
    assert meeting.platform == "Google Meet", "the literal 'null' should have been repaired"
    assert meeting.action_items[0].owner == "Unknown"


async def test_a_parse_failure_returns_none_rather_than_raising() -> None:
    """The pipeline marks the record processed and moves on; it must not crash
    the whole drain because one model reply was malformed."""
    async def garbage(url: str, payload: dict, headers: dict) -> str:
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "not json"}]}}]})

    result = await extract_meeting("text", "email", settings=_vertex_settings(),
                                   transport=garbage)
    assert result is None


async def test_validation_failure_returns_none_rather_than_raising() -> None:
    """Unrepairable output is still not a crash."""
    async def wrong_shape(url: str, payload: dict, headers: dict) -> str:
        inner = json.dumps({"title": None, "kind": {"nested": "garbage"}})
        return json.dumps({"candidates": [{"content": {"parts": [{"text": inner}]}}]})

    result = await extract_meeting("text", "email", settings=_vertex_settings(),
                                   transport=wrong_shape)
    assert result is None


# ─── fixture recording ────────────────────────────────────────────────────────

from scripts import record_fixtures  # noqa: E402


async def test_the_recorder_writes_the_key_the_extractor_reads(tmp_path: Path) -> None:
    """The invariant this whole mechanism rests on.

    CLAUDE.md calls writer/reader id drift a known v5 bug class that cost real
    debugging time twice. The same hazard applies here: if the recorder keys a
    fixture differently from how extract_meeting looks it up, every replay
    misses and tier 0 is dead — with a confusing "no fixture" error rather
    than an obvious cause. So the recorder derives its prompts from the
    extractor's own helper, and this proves the round trip.
    """
    record = {"name": "t", "source_type": "email", "type_hint": None, "text": "hello"}

    # what the recorder would write
    system, user = record_fixtures.prompts_for(record)
    key = fixture_key(system, user, 0.0)
    record_fixtures.write_fixture(
        tmp_path, key,
        {"title": "Round trip", "kind": "email_thread", "platform": "Email",
         "date": "2026-08-20", "summary": "s"},
    )

    # what the extractor actually looks up
    meeting = await extract_meeting(
        record["text"], record["source_type"], settings=_fake_settings(tmp_path)
    )

    assert meeting is not None, "the extractor missed the fixture the recorder just wrote"
    assert meeting.title == "Round trip"


async def test_the_round_trip_holds_with_a_type_hint(tmp_path: Path) -> None:
    """The hint changes the system prompt, so it must change the key on both
    sides identically."""
    record = {
        "name": "t", "source_type": "meet_transcript",
        "type_hint": "A standup. Expect terse updates.", "text": "hello",
    }
    system, user = record_fixtures.prompts_for(record)
    record_fixtures.write_fixture(
        tmp_path, fixture_key(system, user, 0.0),
        {"title": "Hinted", "kind": "standup", "platform": "Google Meet",
         "date": "2026-08-20", "summary": "s"},
    )

    meeting = await extract_meeting(
        record["text"], record["source_type"], type_hint=record["type_hint"],
        settings=_fake_settings(tmp_path),
    )
    assert meeting is not None and meeting.title == "Hinted"


def test_the_corpus_is_loadable_and_well_formed() -> None:
    """Every corpus entry needs the fields the recorder reads."""
    corpus = record_fixtures.load_corpus(record_fixtures.CORPUS_DIR)
    assert corpus, "the sample corpus is empty"
    for record in corpus:
        assert record["source_type"], "source_type is required"
        assert record["text"].strip(), "text is required"
        assert record.get("name"), "name is used in the recorder's output"


def test_the_corpus_covers_more_than_one_meeting_shape() -> None:
    """PHASE_PLAN Phase 7 warns that v5's graph is 73% standups and its
    algorithm output is distorted accordingly. Start the corpus diverse."""
    corpus = record_fixtures.load_corpus(record_fixtures.CORPUS_DIR)
    assert len({r["source_type"] for r in corpus}) > 1


# ─── chat_list (found in a live backfill log) ─────────────────────────────────


def test_a_bare_array_parses_through_the_list_path() -> None:
    """The bug: several prompts say "respond ONLY with a JSON array", and
    routing them through the object parser threw away correct answers. Fact
    extraction produced ZERO facts across the whole corpus while the model was
    answering perfectly."""
    from meeting_notes.llm_client import _loads_lenient_list

    assert _loads_lenient_list('["a", "b"]') == ["a", "b"]


def test_the_list_path_salvages_an_array_wrapped_in_prose() -> None:
    from meeting_notes.llm_client import _loads_lenient_list

    assert _loads_lenient_list('Sure:\n["a"]\nhope that helps') == ["a"]


def test_the_list_path_unwraps_a_single_key_object() -> None:
    """Models wrap the array in an object despite being told not to."""
    from meeting_notes.llm_client import _loads_lenient_list

    assert _loads_lenient_list('{"facts": ["a", "b"]}') == ["a", "b"]


def test_the_list_path_returns_none_for_a_plain_object() -> None:
    from meeting_notes.llm_client import _loads_lenient_list

    assert _loads_lenient_list('{"title": "x"}') is None


def test_chat_json_still_rejects_arrays() -> None:
    """The object contract is unchanged -- that rejection is correct for
    extraction, which must never receive a list."""
    assert _loads_lenient('["a"]') is None


async def test_chat_list_reaches_the_backend_and_parses() -> None:
    from meeting_notes.llm_client import chat_list

    async def transport(url: str, payload: dict, headers: dict) -> str:
        return json.dumps({"candidates": [{"content": {"parts": [{"text": '["fact one", "fact two"]'}]}}]})

    result = await chat_list("s", "u", settings=_vertex_settings(), transport=transport)
    assert result == ["fact one", "fact two"]


# ─── raw url extraction & repair links merging ───────────────────────────────


def test_extract_raw_urls_harvests_valid_document_links() -> None:
    from meeting_notes.extractor import _extract_raw_urls

    text = (
        "Please review the design spec at https://docs.google.com/document/d/123/edit "
        "and the project board at https://michael-baylard.atlassian.net/browse/MDP-45. "
        "Also see https://drive.google.com/file/d/456/view."
    )
    urls = _extract_raw_urls(text)
    assert urls == [
        "https://docs.google.com/document/d/123/edit",
        "https://michael-baylard.atlassian.net/browse/MDP-45",
        "https://drive.google.com/file/d/456/view",
    ]


def test_extract_raw_urls_filters_noise_domains_and_image_assets() -> None:
    from meeting_notes.extractor import _extract_raw_urls

    text = (
        "Check namespace http://schemas.microsoft.com/office/2004/12/omml and "
        "http://www.w3.org/1999/xhtml. Logo at https://cdn.example.com/logo.png and "
        "https://mail.google.com/mail/u/0/#inbox. "
        "Real doc: https://company.atlassian.net/wiki/spaces/ENG/pages/789."
    )
    urls = _extract_raw_urls(text)
    assert urls == ["https://company.atlassian.net/wiki/spaces/ENG/pages/789"]


def test_repair_merges_raw_urls_with_extracted_links() -> None:
    from meeting_notes.extractor import repair

    raw_data = {
        "title": "Architecture Sync",
        "links": ["https://docs.google.com/document/d/extracted"],
    }
    context = {
        "text": "Meeting notes with additional doc https://docs.google.com/document/d/raw_in_body",
    }
    repaired = repair(raw_data, context=context)
    assert repaired["links"] == [
        "https://docs.google.com/document/d/extracted",
        "https://docs.google.com/document/d/raw_in_body",
    ]

