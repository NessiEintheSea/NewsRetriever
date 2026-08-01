"""
Pipeline orchestration — two jobs (requirement 14):

* ``run_ingest``  : fetch → exact-dedup → embed → story link/update → persist.
                    Runs frequently (every 2-3h). No delivery.
* ``run_digest``  : gather recent new/updated stories → rank → diversity →
                    render (full or delta) → deliver → record history.
                    Runs once each morning.

Both take injected ``db`` / ``embedder`` / ``llm`` (and ``notifier`` for digest)
so they are fully testable without network or a real DB.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src import config
from src.db import Database
from src.dedup import dedup_keys, is_exact_duplicate
from src.diversity import select
from src.embedding import Embedder
from src.llm import LLMClient, Metrics
from src.ranking import Candidate, rank
from src.schemas import ArticleFacts
from src.source_quality import classify_source, is_primary, TIER_ORDER
from src.stories import process_article

logger = logging.getLogger(__name__)

_CHANGE_PRIORITY = {"new_story": 3, "major_update": 2, "minor_update": 1, "no_meaningful_change": 0}


@dataclass
class IngestStats:
    feeds_genres: int = 0
    fetched: int = 0
    exact_dups: int = 0
    processed: int = 0
    new_stories: int = 0
    major_updates: int = 0
    minor_updates: int = 0
    no_change: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class DigestStats:
    considered: int = 0
    delivered: int = 0
    skipped_no_change: int = 0
    skipped_minor: int = 0
    skipped_already_delivered: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _interest_terms() -> set[str]:
    return {g.strip().lower() for g in config.GENRES if g.strip()}


# ── Ingestion ────────────────────────────────────────────────────────────────
def run_ingest(
    db: Database,
    embedder: Embedder,
    llm: LLMClient,
    *,
    genres=None,
    keep=None,
    metrics: Metrics | None = None,
) -> IngestStats:
    from src.fetcher import fetch_all

    genres = genres or config.GENRES
    keep = keep or config.ARTICLES_PER_GENRE
    metrics = metrics or llm.metrics
    stats = IngestStats(feeds_genres=len(genres))

    genre_articles = fetch_all(genres, keep)
    articles = [a for arts in genre_articles.values() for a in arts]
    stats.fetched = len(articles)

    lookback = datetime.now(timezone.utc) - timedelta(days=config.STORY_LOOKBACK_DAYS)
    seen = db.seen_dedup_keys(since=lookback)
    lookback_stories = db.recent_stories(since=lookback)

    for article in articles:
        keys = dedup_keys(
            guid=article.guid, canonical_url=article.canonical_url, fp=article.fingerprint
        )
        if is_exact_duplicate(keys, seen):
            stats.exact_dups += 1
            continue
        seen.update(keys)

        # Enrich with full article text (only for unique articles, to bound requests).
        if config.FETCH_FULL_TEXT:
            from src.content import fetch_full_text

            body = fetch_full_text(
                article.url,
                timeout=config.FULL_TEXT_TIMEOUT,
                max_chars=config.FULL_TEXT_MAX_CHARS,
            )
            if body:
                article.description = body

        try:
            result = process_article(
                article, db, embedder, llm,
                lookback_stories=lookback_stories,
                similarity_threshold=config.SIMILARITY_THRESHOLD,
                candidate_limit=config.SIMILARITY_CANDIDATE_LIMIT,
                metrics=metrics,
            )
        except Exception as exc:  # never let one article abort the run
            logger.warning("Failed to process article '%s': %s", article.title[:60], exc)
            stats.errors += 1
            metrics.errors += 1
            continue

        stats.processed += 1
        ct = result.change_type
        if ct == "new_story":
            stats.new_stories += 1
            if result.story not in lookback_stories:
                lookback_stories.append(result.story)  # cluster within this batch
        elif ct == "major_update":
            stats.major_updates += 1
        elif ct == "minor_update":
            stats.minor_updates += 1
        else:
            stats.no_change += 1

    logger.info("Ingest stats: %s", stats.as_dict())
    return stats


# ── Digest ───────────────────────────────────────────────────────────────────
def _representative_article(db: Database, story_id: int):
    arts = db.articles_for_story(story_id)
    if not arts:
        return None
    # Prefer highest-quality source, then most recent.
    def key(a):
        tier = classify_source(a.url)
        return (TIER_ORDER.index(tier) if tier in TIER_ORDER else 99,
                -(a.published_at or a.fetched_at).timestamp())
    return sorted(arts, key=key)[0]


def _age_hours(article) -> float:
    ts = article.published_at or article.fetched_at
    if ts is None:
        return -1.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0)


def _new_item(story, rep, facts: ArticleFacts) -> dict:
    return {
        "kind": "new",
        "title": facts.headline or story.current_title,
        "lede": facts.summary,
        "summary_points": facts.key_facts,
        "why_it_matters": facts.why_it_matters,
        "categories": [facts.category or story.category] if (facts.category or story.category) else [],
        "source_name": rep.source_name if rep else "",
        "url": rep.url if rep else "",
    }


def _update_item(story, event, rep, facts: Optional[ArticleFacts]) -> dict:
    return {
        "kind": "update",
        "title": (facts.headline if facts and facts.headline else story.current_title),
        "lede": facts.summary if facts else "",
        "new_facts": (facts.key_facts if facts and facts.key_facts else event.new_facts),
        "changed_facts": event.changed_facts,
        "unchanged_facts": event.unchanged_facts,
        "why_it_matters": facts.why_it_matters if facts else "",
        "source_name": rep.source_name if rep else "",
        "url": rep.url if rep else "",
    }


def _cached_facts(story) -> ArticleFacts:
    """Fallback ArticleFacts from the ingest-time cache (or a bare summary)."""
    if story.summary_json:
        try:
            return ArticleFacts.model_validate(story.summary_json)
        except Exception:
            pass
    return ArticleFacts(summary=story.rolling_summary, category=story.category)


def build_candidates(db: Database, since: datetime, stats: DigestStats) -> tuple[list, dict]:
    """Return (candidates, meta_by_story_id) for delivery.

    ``meta[story_id] = (kind, story, rep_article, chosen_event_or_None)`` — the
    reader-facing summary is generated later, only for the *selected* items.

    Delivery rules per story:
      * First time it's delivered  → full "new" summary (from cached facts).
      * Already delivered before    → deliver the most significant *newer*
        update as a delta; skip if there is nothing new since last delivery.
      * ``no_meaningful_change`` never delivers; ``minor_update`` gated by config.
    """
    events = db.recent_events(since)
    by_story: dict = {}
    for ev in events:
        by_story.setdefault(ev.story_id, []).append(ev)

    candidates: list[Candidate] = []
    meta: dict = {}
    for story_id, evs in by_story.items():
        stats.considered += 1
        last_at = db.last_delivery_at(story_id)
        first_delivery = last_at is None

        # Events newer than the last successful delivery (all of them if never delivered).
        fresh = [
            e for e in evs
            if (last_at is None or e.detected_at > last_at)
            and e.change_type != "no_meaningful_change"
        ]
        if not fresh:
            if not first_delivery:
                stats.skipped_already_delivered += 1
            else:
                stats.skipped_no_change += 1
            continue

        chosen = max(fresh, key=lambda e: (_CHANGE_PRIORITY.get(e.change_type, 0), e.detected_at))

        if first_delivery:
            kind, change_type = "new", "new_story"
        else:
            if chosen.change_type == "minor_update" and not config.DELIVER_MINOR_UPDATES:
                stats.skipped_minor += 1
                continue
            kind, change_type = "update", chosen.change_type

        story = db.get_story(story_id)
        if story is None:
            continue
        rep = _representative_article(db, story_id)
        tier = classify_source(rep.url if rep else "", (story.summary_json or {}).get("source_type", ""))
        candidates.append(
            Candidate(
                story_id=story_id,
                kind=kind,
                change_type=change_type,
                title=story.current_title,
                url=rep.url if rep else "",
                source_name=rep.source_name if rep else "",
                category=story.category,
                tier=tier,
                is_primary=is_primary(tier),
                importance=story.importance_score,
                age_hours=_age_hours(rep) if rep else -1.0,
                embedding=story.representative_embedding,
            )
        )
        meta[story_id] = (kind, story, rep, None if kind == "new" else chosen)
    return candidates, meta


def run_digest(
    db: Database,
    embedder: Embedder,
    llm: LLMClient,
    notifier,
    *,
    since_hours: int = 24,
    channel_name: str = "discord",
    metrics: Metrics | None = None,
) -> tuple[dict, DigestStats]:
    from src.deliver import summarize_new, summarize_update

    stats = DigestStats()
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    candidates, meta = build_candidates(db, since, stats)

    weights = {
        "WEIGHT_RELEVANCE": config.WEIGHT_RELEVANCE,
        "WEIGHT_NOVELTY": config.WEIGHT_NOVELTY,
        "WEIGHT_IMPORTANCE": config.WEIGHT_IMPORTANCE,
        "WEIGHT_SOURCE_QUALITY": config.WEIGHT_SOURCE_QUALITY,
        "WEIGHT_RECENCY": config.WEIGHT_RECENCY,
    }
    ranked = rank(candidates, weights, _interest_terms())
    for c in ranked:
        logger.info("rank story=%s kind=%s score=%.3f %s", c.story_id, c.kind, c.score, c.breakdown)

    selected = select(
        ranked,
        max_items=config.DIGEST_MAX_ITEMS,
        max_per_source=config.MAX_ITEMS_PER_SOURCE,
        max_per_category=config.MAX_ITEMS_PER_CATEGORY,
        max_updates=config.MAX_UPDATE_ITEMS,
        require_primary=config.REQUIRE_PRIMARY_SOURCE,
    )

    # Polish ONLY the selected items into reader-facing, Japanese news briefs.
    items: dict = {}
    for c in selected:
        entry = meta.get(c.story_id)
        if not entry:
            continue
        kind, story, rep, ev = entry
        text = (rep.description if rep and rep.description else story.rolling_summary)
        title = rep.title if rep and rep.title else story.current_title
        if kind == "new":
            facts = summarize_new(llm, title, text) or _cached_facts(story)
            items[c.story_id] = _new_item(story, rep, facts)
        else:
            facts = summarize_update(llm, story.current_title, story.rolling_summary,
                                     ev.new_facts, ev.changed_facts)
            items[c.story_id] = _update_item(story, ev, rep, facts)

    now = datetime.now(timezone.utc)
    digest = {
        "date": now.strftime("%a %d %b %Y"),
        "generated_at": now.strftime("%H:%M UTC"),
        "items": [items[c.story_id] for c in selected if c.story_id in items],
    }

    if not digest["items"]:
        logger.info("Digest: no items to deliver.")
        return digest, stats

    try:
        notifier.send_digest(digest)
        delivery_status = "success"
    except Exception as exc:
        logger.error("Delivery failed: %s", exc)
        delivery_status = "failed"
        if metrics:
            metrics.errors += 1

    for c in selected:
        if c.story_id not in items:
            continue
        db.record_delivery(
            story_id=c.story_id,
            article_id=None,
            delivery_type=c.kind,
            channel=channel_name,
            status=delivery_status,
        )
        if delivery_status == "success":
            stats.delivered += 1

    logger.info("Digest stats: %s", stats.as_dict())
    if delivery_status == "failed":
        raise RuntimeError("Digest delivery failed; recorded failure in delivery_history.")
    return digest, stats
