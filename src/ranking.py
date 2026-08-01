"""
Multi-factor ranking.

Replaces the old importance-only ordering with a weighted blend of:
    relevance, novelty, importance, source_quality, recency
each normalised to 0-1. Weights come from config (normalised at use-time so they
need not sum to exactly 1.0). ``score_candidate`` returns the final score plus a
per-factor breakdown so the computation can be logged (requirement 11).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_WORD_RE = re.compile(r"\w+", re.UNICODE)

_NOVELTY_BY_CHANGE = {
    "new_story": 1.0,
    "major_update": 0.7,
    "minor_update": 0.4,
    "no_meaningful_change": 0.0,
}

_RECENCY_WINDOW_HOURS = 48.0


@dataclass
class Candidate:
    story_id: Optional[int]
    kind: str                       # "new" | "update"
    change_type: str
    title: str
    url: str
    source_name: str
    category: str
    tier: str                       # source-quality tier
    is_primary: bool
    importance: float               # 0-1
    age_hours: float                # article age
    embedding: Optional[list[float]] = None
    payload: dict = field(default_factory=dict)  # rendering data (facts / diff)

    # filled in by scoring
    score: float = 0.0
    breakdown: dict = field(default_factory=dict)


def _relevance(candidate: Candidate, interest_terms: set[str]) -> float:
    text = f"{candidate.title} {candidate.category}".lower()
    tokens = set(_WORD_RE.findall(text))
    matches = len(tokens & interest_terms)
    return min(1.0, 0.4 + 0.3 * matches)


def _novelty(candidate: Candidate) -> float:
    return _NOVELTY_BY_CHANGE.get(candidate.change_type, 0.5)


def _recency(candidate: Candidate) -> float:
    if candidate.age_hours < 0:
        return 0.5
    return max(0.0, min(1.0, 1.0 - candidate.age_hours / _RECENCY_WINDOW_HOURS))


def _normalise_weights(weights: dict) -> dict:
    total = sum(max(0.0, v) for v in weights.values()) or 1.0
    return {k: max(0.0, v) / total for k, v in weights.items()}


def score_candidate(candidate: Candidate, weights: dict, interest_terms: set[str]) -> Candidate:
    w = _normalise_weights(weights)
    from src.source_quality import quality_score

    factors = {
        "relevance": _relevance(candidate, interest_terms),
        "novelty": _novelty(candidate),
        "importance": max(0.0, min(1.0, candidate.importance)),
        "source_quality": quality_score(candidate.tier),
        "recency": _recency(candidate),
    }
    final = sum(factors[k] * w.get(f"WEIGHT_{k.upper()}", 0.0) for k in factors)
    candidate.score = final
    candidate.breakdown = {**factors, "final": round(final, 4)}
    return candidate


def rank(candidates: list[Candidate], weights: dict, interest_terms: set[str]) -> list[Candidate]:
    for c in candidates:
        score_candidate(c, weights, interest_terms)
    return sorted(candidates, key=lambda c: c.score, reverse=True)
