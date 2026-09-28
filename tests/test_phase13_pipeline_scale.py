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
    barrier_reached = asyncio.Event()
    release_gate = asyncio.Event()

    async def slow_process(record: StagedRecord, adapter: Any) -> None:
        nonlocal active, peak
        async with lock:
            active += 1
            if active > peak:
                peak = active
            if active == 3:
                barrier_reached.set()
        await release_gate.wait()
        async with lock:
            active -= 1

    records = [_make_staged(f"r{i}") for i in range(6)]
    drain_task = asyncio.create_task(
        drain_batch(
            records,
            process=slow_process,
            sync_jira=None,
            concurrency_limit=3,
        )
    )

    await barrier_reached.wait()
    assert peak == 3
    assert active == 3
    release_gate.set()
    result = await drain_task

    assert result.processed == 6
    assert result.errors == 0


@pytest.mark.asyncio
async def test_drain_batch_records_failure_and_routes_to_dlq() -> None:
    """Verify failing records trigger record_failure with attempt increments."""
    failed_calls: list[tuple[str, str]] = []

    async def flaky_process(record: StagedRecord, adapter: Any) -> None:
        if record.id == "poison":
            raise ValueError("Corrupted record payload")
        return None

    async def mock_record_failure(
        record_id: str, error: str, max_attempts: int = 3
    ) -> tuple[int, bool, str]:
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
        semaphore=asyncio.Semaphore(5),
        embed_batch_fn=fake_batch_embed,
    )

    assert count == 2
    assert len(batch_calls) == 1
    assert batch_calls[0] == ["Task one", "Task two"]


@pytest.mark.asyncio
async def test_vector_embed_pending_bounds_concurrency_with_semaphore_in_batch_mode() -> None:
    """Verify _embed_pending acquires the shared semaphore even when embed_batch_fn is provided."""
    sem = asyncio.Semaphore(1)
    acquired_under_sem = False

    async def fake_batch_embed(texts: list[str], **kwargs: Any) -> list[list[float] | None]:
        nonlocal acquired_under_sem
        # Since sem was initialized with 1, locked() being True confirms semaphore was acquired
        if sem.locked():
            acquired_under_sem = True
        return [[0.1] * 768 for _ in texts]

    rows = [{"id": "act-1", "task": "Task one"}]

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

    await vector._embed_pending(
        "MATCH ... RETURN a.id AS id, a.task AS task",
        "MATCH ... SET a.embedding = $embedding",
        "meet-123",
        "task",
        driver=_Driver(),
        settings=Settings(llm_backend="fake"),
        embed=None,
        semaphore=sem,
        embed_batch_fn=fake_batch_embed,
    )

    assert acquired_under_sem is True


@pytest.mark.asyncio
async def test_vector_embed_pending_multi_batch_concurrency_ceiling() -> None:
    """Verify shared semaphore enforces concurrency ceiling across multiple concurrent batch operations."""
    sem = asyncio.Semaphore(2)
    active = 0
    peak = 0
    lock = asyncio.Lock()
    barrier_reached = asyncio.Event()
    release_gate = asyncio.Event()

    async def fake_batch_embed(texts: list[str], **kwargs: Any) -> list[list[float] | None]:
        nonlocal active, peak
        async with lock:
            active += 1
            if active > peak:
                peak = active
            if active == 2:
                barrier_reached.set()
        await release_gate.wait()
        async with lock:
            active -= 1
        return [[0.1] * 768 for _ in texts]

    class _Session:
        async def run(self, cypher: str, **kwargs: Any) -> Any:
            class _Result:
                def __aiter__(self):
                    self._it = iter([{"id": f"act-{i}", "task": f"Task {i}"} for i in range(5)])
                    return self

                async def __anext__(self):
                    try:
                        return next(self._it)
                    except StopIteration:
                        raise StopAsyncIteration from None

            return _Result() if "RETURN" in cypher else None

        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    class _Driver:
        def session(self) -> _Session:
            return _Session()

    driver = _Driver()
    settings = Settings(llm_backend="fake", embedding_concurrency=2)

    # Launch 6 concurrent _embed_pending calls sharing the same semaphore of capacity 2
    tasks = [
        vector._embed_pending(
            "MATCH ... RETURN a.id AS id, a.task AS task",
            "MATCH ... SET a.embedding = $embedding",
            f"meet-{i}",
            "task",
            driver=driver,
            settings=settings,
            embed=None,
            semaphore=sem,
            embed_batch_fn=fake_batch_embed,
        )
        for i in range(6)
    ]
    task_future = asyncio.gather(*tasks)

    await barrier_reached.wait()
    assert peak == 2
    assert active == 2
    assert sem.locked() is True

    release_gate.set()
    results = await task_future

    assert len(results) == 6
    assert all(count == 5 for count in results)


