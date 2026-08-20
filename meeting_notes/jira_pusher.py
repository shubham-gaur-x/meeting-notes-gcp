"""Confidence gate, dedup gate, then push to Jira. Ported from v5.

Every graph_client/jira_client call is its own injectable keyword — the same
flat-injection style `pipeline.process` uses — rather than a bundled object,
so a test only wires the calls it actually exercises. Defaults bind the real
modules.

Two gates run in this order, both exit criteria for Phase 6:

1. **Confidence.** Below `JIRA_CONFIDENCE_THRESHOLD`, the item is marked
   `needs_review` and no Jira call is attempted at all.
2. **Dedup.** A near-duplicate of an existing open item (same owner, high
   embedding similarity) links `MENTIONED_IN` and comments on the existing
   ticket instead of opening a second one.
"""

from __future__ import annotations

from typing import Any

import structlog

from meeting_notes import dedup
from meeting_notes.config import Settings, get_settings
from meeting_notes.models import ActionItem, ExtractedMeeting
from meeting_notes.utils import uuid5_id

log = structlog.get_logger()


async def _default_mark_needs_review(action_id: str, reason: str) -> None:
    from meeting_notes.graph_client import mark_action_needs_review

    await mark_action_needs_review(action_id, reason)


async def _default_get_open_actions(owner_email: str, *, exclude_id: str) -> list[dict[str, Any]]:
    from meeting_notes.graph_client import get_open_actions_for_owner

    return await get_open_actions_for_owner(owner_email, exclude_id=exclude_id)


async def _default_update_jira_key(action_id: str, jira_key: str) -> None:
    from meeting_notes.graph_client import update_action_jira_key

    await update_action_jira_key(action_id, jira_key)


async def _default_link_mentioned_in(action_id: str, meeting_id: str) -> None:
    from meeting_notes.graph_client import link_action_mentioned_in

    await link_action_mentioned_in(action_id, meeting_id)


async def _default_create_issue(**kwargs: Any) -> str:
    from meeting_notes.jira_client import create_issue

    result: str = await create_issue(**kwargs)
    return result


async def _default_embed(text: str) -> list[float] | None:
    from meeting_notes import llm_client

    return await llm_client.embed(text)


async def _default_add_comment(key: str, text: str) -> None:
    from meeting_notes.jira_client import add_comment

    await add_comment(key, text)


async def _default_active_sprint_id() -> int | None:
    from meeting_notes.jira_client import active_sprint_id

    return await active_sprint_id()


async def push_action_items(
    action_items: list[ActionItem],
    meeting: ExtractedMeeting,
    source_id: str,
    *,
    settings: Settings | None = None,
    mark_needs_review: Any = None,
    get_open_actions: Any = None,
    update_jira_key: Any = None,
    link_mentioned_in: Any = None,
    create_issue: Any = None,
    embed: Any = None,
    add_comment: Any = None,
    get_active_sprint: Any = None,
) -> list[str]:
    """Gate, dedup, then create. Returns the keys of tickets newly created."""
    settings = settings or get_settings()

    if not settings.jira_enabled or not action_items:
        return []
    if not settings.jira_api_token:
        log.warning("jira_pusher.no_token", hint="Set JIRA_API_TOKEN to enable Jira push")
        return []

    mark_needs_review = mark_needs_review or _default_mark_needs_review
    get_open_actions = get_open_actions or _default_get_open_actions
    update_jira_key = update_jira_key or _default_update_jira_key
    link_mentioned_in = link_mentioned_in or _default_link_mentioned_in
    create_issue = create_issue or _default_create_issue
    embed = embed or _default_embed
    add_comment = add_comment or _default_add_comment
    get_active_sprint = get_active_sprint or _default_active_sprint_id

    try:
        sprint_id = await get_active_sprint()
    except Exception as exc:  # noqa: BLE001 - reported, push still proceeds
        log.warning("jira_pusher.sprint_fetch_failed", error=str(exc))
        sprint_id = None

    meeting_id = uuid5_id("meeting", source_id)
    created_keys: list[str] = []

    for i, action in enumerate(action_items):
        # Must match graph_client.upsert_meeting_graph's derivation exactly,
        # or this whole function silently gates/dedups against zero rows.
        action_id = uuid5_id("action", f"{source_id}:{i}:{action.task}")

        if action.confidence < settings.jira_confidence_threshold:
            await mark_needs_review(action_id, f"confidence {action.confidence:.2f} below threshold")
            log.info(
                "jira_pusher.needs_review",
                task=action.task[:60], confidence=round(action.confidence, 2),
            )
            continue

        if settings.jira_dedup_enabled:
            duplicate = await _find_duplicate(
                action, action_id, meeting, meeting_id,
                get_open_actions=get_open_actions, embed=embed,
                link_mentioned_in=link_mentioned_in, add_comment=add_comment,
                threshold=settings.jira_dedup_threshold,
            )
            if duplicate is not None:
                continue

        description = (
            f"From meeting: {meeting.title} ({meeting.date})\n"
            f"Owner: {action.owner}\nDue: {action.due or 'not specified'}"
        )
        try:
            jira_key = await create_issue(
                summary=action.task[:255],
                description=description,
                priority=action.priority,
                sprint_id=sprint_id,
                is_engineering_task=action.is_engineering_task,
            )
            await update_jira_key(action_id, jira_key)
            created_keys.append(jira_key)
            log.info("jira_pusher.issue_created", jira_key=jira_key, task=action.task[:60])
        except Exception as exc:  # noqa: BLE001 - one bad item must not fail the batch
            log.error("jira_pusher.issue_failed", task=action.task[:60], error=str(exc))

    log.info(
        "jira_pusher.batch_done", source_id=source_id,
        total=len(action_items), created=len(created_keys),
    )
    return created_keys


async def _find_duplicate(
    action: ActionItem,
    action_id: str,
    meeting: ExtractedMeeting,
    meeting_id: str,
    *,
    get_open_actions: Any,
    embed: Any,
    link_mentioned_in: Any,
    add_comment: Any,
    threshold: float,
) -> dict[str, Any] | None:
    """Link and comment on an existing item this one duplicates, or None."""
    candidates = await get_open_actions(action.owner, exclude_id=action_id)
    if not candidates:
        return None

    new_embedding = await embed(action.task)
    match = dedup.best_match(action.task, new_embedding, candidates, threshold)
    if not match:
        return None

    await link_mentioned_in(match["id"], meeting_id)
    if match.get("jira_key"):
        try:
            await add_comment(
                match["jira_key"],
                f'Also raised in "{meeting.title}" (dedup similarity {match["score"]:.2f}).',
            )
        except Exception as exc:  # noqa: BLE001 - the link already succeeded
            log.warning("jira_pusher.dedup_comment_failed", key=match["jira_key"], error=str(exc))

    log.info(
        "jira_pusher.deduped", task=action.task[:60],
        matched_key=match.get("jira_key"), score=round(match["score"], 3),
    )
    return match
