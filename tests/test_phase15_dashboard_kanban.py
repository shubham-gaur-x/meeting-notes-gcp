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


def test_jira_identity_warning_single_fire_and_reset() -> None:
    from unittest.mock import patch

    from meeting_notes.config import Settings
    from meeting_notes.jira_pusher import (
        is_self_owned,
        reset_jira_identity_warning_guards,
    )

    reset_jira_identity_warning_guards()

    # 1. No identities configured: warning should fire exactly once across multiple calls
    s_empty = Settings(jira_user_identities="", jira_email="service@company.com")
    with patch("meeting_notes.jira_pusher.log.warning") as mock_warn:
        assert not is_self_owned("anyone", s_empty)
        assert not is_self_owned("anyone_else", s_empty)
        assert mock_warn.call_count == 1
        assert mock_warn.call_args[0][0] == "jira_pusher.no_identities_configured_for_self_only"

        # Calling again continues to suppress log spam
        assert not is_self_owned("third_person", s_empty)
        assert mock_warn.call_count == 1

        # Resetting allows the warning to fire again on fresh configuration/run
        reset_jira_identity_warning_guards()
        assert not is_self_owned("anyone", s_empty)
        assert mock_warn.call_count == 2

    # 2. Service account collision: warning should fire once per service account and suppress duplicates
    reset_jira_identity_warning_guards()
    s_collision = Settings(
        jira_user_identities="svc@company.com, user@company.com",
        jira_email="svc@company.com",
    )
    with patch("meeting_notes.jira_pusher.log.warning") as mock_warn:
        assert not is_self_owned("svc@company.com", s_collision)
        assert is_self_owned("user@company.com", s_collision)
        assert not is_self_owned("svc@company.com", s_collision)
        assert mock_warn.call_count == 1
        assert mock_warn.call_args[0][0] == "jira_pusher.service_account_excluded_from_self_identity"

        reset_jira_identity_warning_guards()
        assert not is_self_owned("svc@company.com", s_collision)
        assert mock_warn.call_count == 2


def test_dashboard_js_copy_handlers_execution_in_node() -> None:
    """Execute actual shipped copy handlers and toolbar logic from dashboard.html inside Node."""
    import re
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        return

    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
    script_match = re.search(r"<script>([\s\S]*?)</script>", html)
    assert script_match, "dashboard.html must contain a main <script> tag"
    dashboard_js = script_match.group(1)

    runner_script = f"""
    const vm = require("vm");

    const fakeEl = () => ({{
      style: {{}},
      dataset: {{}},
      classList: {{ add(){{}}, remove(){{}}, toggle(){{}}, contains(){{ return false; }} }},
      appendChild(){{}},
      removeChild(){{}},
      addEventListener(){{}},
      querySelector(){{ return null; }},
      querySelectorAll(){{ return []; }},
      focus(){{}},
      select(){{}}
    }});

    let copiedText = null;
    Object.defineProperty(navigator, "clipboard", {{
      value: {{ writeText: async (t) => {{ copiedText = t; }} }},
      configurable: true,
      writable: true
    }});

    global.window = {{
      location: {{ hash: "" }},
      addEventListener(){{}},
      matchMedia: () => ({{ matches: false, addEventListener(){{}} }}),
      navigator: navigator
    }};
    global.history = {{ replaceState(){{}} }};
    global.document = {{
      querySelector: () => fakeEl(),
      querySelectorAll: () => [],
      createElement: () => fakeEl(),
      body: fakeEl(),
      execCommand: () => true,
      addEventListener(){{}}
    }};
    global.localStorage = {{
      getItem: () => null,
      setItem: () => {{}},
      removeItem: () => {{}}
    }};
    global.fetch = async () => ({{ ok: true, status: 200, json: async () => ({{}}) }});

    // Evaluate shipped dashboard script in context
    vm.runInThisContext({repr(dashboard_js)});

    async function runVerifications() {{
      // Setup turn fixture in real CHAT_TURNS
      CHAT_TURNS.length = 0;
      CHAT_TURNS.push({{
        id: "turn-test-1",
        answer: "### Summary\\nHere is the answer.\\n\\n" +
                "- [ ] Task 1: Complete rollout\\n- [ ] Task 2: Audit code"
      }});

      // 1. copySpecificAnswer
      copiedText = null;
      const btnAns = {{
        dataset: {{ turnId: "turn-test-1" }},
        textContent: "Copy Answer",
        querySelector: () => null,
        classList: {{ add(){{}}, remove(){{}} }}
      }};
      copySpecificAnswer(btnAns);
      await new Promise(r => setTimeout(r, 20));
      if (!copiedText || !copiedText.includes("### Summary")) {{
        throw new Error("copySpecificAnswer failed: " + copiedText);
      }}
      if (btnAns.textContent !== "Copied Answer!") {{
        throw new Error("copySpecificAnswer label failed");
      }}

      // 2. copySpecificDeliverables
      copiedText = null;
      const btnDeliv = {{
        dataset: {{ turnId: "turn-test-1" }},
        textContent: "Copy Deliverables",
        querySelector: () => null,
        classList: {{ add(){{}}, remove(){{}} }}
      }};
      copySpecificDeliverables(btnDeliv);
      await new Promise(r => setTimeout(r, 20));
      if (!copiedText || !copiedText.includes("Task 1: Complete rollout")) {{
        throw new Error("copySpecificDeliverables failed: " + copiedText);
      }}
      if (btnDeliv.textContent !== "Copied Deliverables!") {{
        throw new Error("copySpecificDeliverables label failed");
      }}

      // 3. copyTaskText
      copiedText = null;
      const btnTask = {{
        dataset: {{ taskText: "Fix production memory issue" }},
        textContent: "Copy",
        querySelector: () => null,
        classList: {{ add(){{}}, remove(){{}} }}
      }};
      copyTaskText(btnTask);
      await new Promise(r => setTimeout(r, 20));
      if (copiedText !== "Fix production memory issue") {{
        throw new Error("copyTaskText failed: " + copiedText);
      }}
      if (btnTask.textContent !== "Copied!") {{
        throw new Error("copyTaskText label failed");
      }}

      // 4. copyCode
      copiedText = null;
      const codeEl = {{ textContent: "const x = 42;" }};
      const wrapEl = {{ querySelector: (s) => s === "pre code" ? codeEl : null }};
      const btnCode = {{
        closest: (s) => s === ".code-block-wrap" ? wrapEl : null,
        textContent: "Copy Code",
        querySelector: () => null,
        classList: {{ add(){{}}, remove(){{}} }}
      }};
      copyCode(btnCode);
      await new Promise(r => setTimeout(r, 20));
      if (copiedText !== "const x = 42;") {{
        throw new Error("copyCode failed: " + copiedText);
      }}
      if (btnCode.textContent !== "Copied!") {{
        throw new Error("copyCode label failed");
      }}

      console.log("SHIPPED_DASHBOARD_COPY_HANDLERS_VERIFIED_SUCCESSFULLY");
    }}

    runVerifications();
    """

    proc = subprocess.run([node, "-e", runner_script], capture_output=True, text=True)
    assert proc.returncode == 0, f"Node verification failed: {proc.stderr}"
    assert "SHIPPED_DASHBOARD_COPY_HANDLERS_VERIFIED_SUCCESSFULLY" in proc.stdout
