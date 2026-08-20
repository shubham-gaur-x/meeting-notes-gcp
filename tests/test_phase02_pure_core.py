"""Phase 2 — the pure core. No I/O, no network, no database.

Every test here runs with no GCP, no Postgres, no Memgraph and no LLM.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from meeting_notes.config import Settings
from meeting_notes.models import (
    ActionItem,
    Decision,
    ExtractedMeeting,
    RawEmail,
    StagedRecord,
)
from meeting_notes.utils import (
    extract_ticket_keys,
    priority_from_due,
    strip_json_fences,
    uuid5_id,
)

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


# ─── utils ────────────────────────────────────────────────────────────────────


def test_uuid5_id_is_deterministic() -> None:
    """The whole MERGE-not-CREATE strategy rests on this. Same input, same id,
    forever — including across processes and machines."""
    assert uuid5_id("meeting", "abc") == uuid5_id("meeting", "abc")


def test_uuid5_id_separates_namespaces() -> None:
    assert uuid5_id("meeting", "abc") != uuid5_id("person", "abc")


def test_uuid5_id_matches_the_value_v5_produces() -> None:
    """Pinned against v5's exact construction: a uuid5 of the namespace string
    under the DNS namespace, then a uuid5 of the value under THAT.

    Not `uuid5(NS, f"{namespace}:{value}")` — an easy and silent mistake to
    make, and it would fork every id in a restored graph so MERGE starts
    creating duplicates instead of matching.
    """
    import uuid

    ns = uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), "meeting")
    assert uuid5_id("meeting", "abc") == str(uuid.uuid5(ns, "abc"))


def test_strip_json_fences_removes_a_fenced_block() -> None:
    """Local models wrap JSON in ```json fences despite being told not to.
    Found by live testing in v5, not by unit tests (CLAUDE.md)."""
    assert strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_json_fences_leaves_bare_json_alone() -> None:
    assert strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_strip_json_fences_on_empty_input() -> None:
    assert strip_json_fences("") == ""


def test_extract_ticket_keys_finds_jira_style_keys() -> None:
    assert extract_ticket_keys("fixes SCRUM-12 and PROJ-3") == ["SCRUM-12", "PROJ-3"]


def test_extract_ticket_keys_dedupes_preserving_order() -> None:
    assert extract_ticket_keys("SCRUM-12, PROJ-3, SCRUM-12") == ["SCRUM-12", "PROJ-3"]


def test_extract_ticket_keys_on_none_is_empty() -> None:
    assert extract_ticket_keys(None) == []


def test_priority_from_due_escalates_as_the_date_approaches() -> None:
    """v5's actual boundaries: <= 14 days high, <= 60 medium, beyond that low."""
    today = date.today()
    assert priority_from_due(today + timedelta(days=1)) == "high"
    assert priority_from_due(today + timedelta(days=14)) == "high"
    assert priority_from_due(today + timedelta(days=30)) == "medium"
    assert priority_from_due(today + timedelta(days=90)) == "low"


def test_priority_from_due_with_no_date_is_low() -> None:
    """Deliberately 'low', not 'medium' — an item with no due date is not
    urgent. Matches v5."""
    assert priority_from_due(None) == "low"


# ─── models (ADR-018) ─────────────────────────────────────────────────────────


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
    with pytest.raises(ValueError):
        StagedRecord(
            id="1",
            source_id="x",
            source_type="carrier-pigeon",  # type: ignore[arg-type]
            payload={},
            fetched_at="2026-08-20T00:00:00Z",
        )


def test_raw_models_survive_as_adapter_parse_targets() -> None:
    """ADR-018 is a storage change, not a loss of typing. The typed models
    still validate a payload as strictly as v5 did."""
    email = RawEmail.model_validate(
        {
            "id": "1",
            "source_id": "abc",
            "subject": "s",
            "from_email": "a@b.c",
            "to_emails": ["d@e.f"],
            "body": "b",
            "received_at": "2026-08-20T00:00:00Z",
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
            "title": "t",
            "kind": "meeting",
            "platform": "meet",
            "date": "2026-08-20",
            "summary": "s",
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
            "title": "t",
            "kind": "meeting",
            "platform": "meet",
            "date": "2026-08-20",
            "summary": "s",
            "invented_field": "???",
        }
    )
    assert not hasattr(meeting, "invented_field")
