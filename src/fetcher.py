"""
Fetcher: pulls articles from RSS feeds for a given genre.

Performance strategy:
- Parallel feed fetching using ThreadPoolExecutor
- 10 second timeout per feed to prevent hanging
- Single pass with ratio-based sampling
- Graceful degradation: skips dead/slow feeds, continues with others
"""
from __future__ import annotations

import html
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import feedparser
import requests

from src.config import (
    FEEDS,
    MAX_DESCRIPTION_CHARS,
    ARTICLES_PER_GENRE,
    MIN_FETCH,
    FETCH_RATIO,
)

logger = logging.getLogger(__name__)

FEED_TIMEOUT_SECONDS = 10
MAX_WORKERS = 5


@dataclass
class Article:
    title: str
    description: str
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
    Calculate how many articles to use.
    Formula: max(MIN_FETCH, total_available x FETCH_RATIO)
    """
    ratio_based = int(total_available * FETCH_RATIO)
    return max(MIN_FETCH, ratio_based)


def _fetch_feed_with_timeout(feed_url: str) -> list:
    """
    Fetch a single feed URL with timeout.
    Returns list of entries or empty list on failure/timeout.
    """
    try:
        response = requests.get(
            feed_url,
            timeout=FEED_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsAgent/1.0)"},
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        return parsed.entries
    except requests.Timeout:
        logger.warning("Feed timed out after %ds: %s", FEED_TIMEOUT_SECONDS, feed_url)
        return []
    except Exception as exc:
        logger.warning("Failed to fetch feed %s: %s", feed_url, exc)
        return []


def _fetch_feeds_parallel(feed_urls: list[str]) -> dict[str, list]:
    """
    Fetch multiple feeds simultaneously using a thread pool.
    Returns {feed_url: [entries]} — preserves order for deduplication.
    All feeds fire at the same time, total wait = slowest feed (max 10s).
    """
    results: dict[str, list] = {url: [] for url in feed_urls}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(_fetch_feed_with_timeout, url): url
            for url in feed_urls
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                logger.warning("Unexpected error fetching %s: %s", url, exc)
                results[url] = []

    return results


def fetch_genre(
    genre: str,
    keep: int = ARTICLES_PER_GENRE,
) -> list[Article]:
    """
    Fetch articles for a genre using parallel fetching + ratio-based sampling.

    All feeds for the genre are fetched simultaneously.
    Total fetch time = slowest responding feed (max FEED_TIMEOUT_SECONDS).
    """
    feeds = FEEDS.get(genre)
    if not feeds:
        logger.warning("No feeds configured for genre '%s'", genre)
        return []

    # ── Fetch all feeds in parallel ──────────────────────────────────────
    feed_results = _fetch_feeds_parallel(feeds)

    # ── Collect and deduplicate articles ─────────────────────────────────
    seen_urls: set[str] = set()
    all_articles: list[Article] = []

    for feed_url in feeds:  # iterate in original order for consistency
        entries = feed_results.get(feed_url, [])
        for entry in entries:
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

    # ── Apply ratio ───────────────────────────────────────────────────────
    total_available = len(all_articles)
    fetch_count = _calculate_fetch_count(total_available)
    articles = all_articles[:fetch_count]

    logger.info(
        "Genre '%s': %d available → using %d (ratio=%.0f%%, min=%d) → keeping %d",
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
    """
    Fetch articles for every genre in parallel.
    All genres fire simultaneously for maximum speed.
    """
    with ThreadPoolExecutor(max_workers=len(genres)) as executor:
        future_to_genre = {
            executor.submit(fetch_genre, genre, keep): genre
            for genre in genres
        }
        results: dict[str, list[Article]] = {}
        for future in as_completed(future_to_genre):
            genre = future_to_genre[future]
            try:
                results[genre] = future.result()
            except Exception as exc:
                logger.error("Failed to fetch genre '%s': %s", genre, exc)
                results[genre] = []

    # Return in original genre order
    return {genre: results.get(genre, []) for genre in genres}