@pytest.mark.asyncio
async def test_vector_embed_pending_preserves_per_item_concurrency_ceiling() -> None:
    """Verify per-item embedding respects semaphore concurrency ceiling when embed_batch_fn is None."""
    sem = asyncio.Semaphore(2)
    active = 0
    peak = 0
    lock = asyncio.Lock()
    barrier_reached = asyncio.Event()
    release_gate = asyncio.Event()

    async def fake_embed_single(text: str, **kwargs: Any) -> list[float]:
        nonlocal active, peak
        async with lock:
            active += 1
            if active > peak:
                peak = active
            if active == 2:
                barrier_reached.set()
        await release_gate.wait()
        async with lock:
            active -= 1
        return [0.1] * 768

    rows = [{"id": f"act-{i}", "task": f"Task {i}"} for i in range(6)]

    class _Session:
        async def run(self, cypher: str, **kwargs: Any) -> Any:
            class _Result:
                def __aiter__(self):
                    self._it = iter(rows)
                    return self

                async def __anext__(self):
                    try:
                        return next(self._it)
                    except StopIteration:
                        raise StopAsyncIteration from None

            return _Result() if "RETURN" in cypher else None

        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    class _Driver:
        def session(self) -> _Session:
            return _Session()

    embed_task = asyncio.create_task(
        vector._embed_pending(
            "MATCH ... RETURN a.id AS id, a.task AS task",
            "MATCH ... SET a.embedding = $embedding",
            "meet-123",
            "task",
            driver=_Driver(),
            settings=Settings(llm_backend="fake"),
            embed=fake_embed_single,
            semaphore=sem,
            embed_batch_fn=None,
        )
    )

    await barrier_reached.wait()
    assert peak == 2
    assert active == 2
    assert sem.locked() is True

    release_gate.set()
    count = await embed_task

    assert count == 6


def test_should_use_linear_fail_safe_routing() -> None:
    from meeting_notes.dev_agent.orchestrator import _should_use_linear

    # 1. Jira only mode
    jira_settings = Settings(issue_tracker="jira", jira_project_key="SCRUM", linear_api_key="lin-key")
    assert _should_use_linear("SCRUM-12", jira_settings) is False
    assert _should_use_linear("ENG-42", jira_settings) is False

    # 2. Linear only mode
    linear_settings = Settings(issue_tracker="linear", linear_api_key="lin-key")
    assert _should_use_linear("ENG-42", linear_settings) is True
    assert _should_use_linear("SCRUM-12", linear_settings) is True

    # 3. Both mode: Jira prefix matches -> Jira, Linear format -> Linear, Malformed -> raises ValueError
    both_settings = Settings(
        issue_tracker="both",
        jira_project_key="SCRUM",
        linear_api_key="lin-key",
        jira_enabled=True,
    )
    assert _should_use_linear("SCRUM-12", both_settings) is False
    assert _should_use_linear("ENG-42", both_settings) is True
    assert _should_use_linear("11111111-2222-3333-4444-555555555555", both_settings) is True
    with pytest.raises(ValueError, match="Ambiguous tracker key"):
        _should_use_linear("MALFORMED_NO_HYPHEN", both_settings)


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


