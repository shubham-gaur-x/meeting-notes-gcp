"""Tests for Server-Sent Events (SSE) token streaming on memory query."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from meeting_notes.memory import retrieval


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_stream_memory_query_generator() -> None:
    """Test retrieval.stream_memory_query directly."""
    with (
        patch("meeting_notes.memory.retrieval.extract_entities", new_callable=AsyncMock) as mock_extract,
        patch("meeting_notes.memory.retrieval.assemble_context", new_callable=AsyncMock) as mock_context,
        patch("meeting_notes.memory.retrieval._chat", new_callable=AsyncMock) as mock_chat,
        patch("meeting_notes.memory.episodic.log_session", new_callable=AsyncMock),
    ):
        mock_extract.return_value = {"people": ["Alice"], "topics": ["Dataform"], "date_hint": None}
        mock_context.return_value = (["- Task: Build pipeline [OPEN] (Alice)"], ["node_1"])
        mock_chat.return_value = {"answer": "Alice is building the Dataform pipeline."}

        events = []
        async for chunk in retrieval.stream_memory_query("What is Alice working on?"):
            events.append(chunk)

        assert len(events) >= 3
        # First chunk is context
        assert events[0]["event"] == "context"
        assert events[0]["node_ids"] == ["node_1"]
        assert events[0]["entities"]["people"] == ["Alice"]

        # Intermediate chunks are tokens
        token_deltas = [e["delta"] for e in events if e.get("event") == "token"]
        assert "".join(token_deltas) == "Alice is building the Dataform pipeline."

        # Final chunk is done with followups
        done_event = [e for e in events if e.get("event") == "done"][0]
        assert len(done_event["suggested_followups"]) > 0


@pytest.mark.asyncio
async def test_memory_query_endpoint_streaming(app) -> None:
    """Test POST /graph/memory/query?stream=true returns text/event-stream."""
    with (
        patch("meeting_notes.memory.retrieval.extract_entities", new_callable=AsyncMock) as mock_extract,
        patch("meeting_notes.memory.retrieval.assemble_context", new_callable=AsyncMock) as mock_context,
        patch("meeting_notes.memory.retrieval._chat", new_callable=AsyncMock) as mock_chat,
        patch("meeting_notes.memory.episodic.log_session", new_callable=AsyncMock),
    ):
        mock_extract.return_value = {"people": [], "topics": ["Migration"], "date_hint": None}
        mock_context.return_value = (["- Fact: BigQuery migration in progress"], ["node_bq"])
        mock_chat.return_value = {"answer": "The BigQuery migration is underway."}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/graph/memory/query?stream=true",
                json={"question": "What is the migration status?"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            lines = [line for line in resp.text.split("\n") if line.startswith("data: ")]
            assert len(lines) >= 3

            first_payload = json.loads(lines[0][6:])
            assert first_payload["event"] == "context"
            assert first_payload["node_ids"] == ["node_bq"]


@pytest.mark.asyncio
async def test_memory_query_endpoint_non_streaming_compatibility(app) -> None:
    """Test POST /graph/memory/query without stream=true returns standard JSON."""
    with (
        patch("meeting_notes.memory.retrieval.extract_entities", new_callable=AsyncMock) as mock_extract,
        patch("meeting_notes.memory.retrieval.assemble_context", new_callable=AsyncMock) as mock_context,
        patch("meeting_notes.memory.retrieval._chat", new_callable=AsyncMock) as mock_chat,
        patch("meeting_notes.memory.episodic.log_session", new_callable=AsyncMock),
    ):
        mock_extract.return_value = {"people": [], "topics": [], "date_hint": None}
        mock_context.return_value = (["- Fact: Demo fact"], ["node_demo"])
        mock_chat.return_value = {"answer": "Standard JSON response."}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/graph/memory/query",
                json={"question": "Tell me about demo."},
            )
            assert resp.status_code == 200
            assert "application/json" in resp.headers["content-type"]
            data = resp.json()
            assert data["answer"] == "Standard JSON response."
            assert data["node_ids"] == ["node_demo"]
