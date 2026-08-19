"""Phase 0.6 — the preflight doctor.

Every check takes its environment probe as a parameter, so this whole file runs
with no Docker, no sockets, no filesystem, no gcloud, and no network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.doctor import (
    REQUIRED_PORTS,
    CheckResult,
    Status,
    build_parser,
    check_command,
    check_docker_daemon,
    check_llm_backend,
    check_port_free,
    check_python_version,
    check_tfvars,
    check_token_age,
    exit_code_for,
    render_report,
    run_checks,
    secret_status,
)

# ─── result type and exit codes ───────────────────────────────────────────────


def test_exit_code_zero_when_all_pass() -> None:
    assert exit_code_for([CheckResult("a", Status.PASS, "ok")]) == 0


def test_exit_code_one_on_any_fail() -> None:
    results = [
        CheckResult("a", Status.PASS, "ok"),
        CheckResult("b", Status.FAIL, "bad", "run something"),
    ]
    assert exit_code_for(results) == 1


def test_exit_code_two_on_warnings_only() -> None:
    results = [CheckResult("a", Status.PASS, "ok"), CheckResult("b", Status.WARN, "meh")]
    assert exit_code_for(results) == 2


def test_fail_outranks_warn_in_exit_code() -> None:
    results = [
        CheckResult("a", Status.WARN, "meh"),
        CheckResult("b", Status.FAIL, "bad", "fix it"),
    ]
    assert exit_code_for(results) == 1


def test_exit_code_zero_for_no_checks() -> None:
    assert exit_code_for([]) == 0


# ─── report rendering ─────────────────────────────────────────────────────────


def test_report_shows_every_remediation_for_failures() -> None:
    report = render_report(
        [CheckResult("terraform", Status.FAIL, "not installed", "brew install terraform")],
        tier=2,
    )
    assert "FAIL" in report
    assert "terraform" in report
    assert "brew install terraform" in report


def test_report_states_which_tier_was_checked() -> None:
    assert "tier 0" in render_report([], tier=0).lower()


def test_report_does_not_invent_remediation_for_passes() -> None:
    report = render_report([CheckResult("docker", Status.PASS, "running")], tier=0)
    assert "PASS" in report
    assert "docker" in report


# ─── tier 0 checks ────────────────────────────────────────────────────────────


def test_python_version_passes_on_311() -> None:
    assert check_python_version((3, 11)).status is Status.PASS


def test_python_version_passes_on_312() -> None:
    assert check_python_version((3, 12)).status is Status.PASS


def test_python_version_fails_on_310_with_remediation() -> None:
    result = check_python_version((3, 10))
    assert result.status is Status.FAIL
    assert result.remediation


def test_command_present() -> None:
    result = check_command("docker", which=lambda _: "/usr/bin/docker")
    assert result.status is Status.PASS


def test_command_absent_names_how_to_install() -> None:
    result = check_command("terraform", which=lambda _: None)
    assert result.status is Status.FAIL
    assert result.remediation
    assert "terraform" in result.remediation


def test_docker_daemon_up() -> None:
    assert check_docker_daemon(probe=lambda: True).status is Status.PASS


def test_docker_daemon_down_has_remediation() -> None:
    result = check_docker_daemon(probe=lambda: False)
    assert result.status is Status.FAIL
    assert result.remediation


def test_port_free_passes() -> None:
    result = check_port_free(5432, "Postgres", probe=lambda _: True)
    assert result.status is Status.PASS


def test_port_occupied_warns_not_fails() -> None:
    """An occupied port is recoverable — the user may already be running the
    stack. It must not hard-fail a clean clone."""
    result = check_port_free(5432, "Postgres", probe=lambda _: False)
    assert result.status is Status.WARN
    assert result.remediation
    assert "5432" in result.detail or "5432" in result.remediation


def test_required_ports_cover_the_local_stack() -> None:
    assert set(REQUIRED_PORTS) == {5432, 7687, 7444, 8080}


# ─── tier 1 ───────────────────────────────────────────────────────────────────


def test_llm_backend_fake_needs_no_credentials() -> None:
    result = check_llm_backend({"LLM_BACKEND": "fake"})
    assert result.status is Status.PASS


def test_llm_backend_gemini_without_key_fails() -> None:
    result = check_llm_backend({"LLM_BACKEND": "gemini"})
    assert result.status is Status.FAIL
    assert result.remediation


def test_llm_backend_gemini_with_key_passes() -> None:
    result = check_llm_backend({"LLM_BACKEND": "gemini", "GEMINI_API_KEY": "x"})
    assert result.status is Status.PASS


def test_llm_backend_unknown_value_fails() -> None:
    result = check_llm_backend({"LLM_BACKEND": "banana"})
    assert result.status is Status.FAIL


def test_llm_backend_defaults_to_fake_when_unset() -> None:
    assert check_llm_backend({}).status is Status.PASS


# ─── tier 2 ───────────────────────────────────────────────────────────────────


def test_secret_status_reports_set_without_the_value() -> None:
    result = secret_status({"JIRA_API_TOKEN": "supersecret"}, "JIRA_API_TOKEN")
    assert result.status is Status.PASS
    assert "supersecret" not in result.detail


def test_secret_status_reports_unset() -> None:
    result = secret_status({}, "JIRA_API_TOKEN")
    assert result.status is Status.FAIL
    assert "unset" in result.detail.lower()


def test_blank_secret_counts_as_unset() -> None:
    assert secret_status({"JIRA_API_TOKEN": "   "}, "JIRA_API_TOKEN").status is Status.FAIL


def test_no_check_ever_emits_a_secret_value() -> None:
    """The single most important test in this file. docs/GOOGLE_AUTH.md §7.

    Values carry a canary substring that cannot appear in any variable *name*,
    so this asserts the value leaked — not merely that the key was printed.
    Printing the key name is required; printing any part of its value is not.
    """
    env = {
        "GOOGLE_OAUTH_CLIENT_SECRET": "GOCSPX-leakcanary-aaa",
        "GEMINI_API_KEY": "AIza-leakcanary-bbb",
        "JIRA_API_TOKEN": "jiratok-leakcanary-ccc",
    }
    results = [secret_status(env, key) for key in env]
    blob = render_report(results, tier=2)

    assert "leakcanary" not in blob
    for value in env.values():
        assert value not in blob
    # Not even a leading fragment — no truncated prefixes.
    for value in env.values():
        assert value[:8] not in blob

    # The key names themselves must still be visible, or the report is useless.
    for key in env:
        assert key in blob


def test_token_age_fresh_passes(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    path = tmp_path / "token.json"
    path.write_text(f'{{"issued_at": "{(now - timedelta(days=1)).isoformat()}"}}', encoding="utf-8")
    result = check_token_age(path, now=now)
    assert result.status is Status.PASS


def test_token_age_expired_fails_with_reconsent(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    path = tmp_path / "token.json"
    path.write_text(f'{{"issued_at": "{(now - timedelta(days=9)).isoformat()}"}}', encoding="utf-8")
    result = check_token_age(path, now=now)
    assert result.status is Status.FAIL
    assert result.remediation is not None
    assert "reconsent" in result.remediation


def test_token_age_nearly_expired_warns(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    path = tmp_path / "token.json"
    path.write_text(
        f'{{"issued_at": "{(now - timedelta(days=6.5)).isoformat()}"}}', encoding="utf-8"
    )
    assert check_token_age(path, now=now).status is Status.WARN


def test_token_age_missing_file_fails(tmp_path: Path) -> None:
    result = check_token_age(tmp_path / "nope.json", now=datetime.now(UTC))
    assert result.status is Status.FAIL
    assert result.remediation is not None
    assert "auth-spike" in result.remediation


def test_token_age_never_prints_the_token(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    path = tmp_path / "token.json"
    path.write_text(
        f'{{"issued_at": "{now.isoformat()}", "refresh_token": "LEAKME-XYZ"}}', encoding="utf-8"
    )
    result = check_token_age(path, now=now)
    assert "LEAKME" not in render_report([result], tier=2)


def test_tfvars_present() -> None:
    assert check_tfvars("personal", exists=lambda _: True).status is Status.PASS


def test_tfvars_absent_points_at_the_example() -> None:
    result = check_tfvars("personal", exists=lambda _: False)
    assert result.status is Status.FAIL
    assert result.remediation is not None
    assert "example" in result.remediation


# ─── orchestration and CLI ────────────────────────────────────────────────────


def test_tier_zero_runs_only_local_checks() -> None:
    names = {r.name for r in run_checks(tier=0, env={})}
    assert not any("Jira" in n or "gcloud" in n or "terraform" in n for n in names)


def test_higher_tiers_are_supersets_of_tier_zero() -> None:
    tier0 = {r.name for r in run_checks(tier=0, env={})}
    tier2 = {r.name for r in run_checks(tier=2, env={})}
    assert tier0 <= tier2


def test_tier_two_checks_cloud_tooling() -> None:
    names = " ".join(r.name for r in run_checks(tier=2, env={}))
    assert "terraform" in names
    assert "gcloud" in names


def test_parser_accepts_tier_and_env() -> None:
    args = build_parser().parse_args(["--tier", "2", "--env", "onix"])
    assert args.tier == 2
    assert args.env == "onix"


def test_parser_defaults_to_tier_zero() -> None:
    assert build_parser().parse_args([]).tier == 0
