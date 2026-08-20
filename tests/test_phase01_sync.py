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
    select_restore_pair,
    snapshot_name,
    sync_down,
    sync_up,
    wait_for_memgraph,
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
    sync_down("personal", "proj", "proj-backups", "us-central1-a", now=FIXED, runner=runner)

    export_at = next(i for i, c in enumerate(runner.calls) if "export" in " ".join(c))
    destroy_at = next(i for i, c in enumerate(runner.calls) if "destroy" in " ".join(c))
    assert export_at < destroy_at, "export must complete before destroy is issued"


def test_sync_down_never_destroys_when_the_sql_export_fails() -> None:
    """The single most important test in this file. A failed export followed by
    a destroy is permanent, unrecoverable data loss."""
    runner = RecordingRunner({"sql export": _fail("quota exceeded")})

    with pytest.raises(SyncError, match="export"):
        sync_down("personal", "proj", "proj-backups", "us-central1-a", now=FIXED, runner=runner)

    assert not runner.ran("destroy"), "destroy must not run after a failed export"


def test_sync_down_never_destroys_when_the_snapshot_fails() -> None:
    runner = RecordingRunner({"disks snapshot": _fail("disk busy")})

    with pytest.raises(SyncError, match="snapshot"):
        sync_down("personal", "proj", "proj-backups", "us-central1-a", now=FIXED, runner=runner)

    assert not runner.ran("destroy"), "destroy must not run after a failed snapshot"


def test_sync_down_never_destroys_when_the_export_object_is_missing() -> None:
    """gcloud sql export can exit 0 having written nothing usable. Verify the
    object, do not trust the exit code."""
    runner = RecordingRunner({"storage objects describe": _fail("not found")})

    with pytest.raises(SyncError):
        sync_down("personal", "proj", "proj-backups", "us-central1-a", now=FIXED, runner=runner)

    assert not runner.ran("destroy")


def test_sync_down_passes_zone_to_the_disk_snapshot_command() -> None:
    """`gcloud compute disks snapshot` operates on a zonal resource and 400s
    with "Underspecified resource" without --zone — confirmed live against
    the real CLI. `snapshots describe` right after is a global resource and
    correctly takes no zone; this test only checks the snapshot-create call."""
    runner = RecordingRunner(
        {"sql export": _ok(), "disks snapshot": _ok(), "snapshots describe": _ok("READY")}
    )
    sync_down("personal", "proj", "proj-backups", "us-central1-a", now=FIXED, runner=runner)

    snapshot_cmd = next(c for c in runner.calls if "disks" in c and "snapshot" in c)
    assert "--zone=us-central1-a" in snapshot_cmd


def test_sync_down_never_destroys_when_the_snapshot_is_not_ready() -> None:
    """`gcloud compute disks snapshot` exits 0 as soon as the snapshot is
    created, which is before it holds usable data. FAILED is not a state we may
    destroy on top of."""
    runner = RecordingRunner({"snapshots describe": _ok("FAILED")})

    with pytest.raises(SyncError, match="READY"):
        sync_down("personal", "proj", "proj-backups", "us-central1-a", now=FIXED, runner=runner)

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
    """First ever run: no snapshots, no exports. Must still succeed.

    `gcloud storage ls` on a prefix with zero objects exits 1 with "One or
    more URLs matched no objects" rather than exiting 0 with empty output —
    confirmed against the real CLI during Phase 1's live validation, not
    assumed. An earlier version of this test mocked exit 0, which passed
    against the mock but failed the very first real sync-up.
    """
    runner = RecordingRunner(
        {
            "snapshots list": _ok("[]"),
            "storage ls": _fail("One or more URLs matched no objects."),
        }
    )
    sync_up("personal", "proj", "proj-backups", runner=runner)

    apply_cmd = next(c for c in runner.calls if "apply" in " ".join(c))
    assert "memgraph_restore_snapshot=" in " ".join(apply_cmd)
    assert not runner.ran("sql import"), "nothing to import on a virgin project"


