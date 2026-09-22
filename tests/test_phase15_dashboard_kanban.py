"""Tests for Cmd+K command palette and Linear deep linking in dashboard.html."""

from __future__ import annotations

from pathlib import Path

import api


def test_linear_ticket_badges_and_deep_links() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # Verify CSS styling for Linear ticket badge
    assert ".ticket-badge.linear" in html
    assert ".ticket-badge.jira" in html

    # Verify linear identifier and direct link generation in Action Items table
    assert "r.linear_identifier" in html
    assert "https://linear.app/issue/" in html or "r.linear_url" in html
    assert 'title="Open in Linear"' in html
