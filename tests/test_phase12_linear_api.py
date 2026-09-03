"""Tests for api.routers.linear_ops."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_linear_ops_transition(app) -> None:
    with (
        patch(
            "meeting_notes.linear_client.transition_issue",
            new_callable=AsyncMock,
            return_value={"id": "iss_1", "state": {"name": "Done", "type": "completed"}},
        ),
        patch("meeting_notes.graph_client.update_action_linear_state", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/linear/transition",
                json={"issue_id": "iss_1", "state_id": "state_done_123", "action_id": "act_1"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["issue_id"] == "iss_1"
            assert data["state"] == "Done"
            assert data["is_done"] is True


@pytest.mark.asyncio
async def test_linear_ops_subtask(app) -> None:
    with (
        patch(
            "meeting_notes.linear_client.create_issue",
            new_callable=AsyncMock,
            return_value={
                "id": "iss_sub_1",
                "identifier": "ENG-55",
                "url": "https://linear.app/team/issue/ENG-55",
                "state": {"name": "Todo"},
            },
        ),
        patch("meeting_notes.graph_client.update_action_linear_info", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/linear/subtask",
                json={
                    "parent_id": "iss_parent_1",
                    "title": "Subtask title",
                    "description": "Subtask description",
                    "child_action_id": "act_child_1",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["parent_id"] == "iss_parent_1"
            assert data["identifier"] == "ENG-55"


@pytest.mark.asyncio
async def test_linear_ops_health(app) -> None:
    with patch(
        "meeting_notes.linear_client.list_projects",
        new_callable=AsyncMock,
        return_value=[{"id": "proj_1", "name": "Project Alpha"}],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/linear/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["connected"] is True
            assert data["projects_count"] == 1
