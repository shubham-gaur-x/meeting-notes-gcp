#!/usr/bin/env python3
"""Phase 1 — bring the ephemeral tier up for a sync session, then tear it down.

Under ADR-016 the Cloud SQL instance and the Memgraph VM exist only while
actively syncing. Everything else is durable and cheap. This script owns the
transition in both directions.

    make sync-up     apply the ephemeral tier, restoring the last backup
    make sync-down   back up, VERIFY the backup, then destroy

The verification between "back up" and "destroy" is the whole point. A failed
export that still proceeds to destroy is permanent data loss, so every path to
`terraform destroy` runs through a check that raises rather than returns.

Like scripts/auth_spike.py and scripts/doctor.py, this predates
meeting_notes/config.py and takes its environment as a parameter.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

# A command runner, injected so tests never invoke gcloud or terraform.
Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

EXPORT_PREFIX = "cloudsql"
SNAPSHOT_PREFIX = "memgraph-data"


class SyncError(RuntimeError):
    """A sync step failed. Raised rather than returned so no caller can
    accidentally continue to a destructive step after a failure."""


def _stamp(now: datetime) -> str:
    """Compact UTC timestamp. Lowercase so it is legal in a GCE resource name,
    and fixed-width so lexical sort equals chronological sort."""
    return now.strftime("%Y%m%dt%H%M%Sz")


def export_object_name(now: datetime) -> str:
    """GCS object path for a Cloud SQL export."""
    return f"{EXPORT_PREFIX}/meeting-memory-{_stamp(now)}.sql.gz"


def snapshot_name(now: datetime) -> str:
    """GCE snapshot name for the Memgraph data disk.

    Must match [a-z]([-a-z0-9]*[a-z0-9])? and be at most 63 characters.
    """
    return f"{SNAPSHOT_PREFIX}-{_stamp(now)}"


def backup_uri(bucket: str, obj: str) -> str:
    return f"gs://{bucket}/{obj}"


def select_latest(
    items: list[dict[str, str]], key: str, name_field: str
) -> str | None:
    """Name of the most recent item, or None if there are none.

    None is a legitimate answer — the first-ever sync-up has no backup to
    restore. A record missing its timestamp is NOT legitimate: it means the
    gcloud output shape changed, and guessing would restore the wrong backup.
    """
    if not items:
        return None

    try:
        newest = max(items, key=lambda item: item[key])
    except KeyError as exc:
        raise SyncError(
            f"Record is missing {key!r} — gcloud output shape may have changed. "
            f"Refusing to guess which backup is newest."
        ) from exc

    return newest[name_field]


# ─── choosing what to restore from ────────────────────────────────────────────

# The stamp both artifact names embed, e.g. 20260820t024109z. Anchored to the
# exact shape _stamp() produces so a stray object in the bucket cannot be
# mistaken for a backup.
_STAMP_RE = re.compile(r"\d{8}t\d{6}z")


def stamp_of(name: str) -> str | None:
    """The shared timestamp in an export object path or a snapshot name."""
    match = _STAMP_RE.search(name)
    return match.group(0) if match else None


@dataclass(frozen=True)
class RestorePlan:
    export: str | None
    snapshot: str | None
    paired: bool


def select_restore_pair(exports: list[str], snapshots: list[str]) -> RestorePlan:
    """Choose the export and snapshot to restore the ephemeral tier from.

    `sync_down` stamps both artifacts with the same timestamp, so an export
    and a snapshot sharing a stamp are a matched pair: Postgres holds the
    staged rows and their `processed` flags, and the graph holds exactly what
    was built from them.

    Selecting "newest export" and "newest snapshot" independently is wrong.
    A sync-down that writes its export and then fails before the snapshot
    leaves an orphan export — not hypothetical, it happened during Phase 1
    validation. Restoring that newer orphan against an older snapshot gives a
    database claiming records the graph never received: a silent
    inconsistency, and a miserable one to diagnose months later.

    So: prefer the newest stamp present on both sides. If nothing matches,
    still restore the newest of each rather than discarding usable data — an
    export can outlive its snapshot once the bucket's lifecycle rule starts
    reclaiming — but report `paired = False` so the caller can say so out loud
    instead of hiding it.
    """
    by_stamp_export = {s: e for e in exports if (s := stamp_of(e))}
    by_stamp_snapshot = {s: n for n in snapshots if (s := stamp_of(n))}

    both = set(by_stamp_export) & set(by_stamp_snapshot)
    if both:
        newest = max(both)
        return RestorePlan(by_stamp_export[newest], by_stamp_snapshot[newest], paired=True)

    newest_export = by_stamp_export[max(by_stamp_export)] if by_stamp_export else None
    newest_snapshot = by_stamp_snapshot[max(by_stamp_snapshot)] if by_stamp_snapshot else None

    # Nothing on either side is a consistent state, not a mismatch: a virgin
    # project has nothing to restore and nothing to be wrong about.
    paired = newest_export is None and newest_snapshot is None
    return RestorePlan(newest_export, newest_snapshot, paired=paired)


# ─── orchestration ────────────────────────────────────────────────────────────


def run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Default runner. Captures output so failures can be reported with context."""
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)


