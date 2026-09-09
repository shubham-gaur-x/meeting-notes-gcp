"""Tests for Phase 13: Pipeline Scale, DLQ Resilience, and Batch Embeddings.

Verifies:
1. Bounded concurrency in `pipeline_drain.drain_batch` using semaphore.
2. Error shielding and Dead-Letter Queue (DLQ) tracking on failing records.
3. Batch embeddings via `llm_client.embed_batch` across backends.
4. High-throughput graph vector enrichment using batch embedding.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from meeting_notes import llm_client
from meeting_notes.config import Settings
from meeting_notes.memory import vector
from meeting_notes.models import StagedRecord
from meeting_notes.pipeline_drain import drain_batch


def _make_staged(
    record_id: str,
    source_type: str = "email",
    payload: dict[str, Any] | None = None,
    attempts: int = 0,
) -> StagedRecord:
    return StagedRecord(
        id=record_id,
        source_id=f"src-{record_id}",
        source_type=source_type,
        payload=payload or {},
        fetched_at="2026-09-09T00:00:00Z",
        processed=False,
        attempts=attempts,
    )


@pytest.mark.asyncio
async def test_drain_batch_runs_concurrently_within_semaphore_limit() -> None:
    """Verify drain_batch processes records concurrently without exceeding limit."""
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def slow_process(record: StagedRecord, adapter: Any) -> None:
        nonlocal active, peak
        async with lock:
            active += 1
            if active > peak:
                peak = active
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1

    records = [_make_staged(f"r{i}") for i in range(6)]
    result = await drain_batch(
        records,
        process=slow_process,
        sync_jira=None,
        concurrency_limit=3,
    )

    assert result.processed == 6
    assert result.errors == 0
    assert peak <= 3, f"Peak concurrency {peak} exceeded limit of 3"
    assert peak > 1, f"Expected concurrency > 1, got {peak}"


@pytest.mark.asyncio
async def test_drain_batch_records_failure_and_routes_to_dlq() -> None:
    """Verify failing records trigger record_failure with attempt increments."""
    failed_calls: list[tuple[str, str]] = []

    async def flaky_process(record: StagedRecord, adapter: Any) -> None:
        if record.id == "poison":
            raise ValueError("Corrupted record payload")
        return None

    async def mock_record_failure(record_id: str, error: str) -> tuple[int, bool, str]:
        failed_calls.append((record_id, error))
        return 1, False, "retry"

    records = [_make_staged("ok1"), _make_staged("poison"), _make_staged("ok2")]
    result = await drain_batch(
        records,
        process=flaky_process,
        sync_jira=None,
        record_failure=mock_record_failure,
    )

    assert result.processed == 2
    assert result.errors == 1
    assert len(failed_calls) == 1
    rec_id, err_msg = failed_calls[0]
    assert rec_id == "poison"
    assert "Corrupted record payload" in err_msg


@pytest.mark.asyncio
async def test_embed_batch_fake_backend() -> None:
    """Test embed_batch returns dimension-correct vectors for all items."""
    settings = Settings(llm_backend="fake", embedding_dimension=768)
    texts = ["Action item 1", "Action item 2", "Action item 3"]

    vectors = await llm_client.embed_batch(texts, settings=settings)

    assert len(vectors) == 3
    for v in vectors:
        assert v is not None
        assert len(v) == 768


@pytest.mark.asyncio
async def test_embed_batch_empty_list() -> None:
    vectors = await llm_client.embed_batch([])
    assert vectors == []


@pytest.mark.asyncio
async def test_vector_embed_pending_uses_batch_embed_fn() -> None:
    """Verify _embed_pending calls embed_batch_fn with all texts in one invocation."""
    batch_calls: list[list[str]] = []

    async def fake_batch_embed(texts: list[str], **kwargs: Any) -> list[list[float] | None]:
        batch_calls.append(texts)
        return [[0.1] * 768 for _ in texts]

    rows = [
        {"id": "act-1", "task": "Task one"},
        {"id": "act-2", "task": "Task two"},
    ]

    class _Result:
        def __aiter__(self):
            self._it = iter(rows)
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration from None

    class _Session:
        async def run(self, cypher: str, **kwargs: Any) -> Any:
            return _Result() if "RETURN" in cypher else None

        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    class _Driver:
        def session(self) -> _Session:
            return _Session()

    count = await vector._embed_pending(
        "MATCH ... RETURN a.id AS id, a.task AS task",
        "MATCH ... SET a.embedding = $embedding",
        "meet-123",
        "task",
        driver=_Driver(),
        settings=Settings(llm_backend="fake"),
        embed=None,
        embed_batch_fn=fake_batch_embed,
    )

    assert count == 2
    assert len(batch_calls) == 1
    assert batch_calls[0] == ["Task one", "Task two"]


@pytest.mark.asyncio
async def test_find_sprint_candidates_picks_up_linear_tickets(monkeypatch: pytest.MonkeyPatch) -> None:
    from meeting_notes.dev_agent import orchestrator

    fake_issues = [
        {
            "id": "lin-1",
            "identifier": "ENG-42",
            "title": "Add caching layer",
            "description": "Implement Redis cache in repo: acme/payments",
        }
    ]

    async def mock_search_issues(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        return fake_issues

    async def mock_confidence(key: str) -> float:
        return 0.95

    monkeypatch.setattr("meeting_notes.linear_client.search_issues", mock_search_issues)
    monkeypatch.setattr("meeting_notes.graph_client.get_action_confidence", mock_confidence)

    settings = Settings(
        issue_tracker="linear",
        linear_api_key="test-key",
        dev_agent_confidence_threshold=0.8,
    )

    candidates = await orchestrator.find_sprint_candidates(settings=settings)
    assert len(candidates) == 1
    assert candidates[0]["key"] == "ENG-42"
    assert candidates[0]["tracker"] == "linear"
    assert "repo: acme/payments" in candidates[0]["description"]
