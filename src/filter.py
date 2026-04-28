"""
Filter: uses Claude Haiku to score articles by importance and
select the top N for each genre.

Token-efficiency strategy:
- Sends titles ONLY for scoring (not descriptions) — ~20 tokens/article
- One API call per genre for scoring
- Only top N articles proceed to the summariser with full descriptions
"""
from __future__ import annotations

import json
import logging
import re

import anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    FILTER_PROMPT,
    ARTICLES_PER_GENRE,
)
from src.fetcher import Article

logger = logging.getLogger(__name__)


def _build_filter_prompt(articles: list[Article]) -> str:
    """Build a titles-only prompt for importance scoring."""
    lines = []
    for i, art in enumerate(articles, start=1):
        lines.append(f"{i}. {art.title}")
    return (
        f"Score these {len(articles)} news article titles by importance:\n\n"
        + "\n".join(lines)
    )


def _parse_scores(response_text: str, count: int) -> dict[int, float]:
    """
    Parse the JSON scores response into {1-based index: score}.
    Robust to minor formatting issues — strips markdown fences if present.
    """
    # Strip markdown code fences if model wraps in ```json ... ```
    cleaned = re.sub(r"```(?:json)?|```", "", response_text).strip()

    try:
        data = json.loads(cleaned)
        return {item["index"]: float(item["score"]) for item in data}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Failed to parse filter scores: %s — using positional order", exc)
        # Fallback: assign descending scores by position (newest = highest)
        return {i: float(count - i + 1) for i in range(1, count + 1)}


def filter_genre(
    articles: list[Article],
    keep: int = ARTICLES_PER_GENRE,
) -> list[Article]:
    """
    Score all articles by importance and return the top `keep` articles.

    Pipeline:
    1. Send titles only to Claude for importance scoring (cheap)
    2. Parse scores
    3. Sort by score descending
    4. Return top `keep` articles

    Falls back to first `keep` articles if API call fails.
    """
    if len(articles) <= keep:
        logger.info(
            "Genre '%s': %d articles ≤ keep=%d, skipping filter",
            articles[0].genre if articles else "unknown",
            len(articles),
            keep,
        )
        return articles[:keep]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_prompt = _build_filter_prompt(articles)
    genre = articles[0].genre if articles else "unknown"

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            system=FILTER_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
        logger.info(
            "Filter '%s': scored %d articles using %d input / %d output tokens",
            genre,
            len(articles),
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        scores = _parse_scores(raw_text, len(articles))

    except Exception as exc:
        logger.warning(
            "Filter API call failed for genre '%s': %s — using first %d articles",
            genre,
            exc,
            keep,
        )
        return articles[:keep]

    # Sort articles by score descending, keep top N
    scored = sorted(
        enumerate(articles, start=1),
        key=lambda x: scores.get(x[0], 0),
        reverse=True,
    )
    top_articles = [art for _, art in scored[:keep]]

    logger.info(
        "Filter '%s': kept %d/%d articles  scores=%s",
        genre,
        keep,
        len(articles),
        {art.title[:40]: scores.get(i, 0) for i, art in scored[:keep]},
    )

    return top_articles


def filter_all(
    genre_articles: dict[str, list[Article]],
    keep: int = ARTICLES_PER_GENRE,
) -> dict[str, list[Article]]:
    """Filter all genres down to top `keep` articles each."""
    return {
        genre: filter_genre(articles, keep)
        for genre, articles in genre_articles.items()
    }
