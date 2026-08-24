"""Graph algorithm insights — influence, communities, bridges."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from api.deps import principal
from meeting_notes import graph_client
from meeting_notes.access_control import Principal

router = APIRouter(prefix="/graph/insights", tags=["insights"])


@router.get("/influential")
async def influential(
    label: str = Query("Person"),
    limit: int = Query(10, ge=1, le=100),
    _: Principal = Depends(principal),
) -> dict[str, Any]:
    """Top nodes by PageRank.

    **Governance:** for `Person`, only `tracked = true` people appear. The gate
    lives in `graph_client.get_influential_nodes` so every caller inherits it
    rather than each endpoint remembering to filter.
    """
    nodes = await graph_client.get_influential_nodes(label=label, limit=limit)
    return {"label": label, "nodes": nodes, "count": len(nodes)}


@router.get("/communities")
async def communities(_: Principal = Depends(principal)) -> dict[str, Any]:
    """Clusters the graph found on its own, each named by the topics inside it."""
    found = await graph_client.get_all_communities()
    return {"communities": found, "count": len(found)}


@router.get("/communities/{community_id}")
async def community_members(
    community_id: int, _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Everything inside one cluster. Untracked people are excluded — naming
    an individual is opt-in (CLAUDE.md)."""
    members = await graph_client.get_community_members(community_id)
    return {"community_id": community_id, "members": members, "count": len(members)}


@router.get("/bridges")
async def bridges(
    limit: int = Query(10, ge=1, le=100), _: Principal = Depends(principal)
) -> dict[str, Any]:
    """Nodes joining otherwise separate clusters, by betweenness centrality.

    Untracked people are excluded: centrality is named directly in CLAUDE.md's
    per-person rule."""
    nodes = await graph_client.get_bridge_nodes(limit=limit)
    return {"nodes": nodes, "count": len(nodes)}


@router.get("/node/{node_id}")
async def node_insights(node_id: str, _: Principal = Depends(principal)) -> dict[str, Any]:
    """One node's centrality, community and immediate neighbours."""
    return await graph_client.get_node_insights(node_id)
