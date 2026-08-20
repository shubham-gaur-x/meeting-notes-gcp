#!/usr/bin/env python3
"""Phase 0.6 preflight — answer "why can't I run this?" before the stack trace.

Three tiers, each additive, each honest about what it proves:

    tier 0  make doctor                 local stack, no credentials at all
    tier 1  make doctor LLM=gemini      adds real LLM extraction
    tier 2  make doctor ENV=personal    adds GCP, Workspace, Jira

Every check takes its environment probe as an injected parameter, so the test
suite exercises both branches of every check with no Docker, no sockets, no
network, and no gcloud.

Secrets are reported as set/unset/expired only. No value is ever printed — not
truncated, not prefixed, not length-hinted. See docs/GOOGLE_AUTH.md §7.

Like scripts/auth_spike.py, this predates meeting_notes/config.py and takes its
environment as a parameter rather than reaching for os.environ directly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOKEN_PATH = REPO_ROOT / "token.json"

# Mirrors REFRESH_TOKEN_LIFETIME_DAYS in scripts/auth_spike.py. External +
# Testing OAuth apps expire refresh tokens after exactly 7 days.
REFRESH_TOKEN_LIFETIME_DAYS = 7
TOKEN_WARN_DAYS_REMAINING = 1.0

# Ports the local compose stack binds. Names are user-facing.
# Must match docker-compose.local.yml. Deliberately offset from the
# conventional ports: v5's stack is long-running on this machine and holds
# 5432/7687/3000, and v5 is read-only reference.
REQUIRED_PORTS: dict[int, str] = {
    55432: "Postgres",
    57687: "Memgraph Bolt",
    57444: "Memgraph monitoring",
    53000: "Memgraph Lab",
    # Not in compose — the API runs on the host during Phases 3-8.
    8080: "API",
}

VALID_LLM_BACKENDS = ("fake", "gemini", "lmstudio", "vertex")

INSTALL_HINTS: dict[str, str] = {
    "docker": "Install Docker Desktop: https://docs.docker.com/get-docker/",
    # Terraform is BUSL-licensed and no longer in homebrew-core; the plain
    # `brew install terraform` returns an unrelated fuzzy-match list instead
    # of installing anything.
    "terraform": "Install terraform: brew tap hashicorp/tap && brew install hashicorp/tap/terraform",
    "gcloud": "Install the gcloud CLI: https://cloud.google.com/sdk/docs/install",
}


class Status(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str
    remediation: str | None = None


# ─── tier 0: local ────────────────────────────────────────────────────────────


def check_python_version(version: tuple[int, int]) -> CheckResult:
    major, minor = version
    if (major, minor) >= (3, 11):
        return CheckResult("Python >= 3.11", Status.PASS, f"{major}.{minor}")
    return CheckResult(
        "Python >= 3.11",
        Status.FAIL,
        f"found {major}.{minor}",
        "Install Python 3.11 or newer, then recreate the venv: python3 -m venv .venv",
    )


def check_command(name: str, which: Callable[[str], str | None] = shutil.which) -> CheckResult:
    path = which(name)
    if path:
        return CheckResult(f"{name} installed", Status.PASS, path)
    return CheckResult(
        f"{name} installed",
        Status.FAIL,
        "not on PATH",
        INSTALL_HINTS.get(name, f"Install {name} and ensure it is on your PATH"),
    )


def _docker_daemon_running() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def check_docker_daemon(probe: Callable[[], bool] = _docker_daemon_running) -> CheckResult:
    if probe():
        return CheckResult("Docker daemon", Status.PASS, "running")
    return CheckResult(
        "Docker daemon",
        Status.FAIL,
        "not reachable",
        "Start Docker Desktop, then re-run `make doctor`",
    )


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def check_port_free(
    port: int, service: str, probe: Callable[[int], bool] = _port_is_free
) -> CheckResult:
    name = f"port {port} free ({service})"
    if probe(port):
        return CheckResult(name, Status.PASS, "available")
    # A WARN, not a FAIL: the user may already be running the stack, which is
    # a perfectly good state to be in.
    return CheckResult(
        name,
        Status.WARN,
        f"port {port} is in use",
        f"Something already listens on {port}. If it is this project's stack, "
        "that is fine. Otherwise stop it or run `make demo-down`.",
    )


# ─── tier 1: LLM ──────────────────────────────────────────────────────────────


def check_llm_backend(env: Mapping[str, str]) -> CheckResult:
    backend = (env.get("LLM_BACKEND") or "fake").strip().lower()
    name = "LLM backend"

    if backend not in VALID_LLM_BACKENDS:
        return CheckResult(
            name,
            Status.FAIL,
            f"unknown backend {backend!r}",
            f"Set LLM_BACKEND to one of: {' | '.join(VALID_LLM_BACKENDS)}",
        )

    if backend == "fake":
        return CheckResult(name, Status.PASS, "fake — replays recorded fixtures, no credentials")

    if backend == "gemini":
        if (env.get("GEMINI_API_KEY") or "").strip():
            return CheckResult(name, Status.PASS, "gemini — API key set")
        return CheckResult(
            name,
            Status.FAIL,
            "gemini selected but GEMINI_API_KEY is unset",
            "Get a free key at https://aistudio.google.com/apikey and put it in .env",
        )

    if backend == "lmstudio":
        return CheckResult(
            name, Status.PASS, "lmstudio — ensure the local server is running with both models"
        )

    return CheckResult(name, Status.PASS, "vertex — requires GCP credentials (tier 2)")


# ─── tier 2: cloud ────────────────────────────────────────────────────────────


def secret_status(env: Mapping[str, str], key: str) -> CheckResult:
    """Report whether a credential is present. Never reports its value."""
    if (env.get(key) or "").strip():
        return CheckResult(key, Status.PASS, "set")
    return CheckResult(
        key,
        Status.FAIL,
        "unset",
        f"Set {key} in .env — see .env.example for what it is",
    )


def check_token_age(
    path: Path = DEFAULT_TOKEN_PATH, *, now: datetime | None = None
) -> CheckResult:
    """Check the OAuth refresh token against its 7-day clock.

    Reads only issued_at. The token value is never read into the report.
    """
    name = "OAuth refresh token"
    moment = now or datetime.now(UTC)

    if not path.exists():
        return CheckResult(
            name,
            Status.FAIL,
            "no token.json",
            "Run `make auth-spike` — see docs/GOOGLE_AUTH.md §5",
        )

    try:
        issued_at = datetime.fromisoformat(
            json.loads(path.read_text(encoding="utf-8"))["issued_at"]
        )
    except (ValueError, KeyError, OSError):
        return CheckResult(
            name,
            Status.FAIL,
            "token.json is unreadable or malformed",
            "Run `make auth-spike ARGS=--reconsent` to recreate it",
        )

    age_days = (moment - issued_at).total_seconds() / 86400.0
    remaining = REFRESH_TOKEN_LIFETIME_DAYS - age_days

    if remaining <= 0:
        return CheckResult(
            name,
            Status.FAIL,
            f"expired {abs(remaining):.1f} days ago",
            "Run `make auth-spike ARGS=--reconsent`",
        )
    if remaining <= TOKEN_WARN_DAYS_REMAINING:
        return CheckResult(
            name,
            Status.WARN,
            f"expires in {remaining:.1f} days",
            "Run `make auth-spike ARGS=--reconsent` soon",
        )
    return CheckResult(name, Status.PASS, f"valid, {remaining:.1f} of 7 days remaining")


def check_tfvars(
    env_name: str, *, exists: Callable[[Path], bool] = Path.exists
) -> CheckResult:
    path = REPO_ROOT / "terraform" / "envs" / f"{env_name}.tfvars"
    name = f"terraform/envs/{env_name}.tfvars"
    if exists(path):
        return CheckResult(name, Status.PASS, "present")
    return CheckResult(
        name,
        Status.FAIL,
        "missing",
        f"cp terraform/envs/{env_name}.example.tfvars terraform/envs/{env_name}.tfvars "
        "and fill it in (the real .tfvars is gitignored)",
    )


def _ephemeral_tier_is_up() -> bool:
    """True if the Cloud SQL instance or the Memgraph VM currently exists.

    Reads Terraform state rather than calling gcloud: state is the authority on
    what this project created, and it answers without network round-trips to
    two separate APIs.
    """
    try:
        completed = subprocess.run(
            ["terraform", "-chdir=terraform/ephemeral", "state", "list"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def check_ephemeral_tier(
    probe: Callable[[], bool] = _ephemeral_tier_is_up,
) -> CheckResult:
    """Report whether the billable tier is currently running (ADR-016).

    Both answers are legitimate — up is correct during a sync session, down is
    correct the rest of the month — so this is never a FAIL. It exists because
    the expensive mistake is a sync-down that was skipped or failed, and
    nothing else in the system would tell you.
    """
    name = "ephemeral tier (Cloud SQL + Memgraph VM)"
    if not probe():
        return CheckResult(name, Status.PASS, "down — costing $0")
    return CheckResult(
        name,
        Status.WARN,
        "UP — roughly $58/month while it stays up",
        "Expected during a sync session. When you are done: make sync-down",
    )


# ─── orchestration ────────────────────────────────────────────────────────────


def run_checks(tier: int, env: Mapping[str, str], *, env_name: str = "personal") -> list[CheckResult]:
    """Run every check up to and including `tier`. Tiers are additive."""
    results: list[CheckResult] = [
        check_python_version(sys.version_info[:2]),
        check_command("docker"),
        check_docker_daemon(),
    ]
    results += [check_port_free(port, service) for port, service in REQUIRED_PORTS.items()]

    if tier >= 1:
        results.append(check_llm_backend(env))

    if tier >= 2:
        results += [
            check_command("gcloud"),
            check_command("terraform"),
            secret_status(env, "GCP_PROJECT_ID"),
            secret_status(env, "GOOGLE_OAUTH_CLIENT_ID"),
            secret_status(env, "GOOGLE_OAUTH_CLIENT_SECRET"),
            check_token_age(),
            check_tfvars(env_name),
            check_ephemeral_tier(),
        ]
        if (env.get("JIRA_ENABLED") or "").strip().lower() == "true":
            results += [
                secret_status(env, "JIRA_DOMAIN"),
                secret_status(env, "JIRA_EMAIL"),
                secret_status(env, "JIRA_API_TOKEN"),
            ]

    return results


def exit_code_for(results: list[CheckResult]) -> int:
    if any(r.status is Status.FAIL for r in results):
        return 1
    if any(r.status is Status.WARN for r in results):
        return 2
    return 0


TIER_LABELS = {
    0: "tier 0 — local stack, no credentials",
    1: "tier 1 — local stack + real LLM",
    2: "tier 2 — GCP, Workspace and Jira",
}


def render_report(results: list[CheckResult], tier: int) -> str:
    lines: list[str] = [
        "",
        f"meeting-notes-gcp preflight — {TIER_LABELS.get(tier, f'tier {tier}')}",
        "=" * 62,
    ]

    width = max((len(r.name) for r in results), default=0)
    for result in results:
        lines.append(f"  [{result.status.value}] {result.name.ljust(width)}  {result.detail}")
        if result.remediation and result.status is not Status.PASS:
            lines.append(f"         -> {result.remediation}")

    counts = {status: sum(1 for r in results if r.status is status) for status in Status}
    lines += [
        "",
        f"  {counts[Status.PASS]} passed · {counts[Status.WARN]} warning(s) · "
        f"{counts[Status.FAIL]} failure(s)",
    ]
    if counts[Status.FAIL]:
        lines.append("  Fix the failures above, then re-run. See docs/SETUP.md.")
    lines.append("")
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doctor",
        description="Preflight check — reports exactly what is missing, per tier.",
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=(0, 1, 2),
        default=0,
        help="0 local (default) · 1 adds LLM · 2 adds GCP/Workspace/Jira",
    )
    parser.add_argument(
        "--env", default="personal", help="which terraform env to check at tier 2"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Imported lazily so tier 0 works on a clone with no .env at all.
    from scripts.auth_spike import load_env_file

    load_env_file()
    import os

    results = run_checks(args.tier, os.environ, env_name=args.env)
    print(render_report(results, args.tier))
    return exit_code_for(results)


if __name__ == "__main__":
    raise SystemExit(main())
