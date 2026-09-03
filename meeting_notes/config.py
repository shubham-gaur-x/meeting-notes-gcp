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

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMBackend = Literal["fake", "gemini", "vertex"]


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
    gemini_embedding_model: str = "text-embedding-004"
    # Where the `fake` backend reads recorded fixtures from. Blank = the
    # committed sample_data/llm_fixtures/. Tests point it at a tmp_path.
    llm_fixture_dir: str = ""

    # ─── Dev agent (Phase 11, ADR-020/ADR-021) ─────────────────────────────
    # Coding-model routing. Deliberately separate from llm_backend above --
    # this selects a headless `gemini` CLI subprocess backend, not a
    # chat_json/embed call (CLAUDE.md).
    dev_agent_llm_backend: str = "gemini"
    # Confirm the current model id at build time -- they change (CLAUDE.md).
    # The 3.x models are served only from location "global"; us-central1 has
    # nothing newer than 2.5 (probed live, ADR-021).
    dev_agent_gemini_model: str = "gemini-3-pro-preview"
    dev_agent_gemini_location: str = "global"
    # Config dir the agent owns, so the CLI never reads a developer's own
    # ~/.gemini/settings.json (whose auth selection would win). See
    # dev_agent/backend.py:ensure_cli_home.
    dev_agent_gemini_cli_home: str = "/tmp/dev-agent/gemini-home"
    # No turn cap: the `gemini` CLI exposes none (ADR-021). A run is bounded
    # by dev_agent_timeout_seconds and the guardrail gates.
    dev_agent_timeout_seconds: int = 1800
    dev_agent_max_attempts: int = 1
    dev_agent_repo_dir: str = "/tmp/dev-agent/repo"
    dev_agent_work_root: str = "/tmp/dev-agent/worktrees"
    dev_agent_poll_batch_size: int = 5
    dev_agent_confidence_threshold: float = 0.6
    dev_agent_verify_threshold: float = 0.6
    # Guardrail gates (ADR-020). These run inside the agent's worktree, so
    # they see its changes; a failure escalates the run to NEEDS_HUMAN rather
    # than shipping. Commands are configurable because the gate is about the
    # project's own definition of green, not a hardcoded one.
    # Run through `python -m` so they resolve to the interpreter executing the
    # job -- a bare `ruff`/`mypy` is not on PATH in a fresh worktree.
    dev_agent_test_command: str = "python -m pytest -q"
    dev_agent_lint_command: str = "python -m ruff check ."
    dev_agent_typecheck_command: str = "python -m mypy meeting_notes"
    dev_agent_gate_timeout_seconds: int = 900
    dev_agent_max_diff_files: int = 10
    dev_agent_max_diff_lines: int = 600
    github_owner: str = ""
    github_repo: str = ""
    github_token: str = ""

    # Both Memgraph vector indexes are configured for 768. Changing this means
    # migrating both indexes, so it is not a knob to turn casually.
    embedding_dimension: int = 768

    # ─── Postgres (ADR-015) ───────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 55432
    postgres_db: str = "meeting_memory"
    postgres_user: str = "meeting_notes"
    postgres_password: str = ""
    # Blank means local Postgres; set means the Cloud SQL connector.
    cloud_sql_connection_name: str = ""

    # ─── Memgraph ─────────────────────────────────────────────────────────
    memgraph_host: str = "localhost"
    memgraph_port: int = 57687
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
    # Shared machine secret gating POST /webhook/jira/sync. NOT a Jira
    # credential and not per-person: Jira identity is jira_email/jira_api_token
    # above, one service account for the whole deployment. This only answers
    # "may you make this service spend its Jira quota", because that route
    # costs a full REST sweep per call while the event route beside it cannot
    # be made to write anything a caller chooses.
    #
    # Cloud Run IAM with an OIDC caller is the stronger gate and should become
    # the primary one once Terraform grows a Cloud Scheduler job. This stays as
    # defence in depth rather than being replaced by it.
    jira_sync_trigger_token: str = ""

    # ─── Governance ───────────────────────────────────────────────────────
    fact_min_confidence: float = 0.5
    person_roster_path: str = ""
    access_policy_file: str = ""

    # ─── Pipeline tuning ──────────────────────────────────────────────────
    classifier_score_threshold: float = 0.40
    pipeline_batch_size: int = 50
    graph_write_concurrency: int = 3
    # Embeddings are independent calls at ~12s each; issuing them one at a
    # time made a 16-action meeting spend >3 minutes embedding alone.
    embedding_concurrency: int = 8

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
