"""The four memory layers, plus retrieval.

Each module owns a slice of the graph schema and may issue Cypher **only** for
the node and edge types it owns — the one documented exception to the "all
Cypher in graph_client.py" rule (CLAUDE.md):

    semantic    Fact, Preference, HAS_FACT, PREFERS, KNOWS, INTERESTED_IN
    episodic    MemorySession, PRECEDED_BY, CAUSED_BY, ACCESSED
    procedural  Procedure, ProcedureStep, FOLLOWS_PROCEDURE, HAS_STEP, NEXT_STEP
    vector      the `embedding` property on Meeting / Fact / ActionItem
    retrieval   reads only, never writes

No module here issues a MAGE CALL; those live in graph_algorithms.py.
"""
