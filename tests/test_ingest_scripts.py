"""Unit tests for standalone transcript and Meet history ingestion scripts."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts import ingest_meet_history, ingest_transcript


@pytest.mark.asyncio
async def test_fetch_meet_history_parses_transcripts() -> None:
    fake_conf = {
        "conferenceRecords": [
            {
                "name": "conferenceRecords/conf-123",
                "space": "Design Review",
                "startTime": "2026-09-28T10:00:00Z",
            }
        ]
    }
    fake_trans = {"transcripts": [{"name": "conferenceRecords/conf-123/transcripts/trans-456"}]}
    fake_entries = {"transcriptEntries": [{"text": "Hello team, let us review the architecture."}]}

    mock_client = AsyncMock()
    # 1. conferenceRecords
    res1 = MagicMock(status_code=200)
    res1.json.return_value = fake_conf

    # 2. transcripts
    res2 = MagicMock(status_code=200)
    res2.json.return_value = fake_trans

    # 3. entries
    res3 = MagicMock(status_code=200)
    res3.json.return_value = fake_entries

    mock_client.get.side_effect = [res1, res2, res3]

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        results = await ingest_meet_history.fetch_meet_history("mock_token")

    assert len(results) == 1
    assert results[0]["source_id"] == "conferenceRecords-conf-123"
    assert "architecture" in results[0]["text"]


@pytest.mark.asyncio
async def test_ingest_transcript_main_success(monkeypatch) -> None:
    test_args = [
        "ingest_transcript.py",
        "--title", "Sprint Retro",
        "--text", "Alex: We shipped the feature on time.",
        "--date", "2026-09-28",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    mock_result = MagicMock()
    mock_result.errors = 0

    with (
        patch("scripts.ingest_transcript.db.stage_record", new_callable=AsyncMock) as mock_stage,
        patch("scripts.ingest_transcript.db.close_pool", new_callable=AsyncMock) as mock_close,
        patch("scripts.ingest_transcript.drain_batch", new_callable=AsyncMock) as mock_drain,
    ):
        mock_stage.return_value = 101
        mock_drain.return_value = mock_result

        rc = await ingest_transcript.main()
        assert rc == 0
        assert mock_stage.await_count == 1
        assert mock_close.await_count == 1
        assert mock_drain.await_count == 1


@pytest.mark.asyncio
async def test_ingest_transcript_main_missing_content(monkeypatch) -> None:
    test_args = ["ingest_transcript.py", "--title", "Empty Retro"]
    monkeypatch.setattr(sys, "argv", test_args)

    rc = await ingest_transcript.main()
    assert rc == 1


@pytest.mark.asyncio
async def test_fetch_meet_history_error_handling() -> None:
    # 1. Test top-level conferenceRecords failure (e.g. 403 / 500)
    mock_client = AsyncMock()
    mock_client.get.return_value = MagicMock(status_code=500, text="Internal Server Error")

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        res = await ingest_meet_history.fetch_meet_history("mock_token")
        assert res == []

    # 2. Test partial failures on transcripts and entries
    fake_conf = {"conferenceRecords": [{"name": "conferenceRecords/c1", "space": "Sync"}]}
    res_conf = MagicMock(status_code=200)
    res_conf.json.return_value = fake_conf

    # Transcripts request fails
    res_trans_fail = MagicMock(status_code=404)
    mock_client.get.side_effect = [res_conf, res_trans_fail]

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        res = await ingest_meet_history.fetch_meet_history("mock_token")
        assert res == []

    # Entries request fails or has empty text
    fake_trans = {"transcripts": [{"name": "conferenceRecords/c1/transcripts/t1"}]}
    res_trans = MagicMock(status_code=200)
    res_trans.json.return_value = fake_trans
    res_entries_fail = MagicMock(status_code=500)
    mock_client.get.side_effect = [res_conf, res_trans, res_entries_fail]

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        res = await ingest_meet_history.fetch_meet_history("mock_token")
        assert res == []


@pytest.mark.asyncio
async def test_ingest_meet_history_main_auth_error() -> None:
    with patch(
        "scripts.ingest_meet_history.google_auth.get_access_token",
        side_effect=RuntimeError("Token expired"),
    ):
        rc = await ingest_meet_history.main()
        assert rc == 1


@pytest.mark.asyncio
async def test_ingest_meet_history_main_success_and_drain() -> None:
    fake_items = [{
        "source_id": "conf-test-1",
        "title": "Roadmap Review",
        "start_time": "2026-09-28T12:00:00Z",
        "text": "Jordan: All blockers resolved.",
    }]

    mock_result = MagicMock()
    mock_result.processed = 1
    mock_result.errors = 0

    with (
        patch(
            "scripts.ingest_meet_history.google_auth.get_access_token",
            new_callable=AsyncMock,
        ) as mock_auth,
        patch("scripts.ingest_meet_history.fetch_meet_history", new_callable=AsyncMock) as mock_fetch,
        patch("scripts.ingest_meet_history.db.stage_record", new_callable=AsyncMock) as mock_stage,
        patch("scripts.ingest_meet_history.drain_batch", new_callable=AsyncMock) as mock_drain,
        patch("scripts.ingest_meet_history.db.close_pool", new_callable=AsyncMock) as mock_close,
    ):
        mock_auth.return_value = "token_xyz"
        mock_fetch.return_value = fake_items
        mock_stage.return_value = 202
        mock_drain.return_value = mock_result

        rc = await ingest_meet_history.main()
        assert rc == 0
        assert mock_stage.await_count == 1
        assert mock_drain.await_count == 1
        assert mock_close.await_count == 1


def test_adr018_sql_encapsulation_in_scripts() -> None:
    """ADR-018: Ingestion scripts must NOT contain raw inline SQL."""
    import re
    from pathlib import Path

    sql_regex = re.compile(r"\b(SELECT\s+.*FROM|INSERT\s+INTO|UPDATE\s+.*SET|DELETE\s+FROM)\b", re.IGNORECASE)

    scripts_dir = Path("scripts")
    for script_name in ["ingest_meet_history.py", "ingest_transcript.py"]:
        path = scripts_dir / script_name
        assert path.exists(), f"{script_name} must exist"
        content = path.read_text(encoding="utf-8")
        matches = sql_regex.findall(content)
        assert len(matches) == 0, f"{script_name} violates ADR-018 with inline SQL: {matches}"

