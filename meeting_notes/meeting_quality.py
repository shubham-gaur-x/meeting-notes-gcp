"""Phase 31 — meeting quality scoring.

The graph doesn't just remember meetings, it judges them. Per-meeting component scores
in [0,1] are combined into a weighted ``quality_score`` and written back onto the Meeting
node (via ``memgraph_client`` — no Cypher lives here). Follows the memory-module pattern:
pure scoring logic here, all graph I/O delegated to ``graph_client``.

PORT NOTE: v5's ``score_all_meetings()`` is deliberately NOT ported here.
It is the one function in this module that does I/O -- it orchestrates
``memgraph_client`` -- and graph_client does not exist until Phase 3.
Everything below is pure and testable with no database.

DATA-READINESS (Phase 31 Task 0): components with no underlying data return ``None`` and
are EXCLUDED from the composite (weights renormalized over available components). We never
average over empty signals and call it quality. On the current graph most yield-based
components are null (few durations, 0 decisions, 3 action items); ``score_all_meetings``
reports how many meetings had enough signal so the sparsity is visible, not hidden.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

# Weights for the composite. Documented in one place; renormalized over available
# (non-None) components so a missing signal never silently drags the score toward zero.
WEIGHTS: dict[str, float] = {
    "attendance_ratio": 0.15,
    "decision_yield": 0.20,
    "action_yield": 0.20,
    "action_completion": 0.25,
    "agenda_present": 0.10,
    "recurrence_health": 0.10,
}

_AGENDA_MARKERS = re.compile(
    r"agenda|topics?\s*:|^\s*[-*\d]+[.)]\s+|action items?|objectives?|discuss(ion)?\s*:",
    re.IGNORECASE | re.MULTILINE,
)


def percentile_rank(value: float, population: Sequence[float]) -> float:
    """Fraction of the population <= value, in [0,1]. Neutral 0.5 if population too small."""
    pop = [p for p in population if p is not None]
    if len(pop) < 2:
        return 0.5
    at_or_below = sum(1 for p in pop if p <= value)
    return round(at_or_below / len(pop), 4)


def score_attendance_ratio(attended: int | None, invited: int | None) -> float | None:
    if not invited or invited <= 0 or attended is None:
        return None
    return round(max(0.0, min(1.0, attended / invited)), 4)


def _per_hour(count: int, duration_minutes: float | None) -> float | None:
    if not duration_minutes or duration_minutes <= 0:
        return None
    return count / (duration_minutes / 60.0)


def score_yield(
    count: int, duration_minutes: float | None, population_rates: Sequence[float]
) -> float | None:
    """Percentile-normalized per-hour production rate. None if the meeting has no duration."""
    rate = _per_hour(count, duration_minutes)
    if rate is None:
        return None
    return percentile_rank(rate, population_rates)


def score_action_completion(done: int | None, total: int | None) -> float | None:
    if not total or total <= 0:
        return None
    return round(max(0.0, min(1.0, (done or 0) / total)), 4)


def score_agenda_present(text: str | None) -> float | None:
    """Rules-based (classifier.py style, no LLM). None if there is no text to judge."""
    if not text or not text.strip():
        return None
    return 1.0 if _AGENDA_MARKERS.search(text) else 0.0


def score_recurrence_health(recent_scores: Sequence[float | None]) -> float | None:
    """Trend over the last few occurrences of a recurring series.

    None for a non-series (<2 occurrences). A declining series scores below its mean; a
    stable/improving one scores at/above it. Result clamped to [0,1].
    """
    vals = [s for s in recent_scores if s is not None]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    # Simple slope: last minus first, scaled. Decay (negative slope) pulls the score down.
    slope = (vals[-1] - vals[0]) / (len(vals) - 1)
    return round(max(0.0, min(1.0, mean + slope)), 4)


def composite_quality(
    components: dict[str, float | None], weights: dict[str, float] | None = None
) -> float | None:
    """Weighted mean over AVAILABLE (non-None) components, weights renormalized.

    Returns None when no component has data (honest 'insufficient data', not 0.0).
    """
    weights = weights or WEIGHTS
    avail = {k: v for k, v in components.items() if v is not None and k in weights}
    total_w = sum(weights[k] for k in avail)
    if not avail or total_w == 0:
        return None
    return round(sum(weights[k] * v for k, v in avail.items()) / total_w, 4)


def compute_quality(
    features: dict[str, Any], population_rates: Mapping[str, Sequence[float]]
) -> dict[str, Any]:
    """Pure: turn one meeting's raw features into components + composite.

    ``features`` keys: attended, invited, n_decisions, n_actions, n_actions_done,
    duration_minutes, agenda_text, recurrence_scores. ``population_rates`` provides the
    ``decision`` and ``action`` per-hour distributions for percentile normalization.
    """
    components: dict[str, float | None] = {
        "attendance_ratio": score_attendance_ratio(
            features.get("attended"), features.get("invited")  # type: ignore[arg-type]
        ),
        "decision_yield": score_yield(
            int(features.get("n_decisions", 0) or 0),
            features.get("duration_minutes"),  # type: ignore[arg-type]
            population_rates.get("decision", []),
        ),
        "action_yield": score_yield(
            int(features.get("n_actions", 0) or 0),
            features.get("duration_minutes"),  # type: ignore[arg-type]
            population_rates.get("action", []),
        ),
        "action_completion": score_action_completion(
            features.get("n_actions_done"), features.get("n_actions")  # type: ignore[arg-type]
        ),
        "agenda_present": score_agenda_present(features.get("agenda_text")),  # type: ignore[arg-type]
        "recurrence_health": score_recurrence_health(
            features.get("recurrence_scores", []) or []  # type: ignore[arg-type]
        ),
    }
    score = composite_quality(components)
    return {"quality_score": score, "components": components}


def top_and_bottom(
    scored: list[dict[str, Any]], k: int = 5
) -> dict[str, list[dict[str, Any]]]:
    """Rank meetings that have a score; ignore insufficient-data ones."""
    have = [m for m in scored if m.get("quality_score") is not None]
    have.sort(key=lambda m: m["quality_score"])  # type: ignore[arg-type,return-value]
    return {"lowest": have[:k], "highest": list(reversed(have[-k:]))}
