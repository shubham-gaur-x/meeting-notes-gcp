"""Confidence gate, dedup gate, then push to Linear.

Mirrors jira_pusher with Linear-specific GraphQL mutations, rich Markdown descriptions,
parent/sub-issue hierarchies, and Memgraph write-back.
"""

from __future__ import annotations

from typing import Any

import structlog

from meeting_notes import dedup
from meeting_notes.config import Settings, get_settings
from meeting_notes.models import ActionItem, ExtractedMeeting
from meeting_notes.utils import gmail_thread_url, uuid5_id

log = structlog.get_logger()


async def _default_mark_needs_review(action_id: str, reason: str) -> None:
    from meeting_notes.graph_client import mark_action_needs_review

    await mark_action_needs_review(action_id, reason)


async def _default_get_open_actions(
    owner_email: str | None = None,
    *,
    exclude_id: str,
    meeting_id: str | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    from meeting_notes.graph_client import get_open_actions_for_owner

    return await get_open_actions_for_owner(owner_email, exclude_id=exclude_id, meeting_id=meeting_id)


async def _default_update_linear_info(
    action_id: str, linear_id: str, linear_identifier: str, linear_url: str, linear_state: str
) -> None:
    from meeting_notes.graph_client import update_action_linear_info

    await update_action_linear_info(action_id, linear_id, linear_identifier, linear_url, linear_state)


async def _default_link_mentioned_in(action_id: str, meeting_id: str) -> None:
    from meeting_notes.graph_client import link_action_mentioned_in

    await link_action_mentioned_in(action_id, meeting_id)


async def _default_create_issue(**kwargs: Any) -> dict[str, Any]:
    from meeting_notes.linear_client import create_issue

    result: dict[str, Any] = await create_issue(**kwargs)
    return result


async def _default_embed(text: str) -> list[float] | None:
    from meeting_notes import llm_client

    return await llm_client.embed(text)


async def _default_add_comment(issue_id: str, body: str) -> dict[str, Any]:
    from meeting_notes.linear_client import add_comment

    result: dict[str, Any] = await add_comment(issue_id, body)
    return result


async def push_action_items_to_linear(
    action_items: list[ActionItem],
    meeting: ExtractedMeeting,
    source_id: str,
    *,
    settings: Settings | None = None,
    mark_needs_review: Any = None,
    get_open_actions: Any = None,
    update_linear_info: Any = None,
    link_mentioned_in: Any = None,
    create_issue: Any = None,
    embed: Any = None,
    add_comment: Any = None,
) -> list[str]:
    """Gate, dedup, then create Linear issues.

    Returns the identifiers (e.g. ENG-101) of newly created issues.
    """
    settings = settings or get_settings()

    if not action_items or not settings.linear_api_key or not settings.linear_team_id:
        if not settings.linear_api_key:
            log.warning(
                "linear_pusher.no_api_key",
                hint="Set LINEAR_API_KEY and LINEAR_TEAM_ID to enable Linear push",
            )
        return []

    mark_needs_review = mark_needs_review or _default_mark_needs_review
    get_open_actions = get_open_actions or _default_get_open_actions
    update_linear_info = update_linear_info or _default_update_linear_info
    link_mentioned_in = link_mentioned_in or _default_link_mentioned_in
    create_issue = create_issue or _default_create_issue
    embed = embed or _default_embed
    add_comment = add_comment or _default_add_comment

    meeting_id = uuid5_id("meeting", source_id)
    created_identifiers: list[str] = []

    for i, action in enumerate(action_items):
        action_id = uuid5_id("action", f"{source_id}:{i}:{action.task}")

        if await _is_gated(
            action,
            action_id,
            meeting,
            meeting_id,
            settings,
            mark_needs_review=mark_needs_review,
            get_open_actions=get_open_actions,
            embed=embed,
            link_mentioned_in=link_mentioned_in,
            add_comment=add_comment,
            update_linear_info=update_linear_info,
        ):
            continue

        created_issue = await _create_linear_issue(
            action,
            action_id,
            meeting,
            source_id,
            settings=settings,
            create_issue=create_issue,
            update_linear_info=update_linear_info,
        )
        if created_issue and created_issue.get("identifier"):
            created_identifiers.append(created_issue["identifier"])

    log.info(
        "linear_pusher.batch_done",
        source_id=source_id,
        total=len(action_items),
        created=len(created_identifiers),
    )
    return created_identifiers


async def _is_gated(
    action: ActionItem,
    action_id: str,
    meeting: ExtractedMeeting,
    meeting_id: str,
    settings: Settings,
    *,
    mark_needs_review: Any,
    get_open_actions: Any,
    embed: Any,
    link_mentioned_in: Any,
    add_comment: Any,
    update_linear_info: Any,
) -> bool:
    """Check confidence threshold and semantic deduplication."""
    if action.confidence < settings.linear_confidence_threshold:
        await mark_needs_review(action_id, f"confidence {action.confidence:.2f} below threshold")
        log.info(
            "linear_pusher.needs_review",
            task=action.task[:60],
            confidence=round(action.confidence, 2),
        )
        return True

    if settings.linear_dedup_enabled:
        duplicate = await _find_duplicate(
            action,
            action_id,
            meeting,
            meeting_id,
            get_open_actions=get_open_actions,
            embed=embed,
            link_mentioned_in=link_mentioned_in,
            add_comment=add_comment,
            threshold=settings.linear_dedup_threshold,
            update_linear_info=update_linear_info,
        )
        if duplicate is not None:
            return True

    return False


async def _create_linear_issue(
    action: ActionItem,
    action_id: str,
    meeting: ExtractedMeeting,
    source_id: str,
    *,
    settings: Settings,
    create_issue: Any,
    update_linear_info: Any,
) -> dict[str, Any] | None:
    """Create a Linear issue with rich markdown description and record its info on the ActionItem."""
    source_url = gmail_thread_url(source_id)
    desc_lines = [
        f"**From meeting:** {meeting.title} ({meeting.date})",
    ]
    if source_url:
        desc_lines.append(f"**Source Email Thread:** [{source_url}]({source_url})")

    if meeting.links:
        desc_lines.append("**Referenced Documents:**")
        for link in meeting.links[:5]:
            desc_lines.append(f"- [{link}]({link})")

    desc_lines.append(f"**Owner:** {action.owner}")
    desc_lines.append(f"**Due Date:** {action.due or 'Not specified'}")
    desc_lines.append(f"**Priority:** {action.priority}")

    if meeting.attendees:
        attendee_names = [a.name if hasattr(a, "name") else str(a) for a in meeting.attendees[:8]]
        desc_lines.append(f"**Attendees:** {', '.join(attendee_names)}")

    description = "\n\n".join(desc_lines)

    try:
        issue = await create_issue(
            title=action.task[:255],
            description=description,
            priority=action.priority,
            due_date=action.due,
            settings=settings,
        )
        linear_id = issue.get("id", "")
        linear_identifier = issue.get("identifier", "")
        linear_url = issue.get("url", "")
        linear_state = (issue.get("state") or {}).get("name", "Todo")

        await update_linear_info(action_id, linear_id, linear_identifier, linear_url, linear_state)
        log.info(
            "linear_pusher.issue_created",
            identifier=linear_identifier,
            task=action.task[:60],
        )
        result: dict[str, Any] = issue
        return result
    except Exception as exc:  # noqa: BLE001 - one failed item must not fail batch
        log.error("linear_pusher.issue_failed", task=action.task[:60], error=str(exc))
        return None


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
    update_linear_info: Any,
) -> dict[str, Any] | None:
    """Identify existing open action items with matching embedding similarity."""
    candidates = await get_open_actions(
        action.owner,
        exclude_id=action_id,
        meeting_id=meeting_id,
    )
    if not candidates:
        return None

    new_embedding = await embed(action.task)
    match = dedup.best_match(action.task, new_embedding, candidates, threshold)
    if not match:
        return None

    linear_id = match.get("linear_id")
    linear_identifier = match.get("linear_identifier")
    log.info(
        "linear_pusher.duplicate_found",
        new_task=action.task[:60],
        matched_id=match.get("id"),
        score=round(match["score"], 3),
    )

    await link_mentioned_in(match["id"], meeting_id)
    if linear_id:
        base_comment = (
            f"Referenced again in meeting **{meeting.title}** ({meeting.date}) "
            f"(dedup similarity {match['score']:.2f})."
        )
        source_url = gmail_thread_url(meeting_id) or ""
        comment_text = f"{base_comment}\nSource: {source_url}" if source_url else base_comment
        try:
            await add_comment(linear_id, comment_text)
        except Exception as exc:  # noqa: BLE001
            log.warning("linear_pusher.comment_failed", linear_id=linear_id, error=str(exc))

    if linear_id and linear_identifier:
        await update_linear_info(
            action_id,
            linear_id,
            linear_identifier,
            match.get("linear_url", ""),
            match.get("linear_state", "Todo"),
        )
    return match

