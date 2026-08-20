"""Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016.

Every test runs with no gcloud, no terraform, and no network. Commands are
injected as a callable so the destructive paths are exercised without
destroying anything.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.sync import (
    SyncError,
    backup_uri,
    export_object_name,
    select_latest,
    snapshot_name,
)

FIXED = datetime(2026, 8, 19, 12, 45, 0, tzinfo=UTC)


def test_export_object_name_is_timestamped_and_sorts_chronologically() -> None:
    earlier = export_object_name(datetime(2026, 8, 19, 1, 0, 0, tzinfo=UTC))
    later = export_object_name(FIXED)
    assert earlier < later, "lexical sort must match chronological order"
    assert later.endswith(".sql.gz")
    assert later.startswith("cloudsql/")


def test_snapshot_name_is_a_legal_gce_resource_name() -> None:
    """GCE names must match [a-z]([-a-z0-9]*[a-z0-9])? and be <= 63 chars."""
    import re

    name = snapshot_name(FIXED)
    assert re.fullmatch(r"[a-z]([-a-z0-9]*[a-z0-9])?", name), name
    assert len(name) <= 63


def test_snapshot_names_sort_chronologically() -> None:
    earlier = snapshot_name(datetime(2026, 8, 19, 1, 0, 0, tzinfo=UTC))
    assert earlier < snapshot_name(FIXED)


def test_select_latest_picks_the_most_recent() -> None:
    items = [
        {"name": "old", "creationTimestamp": "2026-08-01T00:00:00Z"},
        {"name": "newest", "creationTimestamp": "2026-08-19T00:00:00Z"},
        {"name": "middle", "creationTimestamp": "2026-08-10T00:00:00Z"},
    ]
    assert select_latest(items, "creationTimestamp", "name") == "newest"


def test_select_latest_returns_none_on_empty() -> None:
    """The first-ever sync-up has no snapshot and no export. Not an error."""
    assert select_latest([], "creationTimestamp", "name") is None


def test_select_latest_raises_on_a_malformed_record() -> None:
    """A missing timestamp means gcloud changed its output shape. Fail loudly
    rather than silently restoring the wrong backup."""
    with pytest.raises(SyncError):
        select_latest([{"name": "x"}], "creationTimestamp", "name")


def test_backup_uri_builds_a_gs_url() -> None:
    assert backup_uri("proj-backups", "cloudsql/x.sql.gz") == "gs://proj-backups/cloudsql/x.sql.gz"
