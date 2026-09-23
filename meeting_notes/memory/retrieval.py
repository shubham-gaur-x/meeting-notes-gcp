"""Memory retrieval — natural-language questions answered from the graph.

**Query-time only.** `pipeline.py` must never import this (CLAUDE.md): the
pipeline writes memory, retrieval reads it, and mixing the two would put an
LLM synthesis call on the ingestion path.

Reads only. The one side effect is logging a `MemorySession`, which is
delegated to `episodic.log_session` because that module owns the node type.

Two governance rules are enforced here rather than assumed:

* **`Person.tracked` gates per-person analytics.** Aggregates are the default;
  naming individuals is opt-in (CLAUDE.md).
* **`FACT_MIN_CONFIDENCE` applies at read time.** Facts seed at 0.3 and gain
  0.1 per corroboration, so an unfiltered read surfaces one-off noise at the
  same weight as a fact repeated across many meetings. This is a
  retrieval-quality floor, not a side-effect gate — unlike an ActionItem,
  a Fact has no ticket to block.
"""

from __future__ import annotations

from typing import Any

import structlog

from meeting_notes.config import Settings, get_settings
from meeting_notes.memory import episodic
from meeting_notes.utils import gmail_thread_url

log = structlog.get_logger()

ENTITY_SYSTEM = (
    "Extract entities from this question. Respond ONLY with JSON: "
    '{"people": ["name"], "topics": ["keyword"], "date_hint": "string or null"} '
    "Be conservative — only extract clearly named entities."
)

SYNTHESIS_SYSTEM_PREFIX = (
    "You are an intelligent executive assistant with access to the user's "
    "meeting memory, decisions, and task graph.\n"
    "Your goal is to answer the user's question directly, cleanly, and with "
    "executive polish in markdown.\n\n"
    "Formatting & Guidelines:\n"
    "- Address the user directly using natural second-person language ('you' / "
    "'your'). Never refer to the user in the third person or leak the user's name.\n"
    "- Structure deliverables and tasks as distinct, easily scannable sections/cards "
    "— with a bold item title, followed by structured metadata: **Owner**, **Due Date**, "
    "**Priority**, and **Details**, plus inline Jira and Source links. Do not crowd deliverables "
    "into flat, indistinct bullet lists.\n"
    "- Cite source meetings and Gmail links: For every deliverable, decision, or update, "
    "always include its relevant source meeting title and link (e.g. `[Meeting Title](url)`) "
    "and Jira ticket (e.g. `[Jira KEY-123](url)`) exactly as provided in the context.\n"
    # Links are reproduced, never composed. The earlier wording told the model
    # to ALWAYS include a link and showed it the URL shapes, which is a recipe
    # for a confidently invented Jira key -- and a fabricated link is worse
    # than no link, because it looks checkable.
    "- Reproduce markdown links EXACTLY as they appear in the context, attached to "
    "the item they belong to. Never construct, guess, or complete a URL that is not "
    "written in the context verbatim. If an item has no link, say nothing about "
    "links for it.\n"
    "- Do NOT create a separate duplicate 'Links Summary' or 'References' section "
    "at the bottom; attach links directly to each item.\n"
    "- Answer using ONLY the context below. Cite names and dates when they are "
    "present. If the context does not contain enough information to answer, say so "
    "plainly -- do not guess.\n\n"
    'Respond ONLY with JSON of exactly this shape: {"answer": "your markdown answer here"}.\n'
    "The answer value must be formatted markdown text, not nested objects or lists.\n\n"
    "Context:\n"
)

NO_CONTEXT_ANSWER = (
    "I don't have anything in memory that answers that. "
    "Nothing in the graph matched the question."
)


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


async def _chat(system: str, user: str, settings: Settings | None, chat: Any) -> Any:
    if chat is None:
        from meeting_notes import llm_client

        chat = llm_client.chat_json
    return await chat(system, user, temperature=0.0, settings=settings)


async def extract_entities(
    question: str, *, settings: Settings | None = None, chat: Any = None
) -> dict[str, Any]:
    """Pull people/topics/date hints out of a question."""
    try:
        parsed = await _chat(ENTITY_SYSTEM, question, settings, chat)
    except Exception as exc:  # noqa: BLE001 - a failed parse degrades to no entities
        log.warning("retrieval.entity_extraction_failed", error=str(exc))
        return {"people": [], "topics": [], "date_hint": None}

    if not isinstance(parsed, dict):
        return {"people": [], "topics": [], "date_hint": None}
    return {
        "people": parsed.get("people") or [],
        "topics": parsed.get("topics") or [],
        "date_hint": parsed.get("date_hint"),
    }


