"""
Core data structures shared across the pipeline.

``Article`` is the object produced by the fetcher and enriched as it moves
through normalisation → dedup → embedding → story linking. It is kept
backwards-compatible with the original 4-field construction
(``title``, ``description``, ``url``, ``genre``) — all new fields are optional.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Article:
    # Core (original fields) --------------------------------------------------
    title: str
    description: str
    url: str
    genre: str

    # Identity / normalisation (Phase 2) --------------------------------------
    guid: str = ""
    canonical_url: str = ""
    normalized_title: str = ""
    source_name: str = ""
    published_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=_now)
    content_hash: str = ""
    fingerprint: str = ""
    language: str = ""

    # Enrichment (Phase 3+) ---------------------------------------------------
    embedding: Optional[list[float]] = None
    story_id: Optional[int] = None
    summary: str = ""

    # DB identity -------------------------------------------------------------
    id: Optional[int] = None


@dataclass
class Story:
    id: Optional[int]
    current_title: str
    rolling_summary: str = ""
    representative_embedding: Optional[list[float]] = None
    first_seen_at: datetime = field(default_factory=_now)
    last_updated_at: datetime = field(default_factory=_now)
    importance_score: float = 0.0
    category: str = ""
    status: str = "active"
    # Cached ArticleFacts (summary, why_it_matters, key_facts, ...) for the
    # representative article, so the daily digest needs no extra LLM call.
    summary_json: Optional[dict] = None


@dataclass
class StoryEvent:
    id: Optional[int]
    story_id: int
    article_id: Optional[int]
    change_type: str
    new_facts: list[str] = field(default_factory=list)
    changed_facts: list[str] = field(default_factory=list)
    unchanged_facts: list[str] = field(default_factory=list)
    confidence: float = 0.0
    detected_at: datetime = field(default_factory=_now)
