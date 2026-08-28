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

log = structlog.get_logger()

ENTITY_SYSTEM = (
    "Extract entities from this question. Respond ONLY with JSON: "
    '{"people": ["name"], "topics": ["keyword"], "date_hint": "string or null"} '
    "Be conservative — only extract clearly named entities."
)

SYNTHESIS_SYSTEM_PREFIX = (
    "You are an intelligent executive assistant with access to the user's meeting memory, decisions, and task graph.\n"
    "Your goal is to answer the user's question directly, cleanly, and with executive polish in markdown.\n\n"
    "Formatting & Guidelines:\n"
    "- Address the user directly using natural second-person language ('you' / 'your'). Never refer to the user in the third person or leak the user's name.\n"
    "- Distinguish accurately between completed/finished work vs open/pending deliverables based strictly on the [STATUS: ...] context.\n"
    "- Favor structured markdown tables whenever presenting multiple deliverables, projects, or sub-tasks, using columns like:\n"
    "  | Deliverable / Sub-task | Owner | Status | Priority | Due Date | Ticket |\n"
    "- For grouped textual sections, add clear spacing, bold section headers, and bulleted sub-task blocks so items never run together.\n"
    "- ALWAYS include direct clickable markdown links using the specific human-readable title of the document, slide deck, or resource as the link text (e.g. [Onshore: Professional Services Profiles](...), [Q3 Resource Plan](...), [Jira MDP-XX](...), [Gmail Thread](...)) rather than generic placeholders or raw URLs whenever links or documents are present in context.\n"
    "- Do NOT create a separate duplicate 'Links Summary' or 'References' section at the bottom; attach links directly inside table cells or inline items.\n"
    "- Base your answer strictly on the context below. If specific details are not in the context, mention it briefly in one sentence.\n\n"
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
        # 1. Action Items (surfacing open deliverables, completed work, and parent/subtask relations)
        actions_res = await session.run(
            """
            MATCH (m:Meeting)-[:FOLLOWS_UP]->(a:ActionItem)
            OPTIONAL MATCH (parent:ActionItem)-[:PARENT_OF]->(a)
            RETURN DISTINCT a.id AS id, a.task AS task, a.owner AS owner,
                   a.due AS due, a.priority AS priority, a.jira_key AS jira_key,
                   coalesce(a.done, false) AS done,
                   parent.task AS parent_task, parent.jira_key AS parent_jira_key,
                   m.title AS meeting_title, m.source_id AS source_id, m.date AS date
            ORDER BY a.done ASC, CASE WHEN a.priority = 'high' THEN 0 ELSE 1 END, a.due ASC
            LIMIT 20
            """
        )
        async for record in actions_res:
            node_ids.append(record["id"])
            status_tag = "[STATUS: COMPLETED / DONE (Finished)]" if record["done"] else "[STATUS: OPEN / IN PROGRESS (Not Finished)]"
            link_parts = []
            if record.get("jira_key"):
                link_parts.append(f"[🔷 Jira {record['jira_key']}](https://michael-baylard.atlassian.net/browse/{record['jira_key']})")
            if record.get("source_id") and str(record["source_id"]).startswith("gmail:"):
                gmail_id = str(record["source_id"]).split(":")[-1]
                link_parts.append(f"[✉️ Gmail Thread](https://mail.google.com/mail/u/0/#inbox/{gmail_id})")

            parent_info = f" | Parent Project: {record['parent_task']} ({record['parent_jira_key']})" if record.get("parent_task") else ""
            links_str = f" | Links: {' '.join(link_parts)}" if link_parts else ""
            lines.append(
                f"ActionItem: {status_tag} | Task: {record['task']} | Owner: {record['owner']} | Due: {record['due'] or 'None'} | Priority: {record['priority']}{parent_info} | Source: {record['meeting_title']}{links_str}"
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
                link_parts = []
                if record.get("source_id") and str(record["source_id"]).startswith("gmail:"):
                    gmail_id = str(record["source_id"]).split(":")[-1]
                    link_parts.append(f"[✉️ Gmail Thread](https://mail.google.com/mail/u/0/#inbox/{gmail_id})")
                links_str = f" | Links: {' '.join(link_parts)}" if link_parts else ""
                lines.append(
                    f"Meeting ({record['date']}): {record['title']}{links_str} — {record['summary']}"
                )

        # 4. Decisions
        decisions_res = await session.run(
            """
            MATCH (m:Meeting)-[:DECIDED]->(d:Decision)
            RETURN DISTINCT d.id AS id, d.text AS text, m.title AS meeting_title, m.date AS date, m.source_id AS source_id
            ORDER BY m.date DESC
            LIMIT 8
            """
        )
        async for record in decisions_res:
            node_ids.append(record["id"])
            link_parts = []
            if record.get("source_id") and str(record["source_id"]).startswith("gmail:"):
                gmail_id = str(record["source_id"]).split(":")[-1]
                link_parts.append(f"[✉️ Gmail Thread](https://mail.google.com/mail/u/0/#inbox/{gmail_id})")
            links_str = f" | Links: {' '.join(link_parts)}" if link_parts else ""
            lines.append(f"Decision: {record['text']} (Meeting: {record['meeting_title']}{links_str})")

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
                MATCH (d:Decision)<-[:DECIDED]-(m:Meeting)
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
                        "question": f"What is the status and requirements for '{short_task}' (due {a['due']})?",
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
                    "question": f"What recent updates, decisions, and action items do we have regarding {name}?",
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
                "question": "What are all of my open deliverables, urgent deadlines, and high-priority commitments?",
            },
            {
                "category": "👥 Stakeholder Tracking",
                "question": "Who is currently waiting on me for deliverables or approvals?",
            },
            {
                "category": "💡 Knowledge Discovery",
                "question": "What key architectural decisions and project milestones were established in recent syncs?",
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
