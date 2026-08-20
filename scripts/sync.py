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
import subprocess
from collections.abc import Callable, Sequence
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

    # 3. Snapshot the Memgraph data disk.
    snap = snapshot_name(now)
    _require(
        runner(
            [
                "gcloud", "compute", "disks", "snapshot", disk,
                f"--snapshot-names={snap}", f"--project={project_id}",
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


def sync_up(
    env_name: str,
    project_id: str,
    bucket: str,
    *,
    runner: Runner = run,
) -> list[str]:
    """Recreate the ephemeral tier, restoring the most recent backup."""
    steps: list[str] = []

    # 1. Find the newest Memgraph snapshot. None on a virgin project.
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
    snapshots = json.loads(result.stdout or "[]")
    latest_snapshot = select_latest(snapshots, "creationTimestamp", "name") or ""
    steps.append(
        f"restoring Memgraph from {latest_snapshot}"
        if latest_snapshot
        else "no Memgraph snapshot found — starting from an empty graph"
    )

    # 2. Apply, handing Terraform the snapshot to restore from.
    _require(
        runner(
            _tf(
                "ephemeral",
                "apply",
                "-auto-approve",
                f"-var=memgraph_restore_snapshot={latest_snapshot}",
                env_name=env_name,
            )
        ),
        "terraform apply of the ephemeral tier",
    )
    steps.append("ephemeral tier is up")

    # 3. Find the newest Cloud SQL export and import it.
    result = _require(
        runner(
            [
                "gcloud", "storage", "ls", f"gs://{bucket}/{EXPORT_PREFIX}/",
                f"--project={project_id}",
            ]
        ),
        "listing Cloud SQL exports",
    )
    exports = sorted(line for line in result.stdout.splitlines() if line.endswith(".sql.gz"))
    if exports:
        instance = terraform_output("ephemeral", "cloudsql_connection_name", runner=runner)
        _require(
            runner(
                [
                    "gcloud", "sql", "import", "sql", instance.split(":")[-1], exports[-1],
                    "--database=meeting_memory", f"--project={project_id}", "--quiet",
                ]
            ),
            "Cloud SQL import",
        )
        steps.append(f"restored Cloud SQL from {exports[-1]}")
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

    bucket = f"{project_id}-backups"

    try:
        steps = (
            sync_up(args.env, project_id, bucket)
            if args.direction == "up"
            else sync_down(args.env, project_id, bucket, now=datetime.now(UTC))
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
