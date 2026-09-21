"""Phase 17 — Historical multi-turn chat feed and context persistence.

Verifies:
1. Retrieval context formatting (_format_history_context).
2. MemoryQuery Pydantic schema validation for history.
3. End-to-end multi-turn query handling through retrieval.full_memory_query.
4. ASGI route /graph/memory/query with historical turns payload.
5. Dashboard static HTML contracts: bottom input dock, scrollable feed,
   multi-turn localStorage persistence, and new thread clear actions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

import api
from api.main import create_app
from api.routers.memory import MemoryQuery
from meeting_notes.memory import retrieval


def test_format_history_context_basic() -> None:
    history = [
        {"role": "user", "text": "What action items are assigned to Alice?"},
        {"role": "assistant", "answer": "Alice has 2 action items: review PR and update specs."},
    ]
    formatted = retrieval._format_history_context(history)
    assert "User: What action items are assigned to Alice?" in formatted
    assert "Assistant: Alice has 2 action items: review PR and update specs." in formatted


def test_format_history_context_truncates_long_turn() -> None:
    long_text = "x" * 600
    history = [{"role": "assistant", "answer": long_text}]
    formatted = retrieval._format_history_context(history)
    assert len(formatted) < 600
    assert formatted.endswith("...")


def test_format_history_context_empty_or_whitespace() -> None:
    history = [{"role": "user", "text": ""}, {"role": "assistant", "text": "   "}]
    assert retrieval._format_history_context(history) == ""
    assert retrieval._format_history_context([]) == ""


def test_memory_query_validation() -> None:
    # Valid without history
    q1 = MemoryQuery(question="What was discussed?")
    assert q1.history is None

    # Valid with history
    q2 = MemoryQuery(
        question="Who was assigned to the first one?",
        history=[
            {"role": "user", "text": "What action items came up?"},
            {"role": "assistant", "text": "Task 1: Auth review, Task 2: DB migration"},
        ],
    )
    assert len(q2.history or []) == 2


@pytest.fixture
def app() -> Any:
    return create_app()


async def _post(app: Any, path: str, **kw: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, **kw)


async def test_full_memory_query_incorporates_history_in_synthesis(monkeypatch: Any) -> None:
    captured_synth_user: list[str] = []

    async def fake_chat(system: str, user: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if "Extract entities" in system or "entity" in system.lower():
            return {"people": ["Alice"], "topics": ["Authentication"], "date_hint": None}
        captured_synth_user.append(user)
        return {"answer": "Alice is assigned to Authentication."}

    monkeypatch.setattr(retrieval, "_chat", fake_chat)
    monkeypatch.setattr(
        retrieval,
        "assemble_context",
        AsyncMock(return_value=(["ActionItem: Task: Auth review | Owner: Alice"], ["node-1"])),
    )
    monkeypatch.setattr(retrieval.episodic, "log_session", AsyncMock())

    history = [
        {"role": "user", "text": "What tasks were assigned in the security meeting?"},
        {"role": "assistant", "answer": "Tasks: Authentication review and TLS rotation."},
    ]
    res = await retrieval.full_memory_query(
        "Who is assigned to that?",
        history=history,
        driver=AsyncMock(),
        log_session=False,
    )

    assert "Alice" in res["answer"]
    assert len(captured_synth_user) == 1
    assert "Recent conversation context:" in captured_synth_user[0]
    assert "User: What tasks were assigned in the security meeting?" in captured_synth_user[0]
    assert "Question: Who is assigned to that?" in captured_synth_user[0]


async def test_api_memory_query_accepts_history_payload(app: Any, monkeypatch: Any) -> None:
    async def fake_full_query(question: str, **kwargs: Any) -> dict[str, Any]:
        assert kwargs.get("history") is not None
        assert len(kwargs["history"]) == 2
        return {
            "question": question,
            "answer": "Follow-up answered with history.",
            "node_ids": ["node-1"],
            "entities": {"people": [], "topics": []},
            "suggested_followups": ["Next step?"],
        }

    monkeypatch.setattr(retrieval, "full_memory_query", fake_full_query)

    response = await _post(
        app,
        "/graph/memory/query",
        json={
            "question": "What about the second milestone?",
            "history": [
                {"role": "user", "text": "What milestones were agreed upon?"},
                {"role": "assistant", "text": "Milestone 1: Alpha launch; Milestone 2: Beta release."},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Follow-up answered with history."


def test_dashboard_html_chat_ui_and_docked_input() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # 1. Container and layout classes
    assert "#ask.panel.active" in html
    assert "display: flex;" in html
    assert ".chat-header" in html
    assert ".chat-feed" in html
    assert ".chat-bottom-dock" in html

    # 2. Controls & buttons in header
    assert 'id="chat-feed"' in html
    assert 'class="chat-btn-new-thread"' in html
    assert "clearChatHistory()" in html
    assert "New Thread" in html

    # 3. Bottom docked input components
    assert '<div class="chat-bottom-dock">' in html
    assert 'id="q"' in html
    assert 'id="ask-btn"' in html
    assert "chat-bottom-hint" in html
    assert "id=\"chat-thread-counter\"" in html

    # 4. Multi-turn historical logic & persistence
    assert "mn_chat_history_v2" in html
    assert "loadChatHistory()" in html
    assert "saveChatHistory()" in html
    assert "renderChatFeed()" in html
    assert "scrollChatToBottom" in html
    assert "copySpecificAnswer(" in html
    assert "copySpecificDeliverables(" in html
    assert "abortChatQuery()" in html


def test_dashboard_unified_header_and_url_hash_routing() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # 1. Unified header containing nav tabs directly (eliminates redundant nav bar row)
    assert '<nav class="header-nav"' in html
    assert '<div class="header-brand">' in html
    assert '<div class="header-actions">' in html

    # 2. All 7 primary panel tabs present
    for panel in ["overview", "meetings", "actions", "workstreams", "graph", "ask", "review"]:
        assert f'data-panel="{panel}"' in html

    # 3. Hash routing and reload persistence
    assert "VALID_PANELS" in html
    assert "function switchTab(" in html
    assert "function getInitialTab(" in html
    assert 'window.addEventListener("hashchange"' in html
    assert "history.replaceState(" in html
    assert "mn_active_tab" in html

    # 4. Vertical content space optimizations
    assert "height: calc(100vh - 78px);" in html
    assert "height: 48px;" in html


def test_ask_landing_page_no_scroll_contract() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # 1. No scroll on landing feed
    assert ".chat-feed.is-landing" in html
    assert "overflow: hidden !important;" in html

    # 2. Compact landing grid layout and classes
    assert ".chat-landing-grid" in html
    assert "prompt-card compact" in html
    assert ".chat-empty-container" in html

    # 3. Dynamic class toggling based on chat turns
    assert 'feed.classList.add("is-landing")' in html
    assert 'feed.classList.remove("is-landing")' in html

    # 4. Dual-section landing layout showing both Preset Common Queries and AI Queries
    assert ".chat-landing-dual" in html
    assert "Common Questions" in html
    assert "AI-Generated Questions" in html
    assert ".chat-landing-col-header" in html


def test_action_items_button_no_wrap_and_typewriter_reveal() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # 1. Action Items button wrapping prevention
    assert "white-space:nowrap; display:inline-block;" in html or "white-space: nowrap; display: inline-block;" in html or "white-space:nowrap" in html
    assert '#actions-body td:last-child { white-space:nowrap; text-align:right; }' in html
    assert '"90px"' in html

    # 2. Typewriter reveal animation
    assert "typewriterReveal(" in html
    assert "activeTypewriterCancel" in html
    assert "typing-cursor" in html
    assert "@keyframes typewriterBlink" in html


def test_ask_reset_without_popup_and_normalized_message_spacing() -> None:
    html = (Path(api.__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")

    # 1. Reset conversation without a popup
    # Ensure confirm() popup is removed from clearChatHistory
    clear_fn_idx = html.find("function clearChatHistory()")
    assert clear_fn_idx != -1
    clear_fn_snippet = html[clear_fn_idx:clear_fn_idx + 400]
    assert "confirm(" not in clear_fn_snippet
    assert "abortChatQuery();" in clear_fn_snippet
    assert "CHAT_TURNS = [];" in clear_fn_snippet
    assert "renderChatFeed();" in clear_fn_snippet

    # 2. Normalized spacing between AI response and new user query
    assert "#ask-body" in html
    assert "gap: 14px;" in html
    assert ".chat-user-msg" in html
    assert "margin:0;" in html
    assert ".chat-loading" in html
    assert ".answer {" in html
    assert "margin:0;" in html
    assert ".answer > *:last-child" in html
    assert "margin-bottom: 0 !important;" in html
