"""Tests for meeting_notes.linear_client."""

from __future__ import annotations

from typing import Any

import pytest

from meeting_notes import linear_client
from meeting_notes.config import Settings


def test_linear_headers() -> None:
    settings = Settings(linear_api_key="lin_api_test_secret_123")
    headers = linear_client.linear_headers(settings)
    assert headers["Authorization"] == "lin_api_test_secret_123"
    assert headers["Content-Type"] == "application/json"


def test_linear_priority_mapping() -> None:
    assert linear_client.linear_priority_from_name("urgent") == 1
    assert linear_client.linear_priority_from_name("high") == 2
    assert linear_client.linear_priority_from_name("medium") == 3
    assert linear_client.linear_priority_from_name("low") == 4
    assert linear_client.linear_priority_from_name("none") == 0
    assert linear_client.linear_priority_from_name("unknown") == 0


@pytest.mark.asyncio
async def test_create_issue_success() -> None:
    recorded_payloads: list[dict[str, Any]] = []

    async def mock_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> tuple[int, Any]:
        assert json_body is not None
        recorded_payloads.append(json_body)
        return 200, {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "iss_123",
                        "identifier": "ENG-42",
                        "title": "Fix auth race condition",
                        "url": "https://linear.app/team/issue/ENG-42",
                        "priority": 2,
                        "state": {"id": "state_todo", "name": "Todo", "type": "unstarted"},
                    },
                }
            }
        }

    settings = Settings(linear_api_key="test_key", linear_team_id="team_eng_1")
    issue = await linear_client.create_issue(
        "Fix auth race condition",
        description="Detailed description",
        priority="high",
        due_date="2026-09-10",
        settings=settings,
        transport=mock_transport,
    )

    assert issue["id"] == "iss_123"
    assert issue["identifier"] == "ENG-42"
    assert issue["url"] == "https://linear.app/team/issue/ENG-42"
    assert len(recorded_payloads) == 1
    variables = recorded_payloads[0]["variables"]["input"]
    assert variables["title"] == "Fix auth race condition"
    assert variables["teamId"] == "team_eng_1"
    assert variables["priority"] == 2
    assert variables["dueDate"] == "2026-09-10"


@pytest.mark.asyncio
async def test_create_project_and_sub_issue() -> None:
    async def mock_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> tuple[int, Any]:
        assert json_body is not None
        query = json_body.get("query", "")
        if "ProjectCreate" in query:
            return 200, {
                "data": {
                    "projectCreate": {
                        "success": True,
                        "project": {
                            "id": "proj_1",
                            "name": "Cloud Migration",
                            "url": "https://linear.app/team/project/cloud-migration",
                            "state": "planned",
                        },
                    }
                }
            }
        if "IssueCreate" in query:
            return 200, {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "iss_sub_1",
                            "identifier": "ENG-43",
                            "title": "Subtask task",
                            "url": "https://linear.app/team/issue/ENG-43",
                            "parent": {"id": "iss_123", "identifier": "ENG-42"},
                        },
                    }
                }
            }
        return 400, {"errors": [{"message": "Unknown query"}]}

    settings = Settings(linear_api_key="test_key", linear_team_id="team_eng_1")

    project = await linear_client.create_project(
        "Cloud Migration", settings=settings, transport=mock_transport
    )
    assert project["id"] == "proj_1"
    assert project["name"] == "Cloud Migration"

    sub_issue = await linear_client.create_issue(
        "Subtask task",
        parent_id="iss_123",
        project_id="proj_1",
        settings=settings,
        transport=mock_transport,
    )
    assert sub_issue["id"] == "iss_sub_1"
    assert sub_issue["identifier"] == "ENG-43"


@pytest.mark.asyncio
async def test_add_comment_and_transition() -> None:
    async def mock_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> tuple[int, Any]:
        assert json_body is not None
        query = json_body.get("query", "")
        if "CommentCreate" in query:
            return 200, {
                "data": {
                    "commentCreate": {
                        "success": True,
                        "comment": {"id": "comm_1", "body": "Mentioned again in sync"},
                    }
                }
            }
        if "IssueUpdate" in query:
            return 200, {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": {
                            "id": "iss_123",
                            "identifier": "ENG-42",
                            "state": {"id": "state_done", "name": "Done", "type": "completed"},
                        },
                    }
                }
            }
        return 400, {"errors": [{"message": "Unknown query"}]}

    settings = Settings(linear_api_key="test_key", linear_team_id="team_eng_1")

    comment = await linear_client.add_comment(
        "iss_123", "Mentioned again in sync", settings=settings, transport=mock_transport
    )
    assert comment["id"] == "comm_1"

    transitioned = await linear_client.transition_issue(
        "iss_123", "state_done", settings=settings, transport=mock_transport
    )
    assert transitioned["id"] == "iss_123"
    assert transitioned["state"]["name"] == "Done"


@pytest.mark.asyncio
async def test_graphql_error_handling() -> None:
    async def mock_error_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> tuple[int, Any]:
        return 200, {"errors": [{"message": "Invalid authentication token"}]}

    settings = Settings(linear_api_key="bad_token", linear_team_id="team_eng_1")
    with pytest.raises(RuntimeError, match="Invalid authentication token"):
        await linear_client.execute_graphql(
            "query { viewer { id } }", settings=settings, transport=mock_error_transport
        )


