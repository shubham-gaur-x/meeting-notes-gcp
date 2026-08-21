"""Pydantic v2 models for the autonomous dev agent.

**One `state` field, not v5's parallel `state` + `status` pair.** v5 tracked
two overlapping "is this run done" facts in two columns with two different
vocabularies (`state`: TRIAGED/PLANNED/.../SHIPPED; `status`:
queued/running/pr_opened/failed) — exactly the kind of duplicated source of
truth that let `state` and the terminal-state check drift apart and produce
the `SHIPPED` resume-loop bug (ADR-020). `DevAgentRun.state` is the only
place a run's position is recorded; `lifecycle.py` is the only vocabulary.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from meeting_notes.dev_agent.lifecycle import ALL_STATES


class DevAgentRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticket_key: str
    state: str
    branch_name: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    error: str | None = None
    attempt_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Session memory (ADR-020: session_memory.py, resumable across attempts).
    state_payload: dict[str, Any] = {}

    @field_validator("state")
    @classmethod
    def _known_state(cls, v: str) -> str:
        if v not in ALL_STATES:
            raise ValueError(f"unknown lifecycle state {v!r}")
        return v

    @field_validator("state_payload", mode="before")
    @classmethod
    def _coerce_payload(cls, v: Any) -> Any:
        # asyncpg returns JSONB as a str; accept both str and dict.
        if v is None:
            return {}
        if isinstance(v, str):
            return json.loads(v) if v.strip() else {}
        return v


class JiraTicket(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    summary: str
    description: str = ""
    status: str = ""
    labels: list[str] = []
    priority: str | None = None


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    returncode: int
    result_text: str = ""
    num_turns: int | None = None
    duration_ms: int = 0
    timed_out: bool = False
