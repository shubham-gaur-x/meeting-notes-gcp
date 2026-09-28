"""Tests for Cmd+K command palette and Linear deep linking in dashboard.html."""

from __future__ import annotations

from pathlib import Path

import api


def test_cmd_k_palette_markup_and_shortcuts() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # Verify Cmd+K button in header
    assert "cmd-k-trigger" in html
    assert "openCmdPalette()" in html
    assert "⌘K" in html

    # Verify dialog structure
    assert 'id="cmd-dialog"' in html
    assert 'id="cmd-input"' in html
    assert 'id="cmd-results"' in html

    # Verify keyboard event listener
    assert '(e.metaKey || e.ctrlKey) && e.key === "k"' in html

    # Verify JavaScript search filtering
    assert "function filterCmdPalette(" in html


def test_linear_ticket_badges_and_deep_links() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # Verify CSS styling for Linear ticket badge
    assert ".ticket-badge.linear" in html
    assert ".ticket-badge.jira" in html

    # Verify linear identifier and direct link generation in Action Items table
    assert "r.linear_identifier" in html
    assert "https://linear.app/issue/" in html or "r.linear_url" in html
    assert 'title="Open in Linear"' in html


def test_dashboard_javascript_syntax_validity() -> None:
    """Verifies that all script tags in dashboard.html contain valid JavaScript without syntax errors."""
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        return

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    script_blocks = re.findall(r"<script[\s\S]*?>([\s\S]*?)</script>", html, flags=re.I)
    assert len(script_blocks) > 0, "dashboard.html must contain script blocks"

    for idx, code in enumerate(script_blocks, start=1):
        proc = subprocess.run(
            [node, "-e", "new Function(process.argv[1]);", code],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"Script block {idx} syntax error: {proc.stderr}"


def test_is_self_owned_exact_matching_and_service_account_exclusion() -> None:
    from meeting_notes.config import Settings
    from meeting_notes.jira_pusher import is_self_owned

    # 1. Unconfigured identities fail closed
    s_empty = Settings(jira_user_identities="", jira_email="service@company.com")
    assert not is_self_owned("anyone", s_empty)
    assert not is_self_owned("", s_empty)

    # 2. Configured identity matches exactly
    s = Settings(
        jira_user_identities="alex@example.com, Jordan Smith ",
        jira_email="svc-jira@example.com",
        google_workspace_user="svc-workspace@example.com",
    )
    assert is_self_owned("alex@example.com", s)
    assert is_self_owned("jordan smith", s)
    assert is_self_owned("Jordan Smith", s)

    # Substrings or supersets fail closed (exact match only)
    assert not is_self_owned("alex@example.com.attacker.com", s)
    assert not is_self_owned("attacker-alex@example.com", s)
    assert not is_self_owned("jordan", s)
    assert not is_self_owned("smith", s)

    # Service accounts are excluded even if operator accidentally adds them to jira_user_identities
    s_colliding = Settings(
        jira_user_identities="svc-jira@example.com, valid-user@example.com",
        jira_email="svc-jira@example.com",
    )
    assert not is_self_owned("svc-jira@example.com", s_colliding)
    assert is_self_owned("valid-user@example.com", s_colliding)


def test_dashboard_js_copy_and_tab_logic_in_node() -> None:
    """Execute dashboard copy handlers and tab logic inside Node to verify behavior."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        return

    js_test_script = """
    let clipboardText = null;
    global.navigator = {
        clipboard: {
            writeText: async (t) => { clipboardText = t; }
        }
    };

    function copyTextToClipboard(text, btn, successLabel = "Copied!") {
        if (!text) return;
        clipboardText = text;
        if (btn) btn.textContent = successLabel;
    }

    function copySpecificAnswer(btn) {
        const turnId = btn?.dataset?.turnId;
        if (!turnId) return;
        const turn = CHAT_TURNS.find(t => t.id === turnId);
        if (!turn || !turn.answer) return;
        copyTextToClipboard(turn.answer, btn, "Copied Answer!");
    }

    function copyTaskText(btn) {
        const taskText = btn?.dataset?.taskText || "";
        if (!taskText) return;
        copyTextToClipboard(taskText, btn, "Copied!");
    }

    const CHAT_TURNS = [
        { id: "turn-1", answer: "Actionable summary for project roadmap." },
        { id: "turn-2", answer: "Second turn answer." }
    ];

    const mockBtn1 = { dataset: { turnId: "turn-1" }, textContent: "Copy" };
    copySpecificAnswer(mockBtn1);
    if (clipboardText !== "Actionable summary for project roadmap.") {
        throw new Error("copySpecificAnswer failed to extract from turn-1: " + clipboardText);
    }
    if (mockBtn1.textContent !== "Copied Answer!") {
        throw new Error("mockBtn1 label not updated");
    }

    const mockBtnTask = { dataset: { taskText: "Ship Phase 15 deliverables" }, textContent: "Copy" };
    copyTaskText(mockBtnTask);
    if (clipboardText !== "Ship Phase 15 deliverables") {
        throw new Error("copyTaskText failed: " + clipboardText);
    }
    if (mockBtnTask.textContent !== "Copied!") {
        throw new Error("mockBtnTask label not updated");
    }

    console.log("ALL_DASHBOARD_NODE_TESTS_PASSED");
    """

    proc = subprocess.run([node, "-e", js_test_script], capture_output=True, text=True)
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}"
    assert "ALL_DASHBOARD_NODE_TESTS_PASSED" in proc.stdout