@pytest.mark.asyncio
async def test_get_issue_and_update_issue() -> None:
    async def mock_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> tuple[int, Any]:
        assert json_body is not None
        query = json_body.get("query", "")
        if "query Issue(" in query:
            return 200, {
                "data": {
                    "issue": {
                        "id": "iss_101",
                        "identifier": "ENG-101",
                        "title": "Existing issue",
                        "priority": 2,
                        "state": {"id": "st_todo", "name": "Todo", "type": "unstarted"},
                    }
                }
            }
        if "mutation IssueUpdate(" in query:
            input_vars = json_body.get("variables", {}).get("input", {})
            return 200, {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": {
                            "id": "iss_101",
                            "identifier": "ENG-101",
                            "title": input_vars.get("title", "Existing issue"),
                            "priority": input_vars.get("priority", 2),
                            "state": {"id": "st_todo", "name": "Todo", "type": "unstarted"},
                        },
                    }
                }
            }
        return 400, {"errors": [{"message": "Unknown query"}]}

    settings = Settings(linear_api_key="test_key", linear_team_id="team_eng_1")
    issue = await linear_client.get_issue("iss_101", settings=settings, transport=mock_transport)
    assert issue is not None
    assert issue["id"] == "iss_101"
    assert issue["identifier"] == "ENG-101"

    updated = await linear_client.update_issue(
        "iss_101",
        title="Updated issue title",
        priority="urgent",
        settings=settings,
        transport=mock_transport,
    )
    assert updated["title"] == "Updated issue title"
    assert updated["priority"] == 1


@pytest.mark.asyncio
async def test_workflow_state_resolution_and_caching() -> None:
    call_count = 0

    async def mock_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> tuple[int, Any]:
        nonlocal call_count
        call_count += 1
        return 200, {
            "data": {
                "workflowStates": {
                    "nodes": [
                        {"id": "st_1", "name": "Backlog", "type": "backlog"},
                        {"id": "st_2", "name": "Todo", "type": "unstarted"},
                        {"id": "st_3", "name": "In Progress", "type": "started"},
                        {"id": "st_4", "name": "Done", "type": "completed"},
                        {"id": "st_5", "name": "Canceled", "type": "canceled"},
                    ]
                }
            }
        }

    settings = Settings(linear_api_key="test_key", linear_team_id="team_cached_1")
    done_state = await linear_client.resolve_workflow_state(
        "done", team_id="team_cached_1", settings=settings, transport=mock_transport
    )
    assert done_state is not None
    assert done_state["id"] == "st_4"
    assert done_state["name"] == "Done"

    # Second call uses cache and should not call mock_transport again
    todo_state = await linear_client.resolve_workflow_state(
        "unstarted", team_id="team_cached_1", settings=settings, transport=mock_transport
    )
    assert todo_state is not None
    assert todo_state["id"] == "st_2"
    assert call_count == 1

    # Resolve by ID directly
    direct_state = await linear_client.resolve_workflow_state(
        "st_3", team_id="team_cached_1", settings=settings, transport=mock_transport
    )
    assert direct_state is not None
    assert direct_state["name"] == "In Progress"


@pytest.mark.asyncio
async def test_create_issue_relation_and_attachment() -> None:
    async def mock_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> tuple[int, Any]:
        assert json_body is not None
        query = json_body.get("query", "")
        if "IssueRelationCreate" in query:
            return 200, {
                "data": {
                    "issueRelationCreate": {
                        "success": True,
                        "issueRelation": {
                            "id": "rel_1",
                            "type": "blocks",
                            "issue": {"id": "iss_1", "identifier": "ENG-1"},
                            "relatedIssue": {"id": "iss_2", "identifier": "ENG-2"},
                        },
                    }
                }
            }
        if "AttachmentCreate" in query:
            return 200, {
                "data": {
                    "attachmentCreate": {
                        "success": True,
                        "attachment": {
                            "id": "att_1",
                            "url": "https://mail.google.com/mail/u/0/#all/xyz",
                            "title": "Meeting Thread",
                        },
                    }
                }
            }
        return 400, {"errors": [{"message": "Unknown query"}]}

    settings = Settings(linear_api_key="test_key", linear_team_id="team_eng_1")
    rel = await linear_client.create_issue_relation(
        "iss_1", "iss_2", relation_type="blocks", settings=settings, transport=mock_transport
    )
    assert rel["id"] == "rel_1"
    assert rel["type"] == "blocks"

    att = await linear_client.create_attachment(
        "iss_1",
        "https://mail.google.com/mail/u/0/#all/xyz",
        title="Meeting Thread",
        settings=settings,
        transport=mock_transport,
    )
    assert att["id"] == "att_1"
    assert att["url"] == "https://mail.google.com/mail/u/0/#all/xyz"


@pytest.mark.asyncio
async def test_close_shared_client() -> None:
    await linear_client.close_shared_client()
    assert linear_client._shared_client is None