@pytest.mark.asyncio
async def test_dlq_db_inspection_and_replay() -> None:
    """Verify list_dead_letter_records, replay, and get_queue_stats db procedures."""
    from datetime import UTC, datetime

    from meeting_notes import db

    executed_queries: list[str] = []

    class FakeConn:
        async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
            executed_queries.append(query)
            return [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "source_id": "bad-email-1",
                    "source_type": "email",
                    "payload": '{"text": "malformed"}',
                    "fetched_at": datetime.now(UTC),
                    "processed": True,
                    "attempts": 3,
                    "last_error": "JSONDecodeError: Unterminated string",
                    "status": "dead_letter",
                }
            ]

        async def fetchval(self, query: str, *args: Any) -> Any:
            executed_queries.append(query)
            if query == db._REPLAY_DLQ_SQL:
                return args[0]
            return None

        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any]:
            executed_queries.append(query)
            return {"total": 10, "pending": 4, "retry": 1, "dead_letter": 2, "processed": 3}

        async def execute(self, query: str, *args: Any) -> str:
            executed_queries.append(query)
            if query == db._REPLAY_ALL_DLQ_SQL:
                return "UPDATE 2"
            return "UPDATE 0"

    fake_conn = FakeConn()

    class FakePool:
        def acquire(self) -> Any:
            class _Ctx:
                async def __aenter__(self) -> FakeConn:
                    return fake_conn

                async def __aexit__(self, *exc: Any) -> bool:
                    return False

            return _Ctx()

        async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
            return await fake_conn.fetch(query, *args)

        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any]:
            return await fake_conn.fetchrow(query, *args)

    pool = FakePool()  # type: ignore[assignment]

    dlq_records = await db.list_dead_letter_records(limit=10, pool=pool)
    assert len(dlq_records) == 1
    assert dlq_records[0].source_id == "bad-email-1"
    assert dlq_records[0].attempts == 3
    assert dlq_records[0].status == "dead_letter"

    replayed = await db.replay_dead_letter_record("11111111-1111-1111-1111-111111111111", pool=pool)
    assert replayed is True

    replayed_all = await db.replay_all_dead_letter_records(pool=pool)
    assert replayed_all == 2

    stats = await db.get_queue_stats(pool=pool)
    assert stats["total"] == 10
    assert stats["dead_letter"] == 2
    assert stats["pending"] == 4

    assert db._LIST_DLQ_SQL in executed_queries
    assert db._REPLAY_DLQ_SQL in executed_queries
    assert db._REPLAY_ALL_DLQ_SQL in executed_queries
    assert db._QUEUE_STATS_SQL in executed_queries


