"""Backend routing and preflight for the dev agent's headless Claude Code runner.

**Deliberately separate from `meeting_notes/llm_client.py`** (CLAUDE.md). This
routes an `asyncio.subprocess` invocation of the `claude` CLI — a coding
agent with tool access — not a `chat_json`/`embed` call. `llm_client.py`'s
contract (structured JSON, temperature 0.0, extraction-shaped) does not fit
what this does, so this module owns its own client selection rather than
being forced through that seam.

Three backends:

* **`local`** — LM Studio, $0. The v5 default.
* **`vertex`** — **new in v6 (ADR-020).** Claude Code supports Vertex AI
  natively via `CLAUDE_CODE_USE_VERTEX=1` plus Application Default
  Credentials — the same auth path `llm_client.py`'s `_vertex_auth_header()`
  already proved working this session for extraction and embeddings. No API
  key at all; authentication is ADC. This is the resolution to v5's actual
  blocker: every backend it tried was free-tier-limited or needed a card it
  didn't have (`docs/CHECKPOINT-live-run-backend.md`), and v6's Vertex
  project already has real billing.
* **`claude`** — direct Anthropic API key, optional, for cost control via a
  pinned model.
"""

from __future__ import annotations

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.utils import with_retry

log = structlog.get_logger()

VALID_BACKENDS = ("local", "vertex", "claude")
DEFAULT_MIN_CONTEXT = 32768


class PreflightError(RuntimeError):
    """Raised when the selected backend is not ready to run (actionable message)."""


def select_backend(settings: Settings) -> str:
    backend = settings.dev_agent_llm_backend.strip().lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(
            f"Invalid dev_agent_llm_backend={backend!r}; must be one of {', '.join(VALID_BACKENDS)}"
        )
    return backend


def model_for_run(backend: str, settings: Settings | None = None) -> str | None:
    """Model id to pass to ``claude --model`` for the given backend.

    local  -> the loaded LM Studio model
    vertex -> the pinned Claude-on-Vertex model id (confirm at build time —
              CLAUDE.md: model names are env vars, never literals)
    claude -> the pinned model if set (cost control), else None (Claude
              Code's own default)
    """
    settings = settings or get_settings()
    if backend == "local":
        return settings.dev_agent_lm_model.strip() or None
    if backend == "vertex":
        return settings.dev_agent_vertex_model.strip() or None
    if backend == "claude":
        return settings.dev_agent_claude_model.strip() or None
    return None


def resolve_backend_env(backend: str, settings: Settings | None = None) -> dict[str, str]:
    """Resolve a backend name to the env overrides for the Claude Code subprocess.

    Invariants, each unit-tested:
      - ``local``:  ANTHROPIC_API_KEY == "" so api.anthropic.com stays unreachable
        even if a real key sits in the parent environment.
      - ``vertex``: CLAUDE_CODE_USE_VERTEX=1, no API key at all — ADC only.
      - ``claude``: ANTHROPIC_API_KEY == the real key; routes to api.anthropic.com.
    """
    settings = settings or get_settings()

    if backend == "local":
        env = {
            "ANTHROPIC_BASE_URL": settings.lm_studio_anthropic_url.rstrip("/"),
            "ANTHROPIC_AUTH_TOKEN": "lmstudio",
            "ANTHROPIC_API_KEY": "",
        }
        # Pin BOTH the main and the background "small/fast" model to the one
        # loaded model. Claude Code otherwise requests a default haiku id for
        # background work; LM Studio's JIT loader then tries to load that
        # unknown id, evicts the loaded coder model, and reloads it at the
        # default 8192 context — v5's original local-backend blocker,
        # reproduced live. Pinning both keeps every request on the model
        # already in memory.
        model = settings.dev_agent_lm_model.strip()
        if model:
            env["ANTHROPIC_MODEL"] = model
            env["ANTHROPIC_SMALL_FAST_MODEL"] = model
        return env

    if backend == "vertex":
        return {
            "CLAUDE_CODE_USE_VERTEX": "1",
            "ANTHROPIC_VERTEX_PROJECT_ID": settings.gcp_project_id,
            "CLOUD_ML_REGION": settings.vertex_location,
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_MODEL": settings.dev_agent_vertex_model,
        }

    if backend == "claude":
        return {
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_API_KEY": settings.dev_agent_anthropic_api_key,
            "ANTHROPIC_AUTH_TOKEN": "",
        }

    raise ValueError(f"Unknown backend {backend!r}")


