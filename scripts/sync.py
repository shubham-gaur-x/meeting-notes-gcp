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
