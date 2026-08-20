"""Jira connector — new code over a ported client.

Incremental by JQL `updated >= watermark`, with the issue's own `updated`
field as the new watermark.

**Disabled Jira is a no-op, not an error.** `JIRA_ENABLED` defaults to false
so tiers 0 and 1 run the whole pipeline without a Jira account; a connector
that raised here would break `make demo` for anyone without one.
"""

from __future__ import annotations

from typing import Any

import structlog

from meeting_notes import jira_client
from meeting_notes.config import Settings, get_settings
from meeting_notes.jira_client import Transport, adf_to_text
from meeting_notes.sources.base import FetchedRecord

log = structlog.get_logger()

_FIELDS = ["summary", "description", "status", "assignee", "reporter", "updated", "issuetype"]


class JiraSource:
    source_type = "jira_issue"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: Transport | None = None,
        max_results: int = 50,
    ) -> None:
        self._settings = settings or get_settings()
        self._transport = transport
        self._max_results = max_results

    def _jql(self, since: str | None) -> str:
        project = self._settings.jira_project_key
        clauses = [f"project = {project}"] if project else []
        if since:
            # JQL wants "yyyy/MM/dd HH:mm"; the watermark is an ISO timestamp.
            stamp = since[:16].replace("T", " ").replace("-", "/")
            clauses.append(f'updated >= "{stamp}"')
        return " AND ".join(clauses) + " ORDER BY updated ASC" if clauses else "ORDER BY updated ASC"

    async def fetch(self, since: str | None) -> list[FetchedRecord]:
        if not self._settings.jira_enabled:
            log.info("jira.disabled", source_event="skip")
            return []

        issues = await jira_client.search_issues(
            self._jql(since),
            fields=_FIELDS,
            max_results=self._max_results,
            settings=self._settings,
            transport=self._transport,
        )

        records: list[FetchedRecord] = []
        for issue in issues:
            fields: dict[str, Any] = issue.get("fields") or {}
            records.append(
                FetchedRecord(
                    source_id=issue["key"],
                    source_type=self.source_type,
                    payload={
                        "key": issue["key"],
                        "summary": fields.get("summary", ""),
                        # ADF -> text, or the extractor reads a stringified dict.
                        "description": adf_to_text(fields.get("description")),
                        "status": (fields.get("status") or {}).get("name", ""),
                        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
                        "assignee": (fields.get("assignee") or {}).get("emailAddress", ""),
                        "reporter": (fields.get("reporter") or {}).get("emailAddress", ""),
                    },
                    watermark=fields.get("updated"),
                )
            )

        log.info("jira.fetched", source_event="search", count=len(records))
        return records