def select_loaded_model(models: list[dict], min_context: int) -> tuple[bool, str]:
    """Pure check over LM Studio's /api/v0/models ``data`` array.

    Returns ``(ok, detail)``. Ready when at least one non-embedding model has
    ``state == "loaded"`` and ``loaded_context_length >= min_context``.
    """
    loaded = [m for m in models if m.get("state") == "loaded" and m.get("type") != "embeddings"]
    if not loaded:
        return False, "no chat model is loaded in LM Studio"
    best = max(loaded, key=lambda m: m.get("loaded_context_length") or 0)
    ctx = best.get("loaded_context_length") or 0
    if ctx < min_context:
        return False, f"loaded model {best.get('id')!r} context {ctx} < required {min_context}"
    return True, f"{best.get('id')} @ {ctx} ctx"


@with_retry(max_attempts=3, base_delay=2.0)
async def _fetch_models(root: str) -> list[dict]:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{root}/api/v0/models")
        resp.raise_for_status()
        data: list[dict] = resp.json().get("data", [])
        return data


async def preflight_local(settings: Settings, min_context: int | None = None) -> str:
    """Verify LM Studio has a chat model loaded with >= min_context."""
    min_context = min_context or settings.dev_agent_min_context
    root = settings.lm_studio_anthropic_url.rstrip("/")
    try:
        models = await _fetch_models(root)
    except Exception as exc:
        raise PreflightError(
            f"Could not reach LM Studio at {root}/api/v0/models ({exc}). Start LM Studio "
            "and load a coder model (set DEV_AGENT_LM_MODEL)."
        ) from exc
    ok, detail = select_loaded_model(models, min_context)
    if not ok:
        model = settings.dev_agent_lm_model or "a coder model"
        raise PreflightError(
            f"LM Studio preflight failed: {detail}. Load {model} in LM Studio with context "
            f"length >= {min_context}."
        )
    log.info("dev_agent.preflight.ok", backend="local", detail=detail)
    return detail


def preflight_vertex(settings: Settings) -> str:
    """Verify the Vertex backend has a project to authenticate against.

    Does not make a network call — ADC availability is checked by Claude Code
    itself at run time. This is the fast, actionable check: is the project
    even configured.
    """
    if not settings.gcp_project_id.strip():
        raise PreflightError(
            "dev_agent_llm_backend=vertex requires GCP_PROJECT_ID to be set. "
            "Application Default Credentials must also be available "
            "(gcloud auth application-default login)."
        )
    detail = f"vertex project={settings.gcp_project_id} region={settings.vertex_location}"
    log.info("dev_agent.preflight.ok", backend="vertex", detail=detail)
    return detail


def preflight_claude(settings: Settings) -> str:
    if not settings.dev_agent_anthropic_api_key.strip():
        raise PreflightError(
            "dev_agent_llm_backend=claude requires DEV_AGENT_ANTHROPIC_API_KEY to be set."
        )
    return "backend=claude (hosted; no local model preflight)"


async def preflight(backend: str, settings: Settings | None = None) -> str:
    """Run backend-appropriate preflight. Only ``local`` makes a network call."""
    settings = settings or get_settings()
    if backend == "local":
        return await preflight_local(settings)
    if backend == "vertex":
        return preflight_vertex(settings)
    if backend == "claude":
        return preflight_claude(settings)
    raise ValueError(f"Unknown backend {backend!r}")