def test_sync_up_raises_on_a_genuine_storage_ls_failure() -> None:
    """Only the specific 'matched no objects' message is tolerated. Any other
    storage ls failure (auth, wrong bucket, permissions) must still raise."""
    runner = RecordingRunner(
        {"snapshots list": _ok("[]"), "storage ls": _fail("403 Forbidden")}
    )

    with pytest.raises(SyncError, match="Cloud SQL exports"):
        sync_up("personal", "proj", "proj-backups", runner=runner)


# ─── restore pairing (ADR-017 follow-up) ──────────────────────────────────────


def test_restore_pair_prefers_the_newest_matched_timestamp() -> None:
    """The bug this exists to prevent.

    A sync-down that writes its export and then fails before the snapshot
    leaves an export with no partner — observed for real during Phase 1
    validation. Picking "latest export" and "latest snapshot" independently
    would then restore Postgres from the orphan while the graph came from an
    older snapshot: the database claims rows the graph never received.
    """
    exports = [
        "gs://b/cloudsql/meeting-memory-20260801t000000z.sql.gz",
        "gs://b/cloudsql/meeting-memory-20260820t022231z.sql.gz",  # orphan, newer
    ]
    snapshots = ["memgraph-data-20260801t000000z"]

    plan = select_restore_pair(exports, snapshots)

    assert plan.paired
    assert "20260801t000000z" in (plan.export or "")
    assert plan.snapshot == "memgraph-data-20260801t000000z"


def test_restore_pair_picks_the_newest_when_several_match() -> None:
    exports = [
        "gs://b/cloudsql/meeting-memory-20260801t000000z.sql.gz",
        "gs://b/cloudsql/meeting-memory-20260820t024109z.sql.gz",
    ]
    snapshots = ["memgraph-data-20260801t000000z", "memgraph-data-20260820t024109z"]

    plan = select_restore_pair(exports, snapshots)

    assert plan.paired
    assert "20260820t024109z" in (plan.export or "")
    assert plan.snapshot == "memgraph-data-20260820t024109z"


def test_restore_pair_falls_back_loudly_when_nothing_matches() -> None:
    """No matched pair must NOT mean discarding usable data — an export can
    outlive its snapshot or vice versa. Restore the newest of each, but say
    plainly that they are unpaired so the mismatch is visible."""
    exports = ["gs://b/cloudsql/meeting-memory-20260820t000000z.sql.gz"]
    snapshots = ["memgraph-data-20260801t000000z"]

    plan = select_restore_pair(exports, snapshots)

    assert not plan.paired
    assert "20260820t000000z" in (plan.export or "")
    assert plan.snapshot == "memgraph-data-20260801t000000z"


def test_restore_pair_on_a_virgin_project_is_empty_but_paired() -> None:
    """Nothing to restore is a legitimate, consistent state — not a mismatch."""
    plan = select_restore_pair([], [])
    assert plan.export is None
    assert plan.snapshot is None
    assert plan.paired


def test_restore_pair_ignores_unparseable_names() -> None:
    """A stray object in the bucket must not be mistaken for a backup."""
    plan = select_restore_pair(
        ["gs://b/cloudsql/notes.txt", "gs://b/cloudsql/meeting-memory-20260801t000000z.sql.gz"],
        ["memgraph-data-20260801t000000z", "some-unrelated-snapshot"],
    )
    assert plan.paired
    assert "20260801t000000z" in (plan.export or "")


