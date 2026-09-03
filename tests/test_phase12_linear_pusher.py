"""Tests for meeting_notes.linear_pusher."""

from datetime import date
from typing import Any

import pytest

from meeting_notes import linear_pusher
from meeting_notes.config import Settings
from meeting_notes.models import ActionItem, Attendee, ExtractedMeeting


def _sample_meeting() -> ExtractedMeeting:
    return ExtractedMeeting(
        title="Engineering Weekly Sync",
        kind="meeting",
        platform="meet",
        date=date(2026, 9, 3),
        summary="Architecture roadmap and deliverables.",
        action_items=[
            ActionItem(
                task="Deploy Linear GraphQL client",
                owner="Michael Baylard",
                confidence=0.9,
                priority="high",
            ),
            ActionItem(
                task="Low confidence vague task",
                owner="Unknown",
                confidence=0.3,
                priority="low",
            ),
        ],
        attendees=[Attendee(name="Michael Baylard"), Attendee(name="Shubham Gaur")],
        links=["https://linear.app/team/project/cloud-migration"],
    )


@pytest.mark.asyncio
async def test_linear_pusher_creates_issues_and_gates_low_confidence() -> None:
    created_issues: list[dict[str, Any]] = []
    reviewed_actions: list[tuple[str, str]] = []
    updated_graph_info: list[tuple[str, str, str, str, str]] = []

    async def mock_create_issue(**kwargs: Any) -> dict[str, Any]:
        created_issues.append(kwargs)
        return {
            "id": "iss_101",
            "identifier": "ENG-101",
            "url": "https://linear.app/team/issue/ENG-101",
            "state": {"name": "Todo"},
        }

    async def mock_mark_needs_review(action_id: str, reason: str) -> None:
        reviewed_actions.append((action_id, reason))

    async def mock_update_linear_info(
        action_id: str, linear_id: str, linear_identifier: str, linear_url: str, linear_state: str
    ) -> None:
        updated_graph_info.append((action_id, linear_id, linear_identifier, linear_url, linear_state))

    settings = Settings(
        linear_api_key="test_api_key",
        linear_team_id="team_1",
        linear_confidence_threshold=0.6,
        linear_dedup_enabled=False,
    )
    meeting = _sample_meeting()

    created_ids = await linear_pusher.push_action_items_to_linear(
        meeting.action_items,
        meeting,
        source_id="gmail_thread_abc123",
        settings=settings,
        create_issue=mock_create_issue,
        mark_needs_review=mock_mark_needs_review,
        update_linear_info=mock_update_linear_info,
    )

    assert created_ids == ["ENG-101"]
    assert len(created_issues) == 1
    assert created_issues[0]["title"] == "Deploy Linear GraphQL client"
    assert created_issues[0]["priority"] == "high"
    assert "Engineering Weekly Sync" in created_issues[0]["description"]
    assert "https://linear.app/team/project/cloud-migration" in created_issues[0]["description"]

    # Low confidence item should be routed to review
    assert len(reviewed_actions) == 1
    assert "confidence 0.30 below threshold" in reviewed_actions[0][1]

    # Graph should be updated with Linear metadata
    assert len(updated_graph_info) == 1
    assert updated_graph_info[0][1] == "iss_101"
    assert updated_graph_info[0][2] == "ENG-101"


@pytest.mark.asyncio
async def test_linear_pusher_dedup_comments_on_existing_issue() -> None:
    added_comments: list[tuple[str, str]] = []
    linked_mentioned_in: list[tuple[str, str]] = []

    async def mock_get_open_actions(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "id": "existing_action_id",
                "task": "Deploy Linear GraphQL client",
                "linear_id": "iss_existing_99",
                "linear_identifier": "ENG-99",
                "linear_url": "https://linear.app/team/issue/ENG-99",
                "embedding": [1.0, 0.0, 0.0],
            }
        ]

    async def mock_embed(text: str) -> list[float]:
        return [1.0, 0.0, 0.0]  # Exact match

    async def mock_add_comment(issue_id: str, body: str) -> dict[str, Any]:
        added_comments.append((issue_id, body))
        return {"id": "comm_99", "body": body}

    async def mock_link_mentioned_in(action_id: str, meeting_id: str) -> None:
        linked_mentioned_in.append((action_id, meeting_id))

    settings = Settings(
        linear_api_key="test_api_key",
        linear_team_id="team_1",
        linear_confidence_threshold=0.6,
        linear_dedup_enabled=True,
        linear_dedup_threshold=0.85,
    )
    meeting = _sample_meeting()

    created_ids = await linear_pusher.push_action_items_to_linear(
        [meeting.action_items[0]],  # Only the first item
        meeting,
        source_id="gmail_thread_abc123",
        settings=settings,
        get_open_actions=mock_get_open_actions,
        embed=mock_embed,
        add_comment=mock_add_comment,
        link_mentioned_in=mock_link_mentioned_in,
    )

    # Near-duplicate should NOT create a new Linear issue
    assert created_ids == []
    assert len(added_comments) == 1
    assert added_comments[0][0] == "iss_existing_99"
    assert "Referenced again in meeting" in added_comments[0][1]
    assert len(linked_mentioned_in) == 1