@pytest.mark.asyncio
async def test_pipeline_dlq_api_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test /pipeline/stats, /pipeline/dlq, and /pipeline/dlq/replay REST endpoints."""
    from httpx import ASGITransport, AsyncClient

    from api.main import create_app
    from meeting_notes.models import StagedRecord

    async def mock_stats() -> dict[str, int]:
        return {"total": 5, "pending": 2, "retry": 0, "dead_letter": 1, "processed": 2}

    valid_uuid = "11111111-1111-1111-1111-111111111111"

    async def mock_list_dlq(limit: int = 50) -> list[StagedRecord]:
        return [
            StagedRecord(
                id=valid_uuid,
                source_id="msg-42",
                source_type="email",
                payload={"bad": True},
                fetched_at="2026-09-09T12:00:00Z",
                processed=True,
                attempts=3,
                last_error="ValidationError: Missing title",
                status="dead_letter",
            )
        ]

    async def mock_replay_one(rec_id: str) -> bool:
        return rec_id == valid_uuid

    async def mock_replay_all() -> int:
        return 1

    monkeypatch.setattr("meeting_notes.db.get_queue_stats", mock_stats)
    monkeypatch.setattr("meeting_notes.db.list_dead_letter_records", mock_list_dlq)
    monkeypatch.setattr("meeting_notes.db.replay_dead_letter_record", mock_replay_one)
    monkeypatch.setattr("meeting_notes.db.replay_all_dead_letter_records", mock_replay_all)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. GET /pipeline/stats
        resp = await client.get("/pipeline/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["total"] == 5
        assert data["stats"]["dead_letter"] == 1

        # 2. GET /pipeline/dlq
        resp = await client.get("/pipeline/dlq")
        assert resp.status_code == 200
        dlq_data = resp.json()
        assert dlq_data["count"] == 1
        assert dlq_data["records"][0]["source_id"] == "msg-42"
        assert dlq_data["records"][0]["attempts"] == 3

        # 3. POST /pipeline/dlq/replay (single record with valid UUID)
        resp = await client.post("/pipeline/dlq/replay", json={"record_id": valid_uuid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "replayed"
        assert resp.json()["record_id"] == valid_uuid

        # 4. POST /pipeline/dlq/replay with invalid UUID format -> 400 Bad Request
        bad_resp = await client.post("/pipeline/dlq/replay", json={"record_id": "not-a-valid-uuid"})
        assert bad_resp.status_code == 400
        assert "must be a valid UUID" in bad_resp.json()["detail"]

        # 5. POST /pipeline/dlq/replay (all)
        resp = await client.post("/pipeline/dlq/replay", json={})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

        # 6. POST /pipeline/dlq/replay with non-admin principal -> 403 Forbidden
        from meeting_notes.access_control import Principal
        from api.deps import principal
        member_principal = Principal(name="test-member", role="member")
        app.dependency_overrides[principal] = lambda: member_principal
        forbidden_resp = await client.post("/pipeline/dlq/replay", json={})
        assert forbidden_resp.status_code == 403
        assert "administrative role required" in forbidden_resp.json()["detail"]
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_find_sprint_candidates_resilient_to_individual_linear_issue_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify one failing Linear issue evaluation does not discard remaining valid issues."""
    from meeting_notes.dev_agent import orchestrator

    fake_issues = [
        {"id": "lin-fail", "identifier": "ENG-1", "title": "Broken", "description": "Fails"},
        {"id": "lin-ok", "identifier": "ENG-2", "title": "Working", "description": "Succeeds"},
    ]

    async def mock_search_issues(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        return fake_issues

    async def mock_confidence(key: str) -> float:
        if key == "ENG-1":
            raise RuntimeError("Corrupted graph node")
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
    assert candidates[0]["key"] == "ENG-2"
    assert candidates[0]["tracker"] == "linear"


@pytest.mark.asyncio
async def test_default_get_issue_detail_linear_does_not_fall_through_to_jira(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Linear API failures surface errors loudly and NEVER attempt Jira."""
    from meeting_notes.dev_agent import orchestrator

    async def mock_linear_fail(key: str, **kwargs: Any) -> Any:
        raise RuntimeError("Linear connection timeout")

    jira_called = False

    async def mock_jira_detail(key: str, **kwargs: Any) -> Any:
        nonlocal jira_called
        jira_called = True
        return {"key": key, "summary": "Jira ticket"}

    monkeypatch.setattr("meeting_notes.linear_client.get_issue", mock_linear_fail)
    monkeypatch.setattr("meeting_notes.jira_client.get_issue_detail", mock_jira_detail)

    settings = Settings(
        issue_tracker="both",
        jira_project_key="SCRUM",
        linear_api_key="test-key",
    )

    with pytest.raises(RuntimeError, match="Linear connection timeout"):
        await orchestrator._default_get_issue_detail("ENG-42", settings=settings)

    assert jira_called is False, "Expected Linear failure to NOT fall through to Jira"


@pytest.mark.asyncio
async def test_drain_batch_record_failure_exception_resilience() -> None:
    """Verify drain_batch survives even if record_failure itself raises."""
    async def failing_process(record: StagedRecord, adapter: Any) -> None:
        raise ValueError("Bad record")

    async def failing_record_failure(record_id: str, error: str) -> tuple[int, bool, str]:
        raise RuntimeError("Postgres connection dropped")

    record = _make_staged("r-crash")
    result = await drain_batch(
        [record],
        process=failing_process,
        sync_jira=None,
        record_failure=failing_record_failure,
    )

    assert result.errors == 1
    assert result.processed == 0


@pytest.mark.asyncio
async def test_record_drain_failure_quarantine_boundary() -> None:
    """Verify db.record_drain_failure transitions to dead_letter at exact max_attempts boundary."""
    from meeting_notes import db

    class FakeConn:
        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any]:
            record_id, err, max_att = args
            return {"attempts": 3, "processed": False, "status": "dead_letter"}

    class FakePool:
        def acquire(self) -> Any:
            class _Ctx:
                async def __aenter__(self) -> FakeConn:
                    return FakeConn()

                async def __aexit__(self, *exc: Any) -> bool:
                    return False

            return _Ctx()

    attempts, processed, status = await db.record_drain_failure(
        "11111111-1111-1111-1111-111111111111",
        "Poison pill payload",
        max_attempts=3,
        pool=FakePool(),  # type: ignore[arg-type]
    )

    assert attempts == 3
    assert processed is False
    assert status == "dead_letter"


@pytest.mark.asyncio
async def test_record_drain_failure_retry_below_boundary() -> None:
    """Verify db.record_drain_failure keeps status as retry below max_attempts."""
    from meeting_notes import db

    class FakeConn:
        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any]:
            return {"attempts": 1, "processed": False, "status": "retry"}

    class FakePool:
        def acquire(self) -> Any:
            class _Ctx:
                async def __aenter__(self) -> FakeConn:
                    return FakeConn()

                async def __aexit__(self, *exc: Any) -> bool:
                    return False

            return _Ctx()

    attempts, processed, status = await db.record_drain_failure(
        "11111111-1111-1111-1111-111111111111",
        "Transient network blip",
        max_attempts=3,
        pool=FakePool(),  # type: ignore[arg-type]
    )

    assert attempts == 1
    assert processed is False
    assert status == "retry"


@pytest.mark.asyncio
async def test_mark_processed_db_execution() -> None:
    """Verify db.mark_processed executes _MARK_PROCESSED_SQL with target record id."""
    from meeting_notes import db

    executed: list[tuple[str, Any]] = []

    class FakeConn:
        async def execute(self, query: str, *args: Any) -> str:
            executed.append((query, args))
            return "UPDATE 1"

    class FakePool:
        def acquire(self) -> Any:
            class _Ctx:
                async def __aenter__(self) -> FakeConn:
                    return FakeConn()

                async def __aexit__(self, *exc: Any) -> bool:
                    return False

            return _Ctx()

    rec_id = "11111111-1111-1111-1111-111111111111"
    await db.mark_processed(rec_id, pool=FakePool())  # type: ignore[arg-type]

    assert len(executed) == 1
    assert executed[0][0] == db._MARK_PROCESSED_SQL
    assert executed[0][1] == (rec_id,)
    assert "last_error = NULL" in db._MARK_PROCESSED_SQL


@pytest.mark.asyncio
async def test_claim_batch_excludes_dead_letter_in_query() -> None:
    """Verify claim_batch passes limit and max_attempts to CLAIM_SQL with dead_letter exclusion."""
    from meeting_notes import db

    executed: list[tuple[str, Any]] = []

    class FakeConn:
        def transaction(self) -> Any:
            class _Tx:
                async def __aenter__(self) -> None:
                    pass

                async def __aexit__(self, *exc: Any) -> bool:
                    return False

            return _Tx()

        async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
            executed.append((query, args))
            return []

    class FakePool:
        def acquire(self) -> Any:
            class _Ctx:
                async def __aenter__(self) -> FakeConn:
                    return FakeConn()

                async def __aexit__(self, *exc: Any) -> bool:
                    return False

            return _Ctx()

    records = await db.claim_batch(limit=25, max_attempts=4, pool=FakePool())  # type: ignore[arg-type]
    assert records == []
    assert len(executed) == 1
    assert executed[0][0] == db.CLAIM_SQL
    assert executed[0][1] == (25, 4)
    assert "coalesce(status, 'pending') != 'dead_letter'" in db.CLAIM_SQL


def test_tracker_routing_with_jira_disabled() -> None:
    """Verify tracker routing routes to Linear or raises when Jira is disabled."""
    from meeting_notes.dev_agent import orchestrator

    settings_linear_only = Settings(
        issue_tracker="both",
        linear_api_key="linear-secret",
        jira_enabled=False,
    )
    assert orchestrator._should_use_linear("ENG-101", settings_linear_only) is True
    assert orchestrator._should_use_linear("ABC-999", settings_linear_only) is True
    assert (
        orchestrator._should_use_linear(
            "11111111-2222-3333-4444-555555555555", settings_linear_only
        )
        is True
    )

    with pytest.raises(ValueError, match="Invalid Linear issue key or identifier"):
        orchestrator._should_use_linear("MALFORMED_NO_HYPHEN", settings_linear_only)


@pytest.mark.asyncio
async def test_orchestrator_operations_raise_when_jira_disabled_and_no_linear() -> None:
    """Verify orchestrator operations loudly raise when Jira is disabled and Linear is unavailable."""
    from meeting_notes.dev_agent import orchestrator

    settings_no_trackers = Settings(
        issue_tracker="jira",
        jira_enabled=False,
        linear_api_key="",
    )

    with pytest.raises(RuntimeError, match="Jira is disabled and Linear is not configured"):
        await orchestrator._default_transition_issue("SCRUM-1", "Done", settings=settings_no_trackers)

    with pytest.raises(RuntimeError, match="Jira is disabled and Linear is not configured"):
        await orchestrator._default_add_comment("SCRUM-1", "Hello", settings=settings_no_trackers)

    with pytest.raises(RuntimeError, match="Jira is disabled and Linear is not configured"):
        await orchestrator._default_get_issue_detail("SCRUM-1", settings=settings_no_trackers)


@pytest.mark.asyncio
async def test_default_add_comment_linear_raises_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify _default_add_comment raises RuntimeError when Linear issue is not found."""
    from meeting_notes.dev_agent import orchestrator

    async def mock_linear_get_empty(key: str, **kwargs: Any) -> Any:
        return None

    monkeypatch.setattr("meeting_notes.linear_client.get_issue", mock_linear_get_empty)
    settings = Settings(linear_api_key="test-key")

    with pytest.raises(RuntimeError, match="Linear issue ENG-99 not found for comment"):
        await orchestrator._default_add_comment("ENG-99", "Test comment", settings=settings)


@pytest.mark.asyncio
async def test_embed_batch_size_mismatch_raises() -> None:
    """Verify embed_batch raises ValueError if the API returns fewer embeddings than inputs."""
    import json

    from meeting_notes import llm_client

    async def fake_vertex_transport_truncated(url: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        return json.dumps({"predictions": [{"embeddings": {"values": [0.1] * 768}}]})

    settings_vertex = Settings(
        llm_backend="vertex",
        vertex_embedding_model="text-embedding-004",
        vertex_location="us-central1",
        gcp_project_id="test-proj",
        embedding_dimension=768,
    )

    with pytest.raises(ValueError, match="Vertex batchEmbed returned 1 predictions for 2 inputs"):
        await llm_client.embed_batch(["text1", "text2"], settings=settings_vertex, transport=fake_vertex_transport_truncated)

    async def fake_gemini_transport_truncated(url: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        return json.dumps({"embeddings": [{"values": [0.1] * 768}]})

    settings_gemini = Settings(
        llm_backend="gemini",
        gemini_embedding_model="text-embedding-004",
        gemini_api_key="fake-key",
        embedding_dimension=768,
    )

    with pytest.raises(ValueError, match="Gemini batchEmbed returned 1 embeddings for 2 inputs"):
        await llm_client.embed_batch(["text1", "text2"], settings=settings_gemini, transport=fake_gemini_transport_truncated)


@pytest.mark.asyncio
async def test_drain_batch_with_default_record_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify drain_batch works end-to-end with the real _default_record_failure and db."""
    from meeting_notes import db
    from meeting_notes.pipeline_drain import _default_record_failure

    db_calls: list[tuple[str, str, int]] = []

    async def mock_db_record_failure(record_id: str, error: str, max_attempts: int = 3, **kwargs: Any) -> tuple[int, bool, str]:
        db_calls.append((record_id, error, max_attempts))
        return 1, False, "retry"

    monkeypatch.setattr(db, "record_drain_failure", mock_db_record_failure)

    async def failing_process(record: StagedRecord, adapter: Any) -> None:
        raise RuntimeError("Process exploded")

    record = _make_staged("r-default-failure")
    settings = Settings(pipeline_max_attempts=5)
    result = await drain_batch(
        [record],
        process=failing_process,
        sync_jira=None,
        record_failure=_default_record_failure,
        settings=settings,
    )

    assert result.errors == 1
    assert len(db_calls) == 1
    assert db_calls[0] == ("r-default-failure", "Process exploded", 5)


@pytest.mark.asyncio
async def test_orchestrator_process_ticket_ambiguous_key_failure_handling() -> None:
    """Verify an ambiguous key that raises ValueError in routing is cleanly caught and fails the ticket without crashing batch."""
    from meeting_notes.dev_agent import orchestrator
    from meeting_notes.dev_agent import lifecycle as lc

    run_finished = False
    finished_state = None
    finished_error = None

    async def mock_claim_run(key: str, state: str, branch: str) -> None:
        pass

    async def mock_finish_run(key: str, state: str, error: str | None = None) -> None:
        nonlocal run_finished, finished_state, finished_error
        run_finished = True
        finished_state = state
        finished_error = error

    async def mock_set_state(key: str, state: str) -> None:
        pass

    async def mock_remove_worktree(repo_dir: str, work_dir: str, branch: str, ignore_errors: bool = True) -> None:
        pass

    settings = Settings(
        issue_tracker="both",
        jira_project_key="SCRUM",
        linear_api_key="lin-secret",
        jira_enabled=True,
    )

    ticket = {"key": "MALFORMED_NO_HYPHEN", "tracker": "ambiguous"}

    await orchestrator.process_ticket(
        ticket,
        settings,
        claim_run=mock_claim_run,
        finish_run=mock_finish_run,
        set_state=mock_set_state,
        remove_worktree=mock_remove_worktree,
    )

    assert run_finished is True
    assert finished_state == lc.FAILED
    assert "Ambiguous tracker key 'MALFORMED_NO_HYPHEN'" in (finished_error or "")


@pytest.mark.asyncio
async def test_default_tracker_helpers_raise_on_ambiguous_key() -> None:
    """Verify default tracker helpers fail loudly when given an ambiguous key in both mode."""
    from meeting_notes.dev_agent import orchestrator

    settings = Settings(
        issue_tracker="both",
        jira_project_key="SCRUM",
        linear_api_key="lin-secret",
        jira_enabled=True,
    )

    with pytest.raises(ValueError, match="Ambiguous tracker key 'AMBIGUOUS'"):
        await orchestrator._default_transition_issue("AMBIGUOUS", "Done", settings=settings)

    with pytest.raises(ValueError, match="Ambiguous tracker key 'AMBIGUOUS'"):
        await orchestrator._default_add_comment("AMBIGUOUS", "Hello", settings=settings)

    with pytest.raises(ValueError, match="Ambiguous tracker key 'AMBIGUOUS'"):
        await orchestrator._default_get_issue_detail("AMBIGUOUS", settings=settings)


def test_schema_sql_includes_backward_compat_migration() -> None:
    """Verify SCHEMA_SQL contains ALTER TABLE statements for existing staged_records tables."""
    from meeting_notes.db import SCHEMA_SQL

    assert "ALTER TABLE staged_records ADD COLUMN IF NOT EXISTS attempts" in SCHEMA_SQL
    assert "ALTER TABLE staged_records ADD COLUMN IF NOT EXISTS last_error" in SCHEMA_SQL
    assert "ALTER TABLE staged_records ADD COLUMN IF NOT EXISTS status" in SCHEMA_SQL


@pytest.mark.asyncio
async def test_queue_stats_does_not_double_count_quarantined_records() -> None:
    """Verify that get_queue_stats keeps dead_letter and processed mutually exclusive."""
    from meeting_notes import db

    class FakePool:
        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any]:
            # Simulate a database containing 1 pending, 1 retry, 1 dead_letter, and 2 processed
            return {
                "total": 5,
                "pending": 1,
                "retry": 1,
                "dead_letter": 1,
                "processed": 2,
            }

    stats = await db.get_queue_stats(pool=FakePool())  # type: ignore[arg-type]
    assert stats["total"] == 5
    assert stats["dead_letter"] == 1
    assert stats["processed"] == 2
    assert stats["pending"] == 1
    assert stats["retry"] == 1
    # Mutually exclusive: sum of distinct buckets equals total
    assert stats["pending"] + stats["retry"] + stats["dead_letter"] + stats["processed"] == stats["total"]





