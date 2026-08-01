"""
Diversity control (MMR-style).

Ranking alone tends to surface several near-identical top stories. This selects a
final set that balances score against novelty-vs-already-selected (Maximal
Marginal Relevance) while enforcing hard constraints:

    * at most DIGEST_MAX_ITEMS total
    * at most MAX_ITEMS_PER_SOURCE per media source
    * at most MAX_ITEMS_PER_CATEGORY per category
    * one item per story
    * at most MAX_UPDATE_ITEMS updates
    * at least one primary source when REQUIRE_PRIMARY_SOURCE (relaxed if none exist)
"""
from __future__ import annotations

from typing import Optional

from src.embedding import cosine
from src.ranking import Candidate

_LAMBDA = 0.7  # weight on score vs. dissimilarity


def _max_sim(candidate: Candidate, selected: list[Candidate]) -> float:
    if not selected or candidate.embedding is None:
        return 0.0
    return max((cosine(candidate.embedding, s.embedding) for s in selected), default=0.0)


def select(
    candidates: list[Candidate],
    *,
    max_items: int,
    max_per_source: int,
    max_per_category: int,
    max_updates: int,
    require_primary: bool,
) -> list[Candidate]:
    selected: list[Candidate] = []
    source_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    story_ids: set = set()
    update_count = 0

    def fits(c: Candidate) -> bool:
        if c.story_id is not None and c.story_id in story_ids:
            return False
        if source_counts.get(c.source_name, 0) >= max_per_source:
            return False
        if category_counts.get(c.category, 0) >= max_per_category:
            return False
        if c.kind == "update" and update_count >= max_updates:
            return False
        return True

    def take(c: Candidate) -> None:
        nonlocal update_count
        selected.append(c)
        source_counts[c.source_name] = source_counts.get(c.source_name, 0) + 1
        category_counts[c.category] = category_counts.get(c.category, 0) + 1
        if c.story_id is not None:
            story_ids.add(c.story_id)
        if c.kind == "update":
            update_count += 1

    remaining = list(candidates)
    while remaining and len(selected) < max_items:
        best: Optional[Candidate] = None
        best_val = float("-inf")
        for c in remaining:
            if not fits(c):
                continue
            mmr = _LAMBDA * c.score - (1 - _LAMBDA) * _max_sim(c, selected)
            if mmr > best_val:
                best_val, best = mmr, c
        if best is None:
            break
        take(best)
        remaining.remove(best)

    if require_primary and not any(c.is_primary for c in selected):
        _ensure_primary(selected, candidates, story_ids, max_items)

    return selected


def _ensure_primary(
    selected: list[Candidate], candidates: list[Candidate], story_ids: set, max_items: int
) -> None:
    """Guarantee at least one primary source if any exists (relaxes otherwise)."""
    primaries = [c for c in candidates if c.is_primary and c.story_id not in story_ids]
    if not primaries:
        return  # No primary available — relax the constraint silently.
    best_primary = max(primaries, key=lambda c: c.score)
    if len(selected) < max_items:
        selected.append(best_primary)
    else:
        # Replace the lowest-scoring non-primary item.
        non_primary = [c for c in selected if not c.is_primary]
        if non_primary:
            victim = min(non_primary, key=lambda c: c.score)
            selected[selected.index(victim)] = best_primary
    selected.sort(key=lambda c: c.score, reverse=True)
