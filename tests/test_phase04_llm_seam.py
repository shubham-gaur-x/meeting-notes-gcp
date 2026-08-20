"""Phase 4 — the LLM seam. Runs with no network, no API key, no LM Studio.

Every backend is exercised through an injected transport, and `fake` replays
recorded fixtures from a tmp_path, so nothing here touches a real model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_notes.config import Settings
from meeting_notes.llm_client import (
    FixtureMiss,
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
    with pytest.raises(FixtureMiss) as exc:
        await chat_json("unrecorded system", "unrecorded user", settings=_fake_settings(tmp_path))

    message = str(exc.value)
    assert "record_fixtures" in message, "the error must name the command that fixes it"


async def test_a_prompt_edit_produces_a_miss_not_a_stale_replay(tmp_path: Path) -> None:
    """The whole point of keying on the prompt."""
    settings = _fake_settings(tmp_path)
    _record(tmp_path, "original system", "usr", {"title": "old"})

    with pytest.raises(FixtureMiss):
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
    for name in ("fake", "gemini", "lmstudio", "vertex"):
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


def _lmstudio_settings(**over: object) -> Settings:
    base = dict(
        _env_file=None, LLM_BACKEND="lmstudio", LM_STUDIO_MODEL="m",
        LM_STUDIO_BASE_URL="http://localhost:1234/v1",
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
        await chat_json("s", "u", settings=_lmstudio_settings(), transport=flaky)

    assert len(calls) == 3, "with_retry(max_attempts=3) should have tried three times"


async def test_a_transport_error_that_recovers_returns_the_result() -> None:
    calls: list[str] = []

    async def recovers(url: str, payload: dict, headers: dict) -> str:
        calls.append(url)
        if len(calls) < 2:
            raise TimeoutError("first attempt fails")
        return json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]})

    result = await chat_json("s", "u", settings=_lmstudio_settings(), transport=recovers)
    assert result == {"ok": True}
    assert len(calls) == 2


async def test_parse_failures_do_NOT_retry() -> None:
    """At temperature 0 an identical retry yields identical output, so retrying
    a parse failure just burns quota to fail the same way. v5 made this policy
    explicit in a comment; here it is a test."""
    calls: list[str] = []

    async def garbage(url: str, payload: dict, headers: dict) -> str:
        calls.append(url)
        return json.dumps({"choices": [{"message": {"content": "not json at all"}}]})

    result = await chat_json("s", "u", settings=_lmstudio_settings(), transport=garbage)

    assert result is None
    assert len(calls) == 1, "a parse failure must not be retried"


# ─── real backends, exercised offline ─────────────────────────────────────────


async def test_extraction_is_always_temperature_zero() -> None:
    """CLAUDE.md: temperature is 0.0 for extraction. Always."""
    seen: dict = {}

    async def capture(url: str, payload: dict, headers: dict) -> str:
        seen.update(payload)
        return json.dumps({"choices": [{"message": {"content": "{}"}}]})

    await chat_json("s", "u", settings=_lmstudio_settings(), transport=capture)
    assert seen["temperature"] == 0.0


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
        return json.dumps({"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    with pytest.raises(ValueError, match="768"):
        await embed("text", settings=_lmstudio_settings(), transport=short)


async def test_a_correct_length_embedding_passes_through() -> None:
    async def right(url: str, payload: dict, headers: dict) -> str:
        return json.dumps({"data": [{"embedding": [0.01] * 768}]})

    vector = await embed("text", settings=_lmstudio_settings(), transport=right)
    assert vector is not None and len(vector) == 768