def _jira_link(jira_key: str | None, settings: Settings) -> str | None:
    """Markdown link to a Jira issue, or None when we cannot build a real one.

    The domain comes from settings, never a literal. A hardcoded tenant is the
    thing that stops this repo moving to the Onix project (CLAUDE.md), and it
    would also quietly point one person's dashboard at another's Jira.
    """
    domain = settings.jira_domain.strip()
    if not jira_key or not domain:
        return None
    return f"[Jira {jira_key}](https://{domain}/browse/{jira_key})"


def _gmail_link(source_id: Any) -> str | None:
    """Markdown link to the originating Gmail thread, or None."""
    url = gmail_thread_url(source_id)
    return f"[Gmail Thread]({url})" if url else None


def _links_suffix(*links: str | None) -> str:
    """` | Links: ...` for whichever links exist, or '' when none do."""
    present = [link for link in links if link]
    return f" | Links: {' '.join(present)}" if present else ""


async def assemble_context(
    entities: dict[str, Any],
    question: str,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    search_meetings: Any = None,
) -> tuple[list[str], list[str]]:
    """Gather graph context for a question. Returns (context_lines, node_ids)."""
    settings = settings or get_settings()
    driver = driver or _driver()
    lines: list[str] = []
    node_ids: list[str] = []

    people = [p for p in entities.get("people", []) if isinstance(p, str)]
    topics = [t.lower().strip() for t in entities.get("topics", []) if isinstance(t, str)]

    async with driver.session() as session:
        # 1. Action Items (always queried to surface open commitments & deliverables)
        actions_res = await session.run(
            """
            MATCH (m:Meeting)-[:FOLLOWS_UP]->(a:ActionItem)
            WHERE coalesce(a.done, false) = false
            RETURN DISTINCT a.id AS id, a.task AS task, a.owner AS owner,
                   a.due AS due, a.priority AS priority, a.jira_key AS jira_key,
                   m.title AS meeting_title, m.source_id AS source_id, m.date AS date
            ORDER BY CASE WHEN a.priority = 'high' THEN 0 ELSE 1 END, a.due ASC
            LIMIT 15
            """
        )
        async for record in actions_res:
            node_ids.append(record["id"])
            links = _links_suffix(
                _jira_link(record.get("jira_key"), settings),
                _gmail_link(record.get("source_id")),
            )
            lines.append(
                f"ActionItem: Task: {record['task']} | Owner: {record['owner']}"
                f" | Due: {record['due'] or 'None'} | Priority: {record['priority']}"
                f" | Source: {record['meeting_title']}{links}"
            )

        # 2. People
        if people:
            result = await session.run(
                """
                UNWIND $names AS name
                MATCH (p:Person)
                WHERE toLower(p.name) CONTAINS toLower(name)
                   OR toLower(p.email) CONTAINS toLower(name)
                RETURN DISTINCT p.id AS id, p.name AS name, p.email AS email
                LIMIT 10
                """,
                names=people,
            )
            async for record in result:
                node_ids.append(record["id"])
                lines.append(f"Person: {record['name']} <{record['email']}>")

        # 3. Topics & Meetings
        if topics:
            result = await session.run(
                """
                UNWIND $topics AS topic
                MATCH (t:Topic)<-[:DISCUSSED]-(m:Meeting)
                WHERE t.name CONTAINS topic
                RETURN DISTINCT m.id AS id, m.title AS title, m.date AS date,
                                m.summary AS summary, m.source_id AS source_id
                ORDER BY m.date DESC
                LIMIT 10
                """,
                topics=topics,
            )
            async for record in result:
                node_ids.append(record["id"])
                links = _links_suffix(_gmail_link(record.get("source_id")))
                lines.append(
                    f"Meeting ({record['date']}): {record['title']}{links} — {record['summary']}"
                )

        # 4. Decisions. PRODUCED, not DECIDED: `_write_decisions` and every
        # other reader in graph_client use PRODUCED, so DECIDED matched nothing
        # and this block returned zero rows against a real graph -- silently,
        # because an empty result is indistinguishable from "no decisions yet".
        decisions_res = await session.run(
            """
            MATCH (m:Meeting)-[:PRODUCED]->(d:Decision)
            RETURN DISTINCT d.id AS id, d.text AS text, m.title AS meeting_title,
                   m.date AS date, m.source_id AS source_id
            ORDER BY m.date DESC
            LIMIT 8
            """
        )
        async for record in decisions_res:
            node_ids.append(record["id"])
            links = _links_suffix(_gmail_link(record.get("source_id")))
            lines.append(
                f"Decision: {record['text']} (Meeting: {record['meeting_title']}{links})"
            )

        # 5. Facts
        result = await session.run(
            """
            MATCH (f:Fact)
            WHERE f.confidence >= $min_confidence
            RETURN f.id AS id, f.text AS text, f.confidence AS confidence
            ORDER BY f.confidence DESC
            LIMIT 10
            """,
            min_confidence=settings.fact_min_confidence,
        )
        async for record in result:
            node_ids.append(record["id"])
            lines.append(f"Fact (confidence {record['confidence']}): {record['text']}")

    # Semantic search as a fallback: a question sharing no keywords with any
    # meeting still finds the right one by meaning. This is the mechanism
    # behind the "zero keyword overlap" exit criterion.
    if not lines and search_meetings is not None:
        for hit in await search_meetings(question, limit=5, driver=driver, settings=settings):
            node_ids.append(hit["id"])
            lines.append(f"Meeting ({hit.get('date')}): {hit.get('title')} — {hit.get('summary')}")

    return lines, node_ids