def test_sync_up_restores_the_matched_pair_not_the_newest_orphan() -> None:
    """End-to-end: the orphan export must not reach `gcloud sql import`."""
    snapshots = json.dumps(
        [{"name": "memgraph-data-20260801t000000z", "creationTimestamp": "2026-08-01T00:00:00Z"}]
    )
    listing = (
        "gs://b/cloudsql/meeting-memory-20260801t000000z.sql.gz\n"
        "gs://b/cloudsql/meeting-memory-20260820t022231z.sql.gz\n"
    )
    runner = RecordingRunner({"snapshots list": _ok(snapshots), "storage ls": _ok(listing)})

    sync_up("personal", "proj", "proj-backups", runner=runner)

    import_cmd = next(c for c in runner.calls if "import" in " ".join(c))
    joined = " ".join(import_cmd)
    assert "20260801t000000z" in joined
    assert "20260820t022231z" not in joined, "restored the orphan instead of the matched pair"


# ─── waiting for Memgraph to actually be serving ──────────────────────────────


def test_wait_for_memgraph_returns_when_the_marker_appears() -> None:
    """terraform reports the VM ready as soon as the API says RUNNING, which is
    well before Docker has pulled the images. The startup script echoes a
    marker when the stack is actually up; poll the serial console for it."""
    slept: list[float] = []
    runner = RecordingRunner({"serial-port-output": _ok("...\nMemgraph bootstrap complete.\n")})

    ok = wait_for_memgraph(
        "vm", "us-central1-a", "proj", runner=runner, sleeper=slept.append, attempts=5, delay=1.0
    )

    assert ok
    assert slept == [], "should not sleep when the marker is already present"


def test_wait_for_memgraph_polls_until_the_marker_shows_up() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def runner(cmd):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] < 3:
            return _ok("still booting")
        return _ok("Memgraph bootstrap complete.")

    ok = wait_for_memgraph(
        "vm", "us-central1-a", "proj", runner=runner, sleeper=slept.append, attempts=5, delay=2.0
    )

    assert ok
    assert slept == [2.0, 2.0], "one sleep between each failed poll"


def test_wait_for_memgraph_gives_up_without_raising() -> None:
    """A VM that never finishes bootstrapping is a real problem, but the tier
    IS up and billing by this point — raising would strand it. Report False
    and let sync_up surface it as a visible warning instead."""
    slept: list[float] = []
    runner = RecordingRunner({"serial-port-output": _ok("no marker here")})

    ok = wait_for_memgraph(
        "vm", "us-central1-a", "proj", runner=runner, sleeper=slept.append, attempts=3, delay=1.0
    )

    assert not ok
    assert len(slept) == 2, "sleeps between attempts, not after the last one"


def test_wait_for_memgraph_tolerates_a_failing_serial_console_read() -> None:
    """The console is not readable in the first seconds after boot. A failed
    read is 'not ready yet', not a hard error."""
    slept: list[float] = []
    runner = RecordingRunner({"serial-port-output": _fail("instance not ready")})

    assert not wait_for_memgraph(
        "vm", "us-central1-a", "proj", runner=runner, sleeper=slept.append, attempts=2, delay=1.0
    )


def test_sync_up_waits_for_memgraph_when_a_zone_is_known() -> None:
    """sync-up must not announce the tier is serving before it is."""
    runner = RecordingRunner(
        {
            "snapshots list": _ok("[]"),
            "storage ls": _fail("One or more URLs matched no objects."),
            "serial-port-output": _ok("Memgraph bootstrap complete."),
        }
    )

    steps = sync_up("personal", "proj", "proj-backups", zone="us-central1-a", runner=runner)

    assert runner.ran("get-serial-port-output")
    assert any("serving Bolt" in s for s in steps)


def test_sync_up_skips_the_wait_when_no_zone_is_configured() -> None:
    """A missing GCP_ZONE degrades to skipping the health wait rather than
    blocking a session that is otherwise fine."""
    runner = RecordingRunner(
        {"snapshots list": _ok("[]"), "storage ls": _fail("One or more URLs matched no objects.")}
    )

    steps = sync_up("personal", "proj", "proj-backups", runner=runner)

    assert not runner.ran("get-serial-port-output")
    assert any("created" in s for s in steps)
