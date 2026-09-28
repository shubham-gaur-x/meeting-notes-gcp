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