async def full_memory_query(
    question: str,
    *,
    driver: Any = None,
    settings: Settings | None = None,
    chat: Any = None,
    search_meetings: Any = None,
    log_session: bool = True,
) -> dict[str, Any]:
    """Answer a natural-language question from the graph.

    Returns the answer plus the node ids that contributed, so the caller can
    show its working rather than presenting an unsourced assertion.
    """
    settings = settings or get_settings()
    driver = driver or _driver()

    entities = await extract_entities(question, settings=settings, chat=chat)
    lines, node_ids = await assemble_context(
        entities, question, driver=driver, settings=settings, search_meetings=search_meetings
    )

    if not lines:
        # Honest emptiness beats a confident guess: the whole point of a
        # memory system is that its answers are grounded.
        return {"question": question, "answer": NO_CONTEXT_ANSWER, "node_ids": [], "entities": entities}

    context = "\n".join(lines)
    try:
        parsed = await _chat(f"{SYNTHESIS_SYSTEM_PREFIX}{context}", question, settings, chat)
        answer = (
            parsed.get("answer")
            if isinstance(parsed, dict) and parsed.get("answer")
            else str(parsed)
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("retrieval.synthesis_failed", error=str(exc))
        answer = NO_CONTEXT_ANSWER

    if log_session:
        try:
            await episodic.log_session(question, str(answer), node_ids, driver=driver)
        except Exception as exc:  # noqa: BLE001 - logging must not fail the answer
            log.warning("retrieval.session_log_failed", error=str(exc))

    # Generate progressive follow-up question chips based on retrieved entities and context
    followups: list[str] = []
    if entities.get("topics"):
        for top in entities["topics"][:2]:
            followups.append(f"What key decisions and deliverables relate to {top}?")
    if entities.get("people"):
        for person in entities["people"][:1]:
            followups.append(f"What action items or commitments involve {person}?")
    if not followups:
        followups = [
            "What related decisions were established on this topic?",
            "Who are the main collaborators and owners involved?",
            "What upcoming deadlines are associated with this work?",
        ]

    return {
        "question": question,
        "answer": answer,
        "suggested_followups": followups[:3],
        "node_ids": node_ids,
        "entities": entities,
    }


async def generate_suggested_questions(
    *, driver: Any = None, settings: Settings | None = None
) -> list[dict[str, str]]:
    """Generate dynamic, context-rich questions based on the user's active graph data.

    Favors active project deliverables, upcoming deadlines, stakeholder requests,
    and progressive information gathering over time.
    """
    settings = settings or get_settings()
    driver = driver or _driver()

    questions: list[dict[str, str]] = []

    try:
        async with driver.session() as session:
            # 1. Open / High-Priority Action Items
            actions_res = await session.run(
                """
                MATCH (a:ActionItem)
                WHERE coalesce(a.done, false) = false
                RETURN a.task AS task, a.owner AS owner, a.due AS due, a.priority AS priority
                ORDER BY CASE WHEN a.priority = 'high' THEN 0 ELSE 1 END, a.due ASC
                LIMIT 5
                """
            )
            actions = [dict(r) async for r in actions_res]

            # 2. Key Topics / Workstreams
            topics_res = await session.run(
                """
                MATCH (t:Topic)
                OPTIONAL MATCH (t)<-[r]-()
                RETURN t.name AS name, count(r) AS degree
                ORDER BY degree DESC
                LIMIT 5
                """
            )
            topics = [dict(r) async for r in topics_res]

            # 3. Recent Decisions
            decisions_res = await session.run(
                """
                MATCH (d:Decision)<-[:PRODUCED]-(m:Meeting)
                RETURN d.text AS text, m.title AS meeting_title, m.date AS date
                ORDER BY m.date DESC
                LIMIT 3
                """
            )
            decisions = [dict(r) async for r in decisions_res]

            # 4. Open Blockers
            blockers_res = await session.run(
                """
                MATCH (b:Blocker)<-[:RAISES_BLOCKER]-(m:Meeting)
                RETURN b.text AS text, m.title AS meeting_title
                LIMIT 3
                """
            )
            blockers = [dict(r) async for r in blockers_res]

        for a in actions[:2]:
            task = a.get("task") or ""
            if task:
                short_task = task[:70] + "..." if len(task) > 70 else task
                if a.get("due"):
                    questions.append({
                        "category": "⏰ Upcoming Deadline",
                        "question": f"What is the status and requirements for "
                                    f"'{short_task}' (due {a['due']})?",
                    })
                else:
                    questions.append({
                        "category": "🎯 Project Action",
                        "question": f"What are the details and next steps for '{short_task}'?",
                    })

        for t in topics[:2]:
            name = t.get("name")
            if name:
                questions.append({
                    "category": "📂 Project Workstream",
                    "question": f"What recent updates, decisions, and action items "
                                f"do we have regarding {name}?",
                })

        for d in decisions[:1]:
            text = d.get("text")
            title = d.get("meeting_title")
            if text and title:
                questions.append({
                    "category": "📋 Decision Context",
                    "question": f"What led to the decision '{text[:60]}...' in {title}?",
                })

        for b in blockers[:1]:
            text = b.get("text")
            if text:
                questions.append({
                    "category": "⚠️ Risk & Blockers",
                    "question": f"What is currently blocking '{text[:60]}...' and how can we resolve it?",
                })
    except Exception as exc:  # noqa: BLE001
        log.warning("retrieval.suggested_questions_failed", error=str(exc))

    if len(questions) < 4:
        questions.extend([
            {
                "category": "🚀 Executive Overview",
                "question": "What are all of my open deliverables, urgent "
                            "deadlines, and high-priority commitments?",
            },
            {
                "category": "👥 Stakeholder Tracking",
                "question": "Who is currently waiting on me for deliverables or approvals?",
            },
            {
                "category": "💡 Knowledge Discovery",
                "question": "What key architectural decisions and project "
                            "milestones were established in recent syncs?",
            },
        ])

    return questions[:6]


async def person_memory_profile(
    email: str, *, driver: Any = None, settings: Settings | None = None
) -> dict[str, Any]:
    """Everything the graph remembers about one person. No LLM call.

    Returns {} when the person is not found, and **{} when they are not
    tracked** — per-person analytics are opt-in (CLAUDE.md).
    """
    settings = settings or get_settings()
    driver = driver or _driver()

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Person {email: $email})
            RETURN p.id AS id, p.name AS name, p.email AS email,
                   coalesce(p.tracked, false) AS tracked,
                   p.pagerank_score AS pagerank_score,
                   p.community_id AS community_id,
                   p.betweenness_centrality AS betweenness_centrality,
                   p.degree_centrality AS degree_centrality
            """,
            email=email,
        )
        records = [dict(r) async for r in result]
        if not records:
            return {}

        profile = records[0]
        if not profile.get("tracked"):
            log.info("retrieval.profile_withheld_untracked", email=email)
            return {}

        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[:ATTENDED]->(m:Meeting)-[:HAS_FACT]->(f:Fact)
            WHERE f.confidence >= $min_confidence
            RETURN DISTINCT f.id AS id, f.text AS text,
                            f.confidence AS confidence, f.source_count AS source_count
            ORDER BY f.confidence DESC
            LIMIT 10
            """,
            email=email,
            min_confidence=settings.fact_min_confidence,
        )
        profile["facts"] = [dict(r) async for r in result]

        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[:PREFERS]->(pref:Preference)
            RETURN pref.id AS id, pref.category AS category, pref.value AS value
            """,
            email=email,
        )
        profile["preferences"] = [dict(r) async for r in result]

        # KNOWS is stored in one canonical direction (lexicographically ordered
        # emails), so this must match either direction or half the edges vanish.
        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[k:KNOWS]-(other:Person)
            RETURN other.name AS name, other.email AS email, k.weight AS weight
            ORDER BY k.weight DESC
            LIMIT 10
            """,
            email=email,
        )
        profile["knows"] = [dict(r) async for r in result]

        result = await session.run(
            """
            MATCH (p:Person {email: $email})-[i:INTERESTED_IN]->(t:Topic)
            RETURN t.name AS name, i.weight AS weight
            ORDER BY i.weight DESC
            LIMIT 10
            """,
            email=email,
        )
        profile["interests"] = [dict(r) async for r in result]

    return profile