def _require(
    result: subprocess.CompletedProcess[str], what: str
) -> subprocess.CompletedProcess[str]:
    """Raise unless the command succeeded.

    Every destructive step in sync_down is preceded by one of these. Returning a
    status instead of raising would let a caller forget to check it, which is
    exactly the mistake that loses a month of graph data.
    """
    if result.returncode != 0:
        raise SyncError(f"{what} failed (exit {result.returncode}): {result.stderr.strip()}")
    return result


def _tf(module: str, *args: str, env_name: str) -> list[str]:
    return [
        "terraform",
        f"-chdir=terraform/{module}",
        *args,
        f"-var-file=../envs/{env_name}.tfvars",
    ]


def terraform_output(module: str, name: str, *, runner: Runner = run) -> str:
    result = _require(
        runner(["terraform", f"-chdir=terraform/{module}", "output", "-raw", name]),
        f"reading terraform output {name!r}",
    )
    return result.stdout.strip()


def sync_down(
    env_name: str,
    project_id: str,
    bucket: str,
    zone: str,
    *,
    now: datetime,
    runner: Runner = run,
) -> list[str]:
    """Back up, verify the backup, then destroy the ephemeral tier.

    Ordering is a safety property, not a preference. Each step raises on
    failure, so `terraform destroy` at the end is only ever reached when every
    preceding verification passed.
    """
    steps: list[str] = []

    instance = terraform_output("ephemeral", "cloudsql_connection_name", runner=runner)
    instance_name = instance.split(":")[-1]
    disk = terraform_output("ephemeral", "memgraph_disk_name", runner=runner)

    # 1. Export Cloud SQL to the durable bucket.
    obj = export_object_name(now)
    uri = backup_uri(bucket, obj)
    _require(
        runner(
            [
                "gcloud", "sql", "export", "sql", instance_name, uri,
                "--database=meeting_memory", f"--project={project_id}",
            ]
        ),
        "Cloud SQL export",
    )
    steps.append(f"exported Cloud SQL to {uri}")

    # 2. Verify the object exists. `gcloud sql export` has been known to exit 0
    #    while producing nothing usable; the exit code alone is not evidence.
    _require(
        runner(["gcloud", "storage", "objects", "describe", uri, f"--project={project_id}"]),
        f"verifying the export object at {uri}",
    )
    steps.append("verified the export object exists")

    # 3. Snapshot the Memgraph data disk. `disks snapshot` operates on a zonal
    #    resource and 400s with "Underspecified resource" without --zone —
    #    unlike `snapshots describe` below, which is a global resource type
    #    and takes no zone at all. Confirmed live, not assumed from docs.
    snap = snapshot_name(now)
    _require(
        runner(
            [
                "gcloud", "compute", "disks", "snapshot", disk,
                f"--snapshot-names={snap}", f"--zone={zone}", f"--project={project_id}",
            ]
        ),
        "Memgraph disk snapshot",
    )
    steps.append(f"snapshotted the Memgraph disk as {snap}")

    # 4. Verify the snapshot is READY, not merely created.
    result = _require(
        runner(
            [
                "gcloud", "compute", "snapshots", "describe", snap,
                "--format=value(status)", f"--project={project_id}",
            ]
        ),
        f"verifying snapshot {snap}",
    )
    if result.stdout.strip() not in ("READY", "UPLOADING"):
        raise SyncError(f"snapshot {snap} is {result.stdout.strip()!r}, not READY")
    steps.append("verified the snapshot")

    # 5. Only now: tear down. Everything above raised on failure, so reaching
    #    this line means both backups are on durable storage.
    _require(
        runner(_tf("ephemeral", "destroy", "-auto-approve", env_name=env_name)),
        "terraform destroy of the ephemeral tier",
    )
    steps.append("destroyed the ephemeral tier — billing for it is now $0")

    return steps


