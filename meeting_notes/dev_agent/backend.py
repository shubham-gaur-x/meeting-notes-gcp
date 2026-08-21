"""Backend routing and preflight for the dev agent's headless coding runner.

**Deliberately separate from `meeting_notes/llm_client.py`** (CLAUDE.md). This
routes an `asyncio.subprocess` invocation of the `gemini` CLI — a coding agent
with tool access — not a `chat_json`/`embed` call. `llm_client.py`'s contract
(structured JSON, temperature 0.0, extraction-shaped) does not fit what this
does, so this module owns its own client selection rather than being forced
through that seam.

**One backend: `gemini` (ADR-021).** The agent runs Gemini CLI against Vertex
AI using Application Default Credentials — the same auth path `llm_client.py`
already uses for extraction and embeddings. Every other candidate was ruled
out on cost or hosting grounds, not capability:

* Claude on Vertex is a Cloud Marketplace "model as a service" purchase, which
  Google's free-trial credit explicitly does not cover — enabling it needs a
  converted billing account.
* The direct Anthropic API is not GCP-hosted.
* LM Studio and any other local model are out of scope for this project.

Auth is set per-subprocess via `GEMINI_CLI_HOME`, pointing at a config
directory this module owns. Without it the CLI reads the developer's own
`~/.gemini/settings.json`, whose `selectedType` wins over the environment and
silently routes to Code Assist instead of Vertex.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from meeting_notes.config import Settings, get_settings

log = structlog.get_logger()

VALID_BACKENDS = ("gemini",)


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
    """Model id to pass to ``gemini --model``, or None for the CLI's default."""
    settings = settings or get_settings()
    if backend == "gemini":
        return settings.dev_agent_gemini_model.strip() or None
    return None


def ensure_cli_home(settings: Settings) -> str:
    """Create the CLI config dir that pins auth to Vertex, and return its path.

    Written every call rather than only when missing: the file is small, and a
    stale `selectedType` here would route the agent to the wrong backend
    without any error a caller could catch.
    """
    home = Path(settings.dev_agent_gemini_cli_home).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    (home / "settings.json").write_text(
        json.dumps({"security": {"auth": {"selectedType": "vertex-ai"}}}, indent=2)
    )
    return str(home)


def resolve_backend_env(backend: str, settings: Settings | None = None) -> dict[str, str]:
    """Resolve a backend name to the env overrides for the CLI subprocess.

    Invariants, each unit-tested:
      - GEMINI_CLI_HOME points at our own config dir, never the developer's.
      - GOOGLE_GENAI_USE_VERTEXAI=1 and a project/location are always set, so
        the CLI cannot fall back to the Code Assist (`oauth-personal`) path.
      - GEMINI_API_KEY == "" so an AI Studio key in the parent environment
        cannot silently redirect billing away from the GCP project.
    """
    settings = settings or get_settings()

    if backend == "gemini":
        return {
            "GEMINI_CLI_HOME": ensure_cli_home(settings),
            "GOOGLE_GENAI_USE_VERTEXAI": "1",
            "GOOGLE_CLOUD_PROJECT": settings.gcp_project_id,
            "GOOGLE_CLOUD_LOCATION": settings.dev_agent_gemini_location,
            "GEMINI_API_KEY": "",
        }

    raise ValueError(f"Unknown backend {backend!r}")


def preflight_gemini(settings: Settings) -> str:
    """Verify the Gemini backend has a project and model configured.

    Does not make a network call — ADC availability is checked by the CLI
    itself at run time. This is the fast, actionable check: is the project
    even configured.
    """
    if not settings.gcp_project_id.strip():
        raise PreflightError(
            "dev_agent_llm_backend=gemini requires GCP_PROJECT_ID to be set. "
            "Application Default Credentials must also be available "
            "(gcloud auth application-default login)."
        )
    model = settings.dev_agent_gemini_model.strip()
    location = settings.dev_agent_gemini_location.strip()
    if not location:
        raise PreflightError(
            "dev_agent_llm_backend=gemini requires DEV_AGENT_GEMINI_LOCATION. "
            "Note the newer models are only served from 'global'."
        )
    detail = f"gemini project={settings.gcp_project_id} location={location} model={model or '(cli default)'}"
    log.info("dev_agent.preflight.ok", backend="gemini", detail=detail)
    return detail


async def preflight(backend: str, settings: Settings | None = None) -> str:
    """Run backend-appropriate preflight."""
    settings = settings or get_settings()
    if backend == "gemini":
        return preflight_gemini(settings)
    raise ValueError(f"Unknown backend {backend!r}")
