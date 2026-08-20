"""The LLM seam — the ONLY module in this package that constructs an LLM client.

Every caller (extractor, memory modules, retrieval) goes through the two
coroutines here. That rule is what makes the backend swappable at all, and
what lets the entire test suite run with no network (CLAUDE.md).

    async def chat_json(system, user, *, temperature=0.0) -> dict | None
    async def embed(text) -> list[float] | None

Four backends behind one protocol (ADR-014):

* ``fake``     replays recorded fixtures. No credentials, no network,
               deterministic. The tier-0 default and the suite's mock.
* ``gemini``   direct AI Studio API key. No GCP project, no billing. Tier 1.
* ``lmstudio`` local models via LM Studio's OpenAI-compatible API.
* ``vertex``   production, on a GCP project with billing.

**A fixture miss raises.** It never falls through to ``None``, a default, or an
empty extraction. A prompt edit changes the fixture key and therefore produces
a loud, immediate failure rather than a silently-wrong result — which ADR-014
calls the worst outcome available here.

``_loads_lenient`` lives in this module rather than in the extractor because
``chat_json`` promises a ``dict``: turning model output into one is precisely
this seam's job. Its body is carried over from v5 unchanged — both it and the
fence stripping in ``utils`` were found by live testing, not unit tests.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any, Protocol

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.utils import strip_json_fences, with_retry

log = structlog.get_logger()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE_DIR = REPO_ROOT / "sample_data" / "llm_fixtures"


class FixtureMiss(RuntimeError):
    """No recorded fixture for this prompt.

    Deliberately fatal (ADR-014). Falling back to None here would turn a
    changed prompt into a silently-empty extraction that looks like a model
    limitation rather than a missing recording.
    """


class Transport(Protocol):
    """Injected HTTP-ish callable, so tests exercise every backend offline."""

    async def __call__(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> str: ...


# ─── fixture keying ───────────────────────────────────────────────────────────


def fixture_key(system: str, user: str, temperature: float) -> str:
    """Stable, filename-safe key for a prompt.

    Covers the system prompt so editing it invalidates the fixture instead of
    replaying a stale answer, and the temperature so a non-zero-temperature
    call cannot borrow a temperature-0 recording.
    """
    digest = hashlib.sha256()
    digest.update(system.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(user.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(f"{temperature:.4f}".encode())
    return digest.hexdigest()[:32]


def fixture_dir(settings: Settings) -> Path:
    return Path(settings.llm_fixture_dir) if settings.llm_fixture_dir else DEFAULT_FIXTURE_DIR


# ─── lenient parsing (carried from v5 unchanged) ──────────────────────────────


def _loads_lenient(text: str) -> dict[str, Any] | None:
    """Parse JSON, tolerating a model that wraps the object in stray prose.

    Tries a strict parse first, then falls back to the first ``{...}`` span.
    Returns None if nothing parses — a non-retryable failure at temperature 0.
    """
    text = strip_json_fences(text or "").strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None



def _loads_lenient_list(text: str) -> list[Any] | None:
    """Parse a JSON ARRAY, tolerating prose around it.

    `chat_json` deliberately rejects a bare array -- it promises a dict, and a
    list would break every extraction caller. But several prompts legitimately
    ask for an array ("respond ONLY with a JSON array of strings"), and routing
    those through the object parser silently discarded correct answers: fact
    extraction produced ZERO facts across the whole corpus while the model was
    answering perfectly. Found in a live backfill log, not by a test.
    """
    text = strip_json_fences(text or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            # Some models wrap the array in a single-key object anyway.
            for value in parsed.values():
                if isinstance(value, list):
                    return value
        return None
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, list) else None
    except (json.JSONDecodeError, ValueError):
        return None


# ─── backend selection ────────────────────────────────────────────────────────


def select_backend(settings: Settings) -> str:
    return settings.llm_backend


# ─── fake ─────────────────────────────────────────────────────────────────────


def _fake_vector(text: str, dimension: int) -> list[float]:
    """A deterministic unit vector derived from the text.

    Stable across runs so semantic-search tests are reproducible, and distinct
    per text so they still discriminate. Normalised because both Memgraph
    vector indexes use cosine similarity.
    """
    raw = bytearray()
    counter = 0
    while len(raw) < dimension * 4:
        raw.extend(hashlib.sha256(f"{text}:{counter}".encode()).digest())
        counter += 1
    values = [struct.unpack_from("<i", raw, i * 4)[0] / 2**31 for i in range(dimension)]
    magnitude = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / magnitude for v in values]


async def _fake_chat_json(system: str, user: str, temperature: float, settings: Settings) -> dict:
    directory = fixture_dir(settings)
    key = fixture_key(system, user, temperature)
    path = directory / f"{key}.json"

    if not path.exists():
        raise FixtureMiss(
            f"No fixture {key}.json in {directory}.\n"
            "The fake backend never guesses — a missing recording is a hard failure "
            "so a changed prompt cannot silently produce an empty extraction.\n"
            "Record it with:  make record-fixtures   "
            "(scripts/record_fixtures.py, needs a real backend)"
        )

    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise FixtureMiss(f"Fixture {path} is not a JSON object")
    return parsed


# ─── real backends ────────────────────────────────────────────────────────────


async def _default_transport(url: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
    """httpx only — never `requests` (CLAUDE.md)."""
    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.text


def _gemini_chat_request(
    system: str, user: str, temperature: float, settings: Settings
) -> tuple[str, dict[str, Any], dict[str, str]]:
    model = settings.gemini_chat_model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    return url, payload, {"x-goog-api-key": settings.gemini_api_key}


def _gemini_text(body: str) -> str:
    data = json.loads(body)
    text: str = data["candidates"][0]["content"]["parts"][0]["text"]
    return text


def _lmstudio_chat_request(
    system: str, user: str, temperature: float, settings: Settings
) -> tuple[str, dict[str, Any], dict[str, str]]:
    url = f"{settings.lm_studio_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.lm_studio_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": 2000,
    }
    return url, payload, {"Authorization": "Bearer lm-studio"}


def _openai_shaped_text(body: str) -> str:
    text: str = json.loads(body)["choices"][0]["message"]["content"]
    return text


def _vertex_chat_request(
    system: str, user: str, temperature: float, settings: Settings
) -> tuple[str, dict[str, Any], dict[str, str]]:
    # Model name comes from settings, never a literal — they change
    # (PHASE_PLAN Phase 4 task 3).
    model = settings.vertex_chat_model
    location = settings.vertex_location
    project = settings.gcp_project_id
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{location}/publishers/google/models/{model}:generateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    return url, payload, {}


def _vertex_auth_header() -> dict[str, str]:
    """Application Default Credentials — no key material in config."""
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {credentials.token}"}


# ─── the protocol ─────────────────────────────────────────────────────────────


@with_retry(max_attempts=3, base_delay=2.0)
async def _post(
    url: str, payload: dict[str, Any], headers: dict[str, str], transport: Transport
) -> str:
    """The retried boundary.

    Only transport failures reach here, so only they are retried. A parse
    failure happens *after* this returns and is deliberately not retried: at
    temperature 0 an identical retry yields identical output, so it would burn
    quota to fail the same way.
    """
    return await transport(url, payload, headers)


async def _raw_completion(
    system: str,
    user: str,
    temperature: float,
    settings: Settings | None,
    transport: Transport | None,
) -> str | None:
    """The backend call, returning raw text.

    Shared by `chat_json` and `chat_list` so the two differ only in the shape
    they expect back, not in which backends they support.

    Returns None for the `fake` backend, whose fixtures are already parsed --
    callers handle that case before reaching here.
    """
    settings = settings or get_settings()
    backend = select_backend(settings)
    transport = transport or _default_transport

    if backend == "gemini":
        url, payload, headers = _gemini_chat_request(system, user, temperature, settings)
        body = await _post(url, payload, headers, transport)
        return _gemini_text(body)
    if backend == "lmstudio":
        url, payload, headers = _lmstudio_chat_request(system, user, temperature, settings)
        body = await _post(url, payload, headers, transport)
        return _openai_shaped_text(body)
    if backend == "vertex":
        url, payload, headers = _vertex_chat_request(system, user, temperature, settings)
        if transport is _default_transport:
            headers = {**headers, **_vertex_auth_header()}
        body = await _post(url, payload, headers, transport)
        return _gemini_text(body)
    raise ValueError(f"unknown LLM backend {backend!r}")


async def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> dict[str, Any] | None:
    """Ask the model for a JSON OBJECT. Returns None if it does not parse.

    A bare array is deliberately rejected: this promises a dict and a list
    would break every extraction caller. Prompts that ask for an array must
    use `chat_list`.
    """
    settings = settings or get_settings()
    backend = select_backend(settings)

    if backend == "fake":
        return await _fake_chat_json(system, user, temperature, settings)

    transport = transport or _default_transport

    if backend == "gemini":
        url, payload, headers = _gemini_chat_request(system, user, temperature, settings)
        body = await _post(url, payload, headers, transport)
        raw = _gemini_text(body)
    elif backend == "lmstudio":
        url, payload, headers = _lmstudio_chat_request(system, user, temperature, settings)
        body = await _post(url, payload, headers, transport)
        raw = _openai_shaped_text(body)
    elif backend == "vertex":
        url, payload, headers = _vertex_chat_request(system, user, temperature, settings)
        if transport is _default_transport:
            headers = {**headers, **_vertex_auth_header()}
        body = await _post(url, payload, headers, transport)
        raw = _gemini_text(body)
    else:
        raise ValueError(f"unknown LLM backend {backend!r}")

    parsed = _loads_lenient(raw)
    if parsed is None:
        log.error("llm.parse_failed", backend=backend, raw_snippet=raw[:200])
    return parsed


async def embed(
    text: str,
    *,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[float] | None:
    """Embed one string. Always `embedding_dimension` long, in every backend."""
    settings = settings or get_settings()
    backend = select_backend(settings)
    dimension = settings.embedding_dimension

    if backend == "fake":
        return _fake_vector(text, dimension)

    transport = transport or _default_transport

    if backend == "lmstudio":
        url = f"{settings.lm_studio_base_url.rstrip('/')}/embeddings"
        payload: dict[str, Any] = {"model": settings.lm_studio_embedding_model, "input": text}
        body = await _post(url, payload, {"Authorization": "Bearer lm-studio"}, transport)
        vector = json.loads(body)["data"][0]["embedding"]
    elif backend == "gemini":
        model = settings.gemini_embedding_model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
        payload = {"content": {"parts": [{"text": text}]}}
        body = await _post(url, payload, {"x-goog-api-key": settings.gemini_api_key}, transport)
        vector = json.loads(body)["embedding"]["values"]
    elif backend == "vertex":
        model = settings.vertex_embedding_model
        location, project = settings.vertex_location, settings.gcp_project_id
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{location}/publishers/google/models/{model}:predict"
        )
        payload = {"instances": [{"content": text}]}
        headers = _vertex_auth_header() if transport is _default_transport else {}
        body = await _post(url, payload, headers, transport)
        vector = json.loads(body)["predictions"][0]["embeddings"]["values"]
    else:
        raise ValueError(f"unknown LLM backend {backend!r}")

    if len(vector) != dimension:
        # Loud, not silent: a wrong-length vector fails at Memgraph insert time,
        # a long way from the call that produced it.
        log.error(
            "llm.embedding_dimension_mismatch",
            backend=backend,
            expected=dimension,
            got=len(vector),
        )
        raise ValueError(
            f"{backend} returned a {len(vector)}-dim embedding but the vector indexes "
            f"are built for {dimension}. Changing this means migrating both indexes."
        )
    return list(vector)


async def chat_list(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    settings: Settings | None = None,
    transport: Transport | None = None,
) -> list[Any] | None:
    """Ask the model for a JSON ARRAY.

    Same backends and retry semantics as `chat_json`; only the expected shape
    differs. Callers whose prompt says "respond with a JSON array" must use
    this, or a correct answer is thrown away as unparseable.
    """
    settings = settings or get_settings()
    if select_backend(settings) == "fake":
        fixture = await _fake_chat_json(system, user, temperature, settings)
        for value in fixture.values():
            if isinstance(value, list):
                return value
        return []

    raw = await _raw_completion(system, user, temperature, settings, transport)
    if raw is None:
        return None
    parsed = _loads_lenient_list(raw)
    if parsed is None:
        log.error("llm.parse_failed_list", raw_snippet=raw[:200])
    return parsed
