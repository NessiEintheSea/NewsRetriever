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

from src.config import FEEDS, MAX_DESCRIPTION_CHARS, ARTICLES_PER_GENRE

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


def fetch_genre(genre: str, n: int = ARTICLES_PER_GENRE) -> list[Article]:
    """
    Return up to `n` articles for `genre`.
    Iterates through configured feeds until enough unique articles are found.
    """
    feeds = FEEDS.get(genre)
    if not feeds:
        logger.warning("No feeds configured for genre '%s'", genre)
        return []

    seen_urls: set[str] = set()
    articles: list[Article] = []

    for feed_url in feeds:
        if len(articles) >= n:
            break
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries:
                if len(articles) >= n:
                    break

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

                articles.append(Article(
                    title=title,
                    description=description,
                    url=url,
                    genre=genre,
                ))
        except Exception as exc:
            logger.warning("Failed to fetch feed %s: %s", feed_url, exc)

    if not articles:
        logger.error("No articles fetched for genre '%s'", genre)
    else:
        logger.info("Fetched %d articles for genre '%s'", len(articles), genre)

    return articles


def fetch_all(genres: list[str], n: int = ARTICLES_PER_GENRE) -> dict[str, list[Article]]:
    """Fetch articles for every genre. Returns {genre: [Article, ...]}."""
    return {genre: fetch_genre(genre, n) for genre in genres}
