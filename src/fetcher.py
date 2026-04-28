"""
Fetcher: pulls top N articles from RSS feeds for a given genre.

Token-efficiency strategy:
- Only sends title + truncated description to the model (no full article body).
- Tries feeds in priority order; stops once N articles are collected.
- Strips HTML tags from descriptions before returning.
"""
from __future__ import annotations

import html
import re
import logging
from dataclasses import dataclass

import feedparser

from src.config import (
    FEEDS,
    MAX_DESCRIPTION_CHARS,
    ARTICLES_PER_GENRE,
    MIN_FETCH,
    FETCH_RATIO,
)

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    description: str  # already stripped and truncated
    url: str
    genre: str


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def _calculate_fetch_count(total_available: int) -> int:
    """
    Calculate how many articles to use after fetching all available.
    Formula: max(MIN_FETCH, total_available × FETCH_RATIO)
    """
    ratio_based = int(total_available * FETCH_RATIO)
    return max(MIN_FETCH, ratio_based)


def fetch_genre(
    genre: str,
    keep: int = ARTICLES_PER_GENRE,
) -> list[Article]:
    """
    Fetch articles for a genre using ratio-based sampling.

    Fetches all entries from all feeds in one pass, then applies
    the ratio to determine how many to keep. This avoids the
    double-fetch problem of counting then re-fetching.

    Args:
        genre: Genre key matching FEEDS config
        keep: Final number of articles wanted after filtering
    """
    feeds = FEEDS.get(genre)
    if not feeds:
        logger.warning("No feeds configured for genre '%s'", genre)
        return []

    # ── Single pass: collect all available articles ──────────────────────
    seen_urls: set[str] = set()
    all_articles: list[Article] = []

    for feed_url in feeds:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries:
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = _strip_html(entry.get("title", "")).strip()
                raw_desc = (
                    entry.get("summary")
                    or entry.get("description")
                    or ""
                )
                description = _truncate(_strip_html(raw_desc), MAX_DESCRIPTION_CHARS)

                if not title:
                    continue

                all_articles.append(Article(
                    title=title,
                    description=description,
                    url=url,
                    genre=genre,
                ))
        except Exception as exc:
            logger.warning("Failed to fetch feed %s: %s", feed_url, exc)

    # ── Apply ratio to determine fetch count ─────────────────────────────
    total_available = len(all_articles)
    fetch_count = _calculate_fetch_count(total_available)
    articles = all_articles[:fetch_count]

    logger.info(
        "Genre '%s': %d articles available → using %d (ratio=%.0f%%, min=%d) → keeping %d",
        genre,
        total_available,
        len(articles),
        FETCH_RATIO * 100,
        MIN_FETCH,
        keep,
    )

    if not articles:
        logger.error("No articles fetched for genre '%s'", genre)

    return articles


def fetch_all(
    genres: list[str],
    keep: int = ARTICLES_PER_GENRE,
) -> dict[str, list[Article]]:
    """Fetch articles for every genre. Returns {genre: [Article, ...]}."""
    return {genre: fetch_genre(genre, keep) for genre in genres}