def wait_for_memgraph(
    instance: str,
    zone: str,
    project_id: str,
    *,
    runner: Runner = run,
    sleeper: Callable[[float], None] = time.sleep,
    attempts: int = 40,
    delay: float = 15.0,
) -> bool:
    """Block until the Memgraph stack is actually serving, or give up.

    Terraform reports the VM ready as soon as the Compute API says RUNNING,
    which is roughly two minutes before Docker has finished pulling the images
    — so `sync-up` used to announce "ephemeral tier is up" while a connection
    to Bolt would still be refused.

    Polls the serial console for the marker `terraform/ephemeral/startup.sh`
    echoes on completion. That is deliberately cheaper than polling Bolt
    itself, which would require standing up an IAP tunnel just to health-check.

    Returns False rather than raising on timeout: by this point the tier is
    created and billing, so aborting would strand it. The caller surfaces the
    failure as a visible warning instead.
    """
    marker = "Memgraph bootstrap complete"
    for attempt in range(attempts):
        result = runner(
            [
                "gcloud", "compute", "instances", "get-serial-port-output", instance,
                f"--zone={zone}", f"--project={project_id}",
            ]
        )
        # A failed read is "not ready yet", not a hard error — the console is
        # briefly unreadable in the first seconds after boot.
        if result.returncode == 0 and marker in result.stdout:
            return True
        if attempt < attempts - 1:
            sleeper(delay)
    return False


