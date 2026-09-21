"""Tests for Linear Kanban board and Cmd+K command palette in dashboard.html."""

from __future__ import annotations

from pathlib import Path

import api


def test_kanban_board_structure_and_columns() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # Verify navigation button and panel
    assert 'data-panel="kanban"' in html
    assert 'id="kanban"' in html
    assert "kanban: " in html or "kanban:" in html

    # Verify 4 Kanban columns
    assert 'id="col-backlog"' in html
    assert 'id="col-todo"' in html
    assert 'id="col-progress"' in html
    assert 'id="col-done"' in html

    # Verify counter badges
    assert 'id="count-backlog"' in html
    assert 'id="count-todo"' in html
    assert 'id="count-progress"' in html
    assert 'id="count-done"' in html

    # Verify card containers
    assert 'id="cards-backlog"' in html
    assert 'id="cards-todo"' in html
    assert 'id="cards-progress"' in html
    assert 'id="cards-done"' in html


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


def test_kanban_javascript_routines() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # Core functional definitions
    assert "function renderKanban()" in html
    assert "async function transitionKanbanItem(" in html
    assert "function openActionDetail(" in html
    assert "function filterCmdPalette(" in html

    # Optimistic local state update before re-render
    assert "renderKanban();" in html
    assert "renderActions();" in html
