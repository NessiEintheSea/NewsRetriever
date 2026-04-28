"""
News Agent — main entrypoint.

Pipeline:
  1. Validate config / secrets
  2. Fetch RSS articles per genre
  3. Summarise all articles in a single Claude Haiku call
  4. Format as Slack Block Kit payload
  5. POST to Slack webhook

Usage:
  python main.py
  GENRES=tech,science python main.py
  ARTICLES_PER_GENRE=5 python main.py
"""
from __future__ import annotations

import logging
import sys

from src.config import validate, GENRES, ARTICLES_PER_GENRE, MIN_FETCH, FETCH_RATIO
from src.fetcher import fetch_all
from src.filter import filter_all
from src.summarizer import summarize
from src.formatter import build_payload
from src.notifier import post_to_slack

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run() -> None:
    # ------------------------------------------------------------------ #
    # 0. Validate secrets up front
    # ------------------------------------------------------------------ #
    try:
        validate()
    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)

    logger.info(
        "Starting news agent  |  genres=%s  |  keep=%d  |  min_fetch=%d  |  ratio=%.0f%%",
        GENRES,
        ARTICLES_PER_GENRE,
        MIN_FETCH,
        FETCH_RATIO * 100,
    )

    # ------------------------------------------------------------------ #
    # 1. Fetch (ratio-based sampling)
    # ------------------------------------------------------------------ #
    genre_articles = fetch_all(GENRES, ARTICLES_PER_GENRE)

    total_fetched = sum(len(arts) for arts in genre_articles.values())
    if total_fetched == 0:
        logger.error("No articles fetched across all genres. Aborting.")
        sys.exit(1)

    logger.info("Total articles fetched across all genres: %d", total_fetched)

    # ------------------------------------------------------------------ #
    # 2. Filter (Claude scores by importance, keeps top N per genre)
    # ------------------------------------------------------------------ #
    genre_articles = filter_all(genre_articles, ARTICLES_PER_GENRE)

    total_kept = sum(len(arts) for arts in genre_articles.values())
    logger.info("Total articles after filtering: %d", total_kept)

    # ------------------------------------------------------------------ #
    # 3. Summarise (single API call for all kept articles)
    # ------------------------------------------------------------------ #
    all_articles = [art for arts in genre_articles.values() for art in arts]
    summarize(all_articles)

    # ------------------------------------------------------------------ #
    # 4. Format
    # ------------------------------------------------------------------ #
    payload = build_payload(genre_articles)

    # ------------------------------------------------------------------ #
    # 5. Notify
    # ------------------------------------------------------------------ #
    try:
        post_to_slack(payload)
    except RuntimeError as exc:
        logger.error("Failed to send Slack notification: %s", exc)
        sys.exit(1)

    logger.info("Done.")


if __name__ == "__main__":
    run()
