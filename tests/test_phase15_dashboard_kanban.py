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
