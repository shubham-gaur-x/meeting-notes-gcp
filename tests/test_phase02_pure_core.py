"""Phase 2 — the pure core. No I/O, no network, no database.

Every test here runs with no GCP, no Postgres, no Memgraph and no LLM.
"""

from __future__ import annotations

import pytest

from meeting_notes.config import Settings

# ─── config ───────────────────────────────────────────────────────────────────


def test_settings_read_from_an_explicit_mapping_not_the_process_env() -> None:
    """Settings must be constructible from an explicit dict so tests never
    depend on the ambient environment."""
    s = Settings(GCP_PROJECT_ID="proj", LLM_BACKEND="fake")
    assert s.gcp_project_id == "proj"
    assert s.llm_backend == "fake"


def test_settings_default_to_the_tier_zero_backend() -> None:
    """A clone with no .env at all must default to the offline backend —
    that is what makes `make demo` work with no credentials (ADR-014)."""
    assert Settings(_env_file=None).llm_backend == "fake"


def test_settings_reject_an_unknown_llm_backend() -> None:
    with pytest.raises(ValueError):
        Settings(LLM_BACKEND="not-a-backend")


def test_embedding_dimension_is_768() -> None:
    """Both Memgraph vector indexes are built for 768. Changing this without
    migrating them silently breaks semantic search (CLAUDE.md)."""
    assert Settings(_env_file=None).embedding_dimension == 768


def test_jira_is_disabled_by_default() -> None:
    """Tier 0 and tier 1 must run the pipeline fully and create no tickets."""
    assert Settings(_env_file=None).jira_enabled is False


def test_cloud_sql_connection_name_blank_means_local() -> None:
    """ADR-015: db.py branches on this to pick its connection mode."""
    assert Settings(_env_file=None).cloud_sql_connection_name == ""
