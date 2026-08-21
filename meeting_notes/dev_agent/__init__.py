"""The autonomous dev agent — Phase 11, ADR-020.

Picks up labelled Jira sprint tickets, implements them with headless Claude
Code in an isolated git worktree, runs seven deterministic guardrail gates
plus an independent LLM review, and opens a PR. **Never merges its own PR** —
`CLOSED` is written only by `/webhook/github`'s `pull_request.merged` handler,
i.e. an actual human merge.

Ported from v5, which never completed an autonomous run (blocked on
free-tier LLM quotas — see ADR-020) and carried a confirmed-live bug: a
`SHIPPED` run was treated as resumable forever, producing 61 `AgentRun`
nodes for one ticket. `lifecycle.py` fixes it.

Module ownership, each deliberate:

    lifecycle.py       state machine + deterministic ids. SHIPPED is terminal.
    guardrails.py       7 deterministic gates + independent LLM reviewer
    self_verify.py      cheap diff-vs-ticket scoring, never blocks review
    session_memory.py   resumable record per ticket, survives across attempts
    backend.py           coding-model routing — NOT meeting_notes.llm_client;
                         this spawns a subprocess with tool access, not a
                         chat_json/embed call
    claude_runner.py    spawns headless `claude`
    git_ops.py          one worktree per ticket
    github_client.py    read-only: find the PR the agent opened, fetch its diff
    orchestrator.py     triage -> process_ticket -> poll_and_process

All Postgres access goes through `meeting_notes.db` — this package owns no
SQL of its own (CLAUDE.md: one SQL-owning module).
"""
