"""Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016.

Every test runs with no gcloud, no terraform, and no network. Commands are
injected as a callable so the destructive paths are exercised without
destroying anything.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime

import pytest

from scripts.sync import (
    SyncError,
    backup_uri,
    export_object_name,
    select_latest,
    snapshot_name,
    sync_down,
    sync_up,
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


def _ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str = "boom") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


class RecordingRunner:
    """Records every command and replays scripted responses."""

    def __init__(self, responses: dict[str, subprocess.CompletedProcess[str]]) -> None:
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, cmd) -> subprocess.CompletedProcess[str]:  # type: ignore[no-untyped-def]
        self.calls.append(list(cmd))
        for fragment, response in self.responses.items():
            if fragment in " ".join(cmd):
                return response
        return _ok()

    def ran(self, fragment: str) -> bool:
        return any(fragment in " ".join(c) for c in self.calls)


def test_sync_down_exports_before_it_destroys() -> None:
    # `snapshots describe` must report READY, or the status gate raises before
    # destroy is ever reached — which is the behaviour the next tests assert.
    runner = RecordingRunner(
        {"sql export": _ok(), "disks snapshot": _ok(), "snapshots describe": _ok("READY")}
    )
    sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    export_at = next(i for i, c in enumerate(runner.calls) if "export" in " ".join(c))
    destroy_at = next(i for i, c in enumerate(runner.calls) if "destroy" in " ".join(c))
    assert export_at < destroy_at, "export must complete before destroy is issued"


def test_sync_down_never_destroys_when_the_sql_export_fails() -> None:
    """The single most important test in this file. A failed export followed by
    a destroy is permanent, unrecoverable data loss."""
    runner = RecordingRunner({"sql export": _fail("quota exceeded")})

    with pytest.raises(SyncError, match="export"):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy"), "destroy must not run after a failed export"


def test_sync_down_never_destroys_when_the_snapshot_fails() -> None:
    runner = RecordingRunner({"disks snapshot": _fail("disk busy")})

    with pytest.raises(SyncError, match="snapshot"):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy"), "destroy must not run after a failed snapshot"


def test_sync_down_never_destroys_when_the_export_object_is_missing() -> None:
    """gcloud sql export can exit 0 having written nothing usable. Verify the
    object, do not trust the exit code."""
    runner = RecordingRunner({"storage objects describe": _fail("not found")})

    with pytest.raises(SyncError):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy")


def test_sync_down_never_destroys_when_the_snapshot_is_not_ready() -> None:
    """`gcloud compute disks snapshot` exits 0 as soon as the snapshot is
    created, which is before it holds usable data. FAILED is not a state we may
    destroy on top of."""
    runner = RecordingRunner({"snapshots describe": _ok("FAILED")})

    with pytest.raises(SyncError, match="READY"):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy")


def test_sync_up_passes_the_latest_snapshot_to_terraform() -> None:
    snapshots = json.dumps(
        [{"name": "memgraph-data-20260801t000000z", "creationTimestamp": "2026-08-01T00:00:00Z"}]
    )
    runner = RecordingRunner({"snapshots list": _ok(snapshots)})
    sync_up("personal", "proj", "proj-backups", runner=runner)

    apply_cmd = next(c for c in runner.calls if "apply" in " ".join(c))
    assert "memgraph_restore_snapshot=memgraph-data-20260801t000000z" in " ".join(apply_cmd)


def test_sync_up_on_a_virgin_project_requests_an_empty_snapshot() -> None:
    """First ever run: no snapshots, no exports. Must still succeed."""
    runner = RecordingRunner({"snapshots list": _ok("[]"), "storage ls": _ok("")})
    sync_up("personal", "proj", "proj-backups", runner=runner)

    apply_cmd = next(c for c in runner.calls if "apply" in " ".join(c))
    assert "memgraph_restore_snapshot=" in " ".join(apply_cmd)
    assert not runner.ran("sql import"), "nothing to import on a virgin project"