def sync_up(
    env_name: str,
    project_id: str,
    bucket: str,
    *,
    zone: str = "",
    runner: Runner = run,
) -> list[str]:
    """Recreate the ephemeral tier, restoring the newest matched backup pair."""
    steps: list[str] = []

    # 1. List both sides of the backup BEFORE applying, so the export and the
    #    snapshot can be chosen as a matched pair rather than independently.
    result = _require(
        runner(
            [
                "gcloud", "compute", "snapshots", "list",
                f"--filter=name~^{SNAPSHOT_PREFIX}-", "--format=json",
                f"--project={project_id}",
            ]
        ),
        "listing Memgraph snapshots",
    )
    snapshots = [s["name"] for s in json.loads(result.stdout or "[]") if "name" in s]

    # `gcloud storage ls` on a prefix with zero objects exits 1 with "One or
    # more URLs matched no objects" rather than exiting 0 with empty output —
    # confirmed against the real CLI, not assumed. A virgin backup bucket is a
    # legitimate first-sync-up state, so that specific message is not a
    # failure; any other non-zero exit (auth, wrong bucket, permissions)
    # still raises through _require.
    ls_result = runner(
        ["gcloud", "storage", "ls", f"gs://{bucket}/{EXPORT_PREFIX}/", f"--project={project_id}"]
    )
    if ls_result.returncode != 0 and "matched no objects" not in ls_result.stderr:
        _require(ls_result, "listing Cloud SQL exports")
    exports = [line.strip() for line in ls_result.stdout.splitlines() if line.strip().endswith(".sql.gz")]

    plan = select_restore_pair(exports, snapshots)
    if not plan.paired:
        # Loud, not silent. The two stores are about to disagree about which
        # point in time they represent, and only the operator can judge
        # whether that is acceptable.
        steps.append(
            "WARNING: no matching export/snapshot pair — restoring "
            f"Postgres from {plan.export} and the graph from {plan.snapshot}. "
            "These are from different sync-downs and may disagree."
        )

    steps.append(
        f"restoring Memgraph from {plan.snapshot}"
        if plan.snapshot
        else "no Memgraph snapshot found — starting from an empty graph"
    )

    # 2. Apply, handing Terraform the snapshot to restore from.
    _require(
        runner(
            _tf(
                "ephemeral",
                "apply",
                "-auto-approve",
                f"-var=memgraph_restore_snapshot={plan.snapshot or ''}",
                env_name=env_name,
            )
        ),
        "terraform apply of the ephemeral tier",
    )
    steps.append("ephemeral tier is created")

    # 2b. ...but "created" is not "serving". Wait for the container stack.
    if zone:
        instance_name = terraform_output("ephemeral", "memgraph_instance_name", runner=runner)
        if wait_for_memgraph(instance_name, zone, project_id, runner=runner):
            steps.append("Memgraph is serving Bolt")
        else:
            steps.append(
                "WARNING: Memgraph did not report a completed bootstrap. The VM is "
                "up and billing; check `gcloud compute instances "
                f"get-serial-port-output {instance_name} --zone={zone}`."
            )

    # 3. Import the paired Cloud SQL export.
    if plan.export:
        instance = terraform_output("ephemeral", "cloudsql_connection_name", runner=runner)
        _require(
            runner(
                [
                    "gcloud", "sql", "import", "sql", instance.split(":")[-1], plan.export,
                    "--database=meeting_memory", f"--project={project_id}", "--quiet",
                ]
            ),
            "Cloud SQL import",
        )
        steps.append(f"restored Cloud SQL from {plan.export}")
    else:
        steps.append("no Cloud SQL export found — starting from an empty database")

    return steps


# ─── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync",
        description="Bring the ephemeral tier up for a session, or tear it down. See ADR-016.",
    )
    parser.add_argument(
        "direction",
        choices=("up", "down"),
        help="up: apply and restore. down: back up, verify, destroy.",
    )
    parser.add_argument("--env", default="personal", help="which terraform env to act on")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from scripts.auth_spike import load_env_file

    load_env_file()
    import os

    project_id = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project_id:
        print("GCP_PROJECT_ID is unset. Put it in .env — see .env.example.")
        return 1

    zone = os.environ.get("GCP_ZONE", "").strip()
    if not zone:
        # Required for sync-down (a disk snapshot is zonal). For sync-up it is
        # only needed to poll the VM, so a missing zone degrades to skipping
        # that wait rather than blocking the session.
        if args.direction == "down":
            print("GCP_ZONE is unset. Put it in .env — see .env.example.")
            return 1
        print("  note: GCP_ZONE unset — skipping the wait for Memgraph to finish booting.")

    bucket = f"{project_id}-backups"

    try:
        steps = (
            sync_up(args.env, project_id, bucket, zone=zone)
            if args.direction == "up"
            else sync_down(args.env, project_id, bucket, zone, now=datetime.now(UTC))
        )
    except SyncError as exc:
        print(f"\n  sync {args.direction} FAILED: {exc}\n")
        if args.direction == "down":
            print("  The ephemeral tier is still UP and still billing.")
            print("  Fix the cause and re-run `make sync-down` — nothing was destroyed.\n")
        return 1

    print(f"\n  sync {args.direction} complete:")
    for step in steps:
        print(f"    - {step}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
