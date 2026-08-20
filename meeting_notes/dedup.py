"""P5 dedup decision: is a new action item a duplicate of an existing open one?

Pure similarity logic (no I/O) so it is deterministic and unit-testable. Prefers embedding
cosine similarity when both sides have an embedding, falls back to text ratio otherwise.
The caller (jira_pusher) supplies same-owner open candidates from the graph; above threshold
it links a MENTIONED_IN edge and comments instead of opening a duplicate Jira issue.
"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    # strict=True is safe: the length guard above already rejects mismatches,
    # and it documents that this zip must never silently truncate.
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def similarity(
    new_text: str, new_embedding: list[float] | None, candidate: dict[str, Any]
) -> float:
    cand_emb = candidate.get("embedding")
    if new_embedding and cand_emb:
        return cosine(new_embedding, cand_emb)
    return SequenceMatcher(None, _norm(new_text), _norm(candidate.get("task", ""))).ratio()


def best_match(
    new_text: str,
    new_embedding: list[float] | None,
    candidates: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any] | None:
    """Return the best candidate above ``threshold`` (with its ``score``), or None."""
    best: dict[str, Any] | None = None
    best_score = 0.0
    for c in candidates:
        s = similarity(new_text, new_embedding, c)
        if s > best_score:
            best, best_score = c, s
    if best is not None and best_score >= threshold:
        return {**best, "score": best_score}
    return None
