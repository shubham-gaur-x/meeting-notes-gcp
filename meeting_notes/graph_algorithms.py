"""MAGE algorithms — the ONLY module where `CALL <module>.<procedure>()` appears.

Never add a MAGE CALL anywhere else (CLAUDE.md). Other modules reach these
through `vector_search()` and `get_jaccard_similarity()`.

All eight procedures used here were verified present on `memgraph-mage:3.11.0`
(307 procedures total) — the same image tag `terraform/envs/*.tfvars` pins for
the deployed VM, so local availability transfers.

Two behaviours are carried from v5 with their reasons, because both were found
by running the system rather than by review:

* **Leiden is called with `"modularity"` explicitly.** MAGE's default
  `objective_function="CPM"` at `resolution_parameter=1` over-fragments a graph
  this sparse into all-singleton communities — confirmed live in v5 at
  **308/308 communities of size 1** — silently corrupting every insight query
  (bridges, communities and PageRank all key off `community_id`) until the next
  per-meeting fast run happened to overwrite it.
* **Each CALL is retried once.** Memgraph raises a transient
  `Cannot resolve conflicting transactions` when a per-meeting fast run collides
  with the nightly full run writing the same score properties. Reproduced live
  in v5 against `betweenness_centrality`.
"""

from __future__ import annotations

from typing import Any

import structlog

from meeting_notes.utils import with_retry

log = structlog.get_logger()

_PAGERANK = ("pagerank", "CALL pagerank.get() YIELD node, rank SET node.pagerank_score = rank")
_BETWEENNESS = (
    "betweenness_centrality",
    "CALL betweenness_centrality.get() YIELD node, betweenness_centrality "
    "SET node.betweenness_centrality = betweenness_centrality",
)
_DEGREE = (
    "degree_centrality",
    "CALL degree_centrality.get() YIELD node, degree AS degree_centrality "
    "SET node.degree_centrality = degree_centrality",
)
_WCC = (
    "wcc",
    "CALL weakly_connected_components.get() YIELD node, component_id "
    "SET node.wcc_id = component_id",
)

# Per-meeting path. Louvain rather than Leiden: it is markedly cheaper and this
# runs after every processed record.
FAST_ALGORITHMS: list[tuple[str, str]] = [
    _PAGERANK,
    (
        "community_detection",
        "CALL community_detection.get() YIELD node, community_id "
        "SET node.community_id = community_id",
    ),
    _BETWEENNESS,
    _DEGREE,
    _WCC,
]

# Nightly path. Leiden is more accurate but must be told to optimise
# modularity -- see the module docstring; dropping that argument is a silent,
# data-destroying regression, and there is a test asserting it.
FULL_ALGORITHMS: list[tuple[str, str]] = [
    _PAGERANK,
    (
        "leiden_community_detection",
        'CALL igraphalg.community_leiden("modularity") YIELD node, community_id '
        "SET node.community_id = community_id",
    ),
    _BETWEENNESS,
    _DEGREE,
    _WCC,
]


def _driver() -> Any:
    from meeting_notes.graph_client import get_driver

    return get_driver()


@with_retry(max_attempts=2, base_delay=1.0)
async def _run_one(session: Any, cypher: str) -> None:
    """One algorithm CALL, retried once on Memgraph's transient write conflict."""
    result = await session.run(cypher)
    # Consuming is required: the async driver otherwise defers execution and
    # surfaces a failing statement's error on the NEXT session.run(), which
    # misattributes the failure to the wrong algorithm.
    await result.consume()


async def _run(algorithms: list[tuple[str, str]], driver: Any = None) -> dict[str, str]:
    """Run each algorithm, catching failures individually.

    One bad CALL must never abort the rest — a transient conflict on
    betweenness should not silently skip the four algorithms after it.
    """
    driver = driver or _driver()
    results: dict[str, str] = {}
    async with driver.session() as session:
        for name, cypher in algorithms:
            try:
                await _run_one(session, cypher)
                results[name] = "ok"
            except Exception as exc:  # noqa: BLE001 - reported per algorithm
                log.warning("graph_algorithms.algorithm_failed", algorithm=name, error=str(exc))
                results[name] = f"failed: {exc}"
    return results


async def run_fast(driver: Any = None) -> dict[str, str]:
    """Per-meeting path. Cheap enough to run after every processed record."""
    results = await _run(FAST_ALGORITHMS, driver)
    log.info("graph_algorithms.fast_run_complete", results=results)
    return results


async def run_full(driver: Any = None) -> dict[str, str]:
    """Nightly path. Leiden over the whole graph."""
    results = await _run(FULL_ALGORITHMS, driver)
    log.info("graph_algorithms.full_run_complete", results=results)
    return results


async def get_jaccard_similarity(
    node_id_a: str, node_id_b: str, driver: Any = None
) -> float:
    """Jaccard similarity between two nodes by shared neighbours.

    `node_similarity.jaccard()` streams over the whole graph and takes no node
    arguments, so the pairwise variant is required to score a specific pair.
    """
    driver = driver or _driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a {id: $id_a}), (b {id: $id_b})
            CALL node_similarity.jaccard_pairwise([a], [b])
            YIELD similarity
            RETURN similarity
            """,
            id_a=node_id_a,
            id_b=node_id_b,
        )
        scores = [record["similarity"] async for record in result]
    return max(scores) if scores else 0.0


async def vector_search(
    index_name: str, query_vector: list[float], limit: int = 5, driver: Any = None
) -> list[dict[str, Any]]:
    """Nearest-neighbour search against a MAGE vector index.

    `memory/vector.py` calls this rather than the procedure directly, keeping
    every MAGE CALL in this one module.
    """
    driver = driver or _driver()
    async with driver.session() as session:
        result = await session.run(
            """
            CALL vector_search.search($index_name, $limit, $query_vector)
            YIELD node, similarity, distance
            RETURN node.id AS node_id, similarity, distance
            ORDER BY similarity DESC
            """,
            index_name=index_name,
            limit=limit,
            query_vector=query_vector,
        )
        return [dict(r) async for r in result]
