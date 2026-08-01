"""
Digest builder — converts the pipeline's per-genre Article objects into the
channel-agnostic digest dict consumed by notifiers.

This is the Phase-1 bridge that keeps the existing (fetch → filter → summarise)
flow working through the new Notifier abstraction. Later phases produce richer
digests (story updates, ranking) but the dict shape stays the same.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse


def source_name_from_url(url: str) -> str:
    """Best-effort human-readable source name from a URL host."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    # feeds.bbci.co.uk -> bbci.co.uk ; rss.nytimes.com -> nytimes.com
    for prefix in ("feeds.", "rss.", "feed."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def _summary_points(article) -> list[str]:
    """Turn a 2-sentence summary into short bullet points."""
    summary = (getattr(article, "summary", "") or article.description or "").strip()
    if not summary:
        return []
    # Split into sentences on '. ' but keep it simple and robust.
    parts = [p.strip() for p in summary.replace("。", "。\n").split("\n")]
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        parts = [s.strip() + "." for s in summary.split(". ") if s.strip()]
    return parts[:3] if parts else [summary]


def build_digest(genre_articles: dict) -> dict:
    """Build a digest dict from ``{genre: [Article, ...]}``."""
    now = datetime.now(timezone.utc)
    items: list[dict] = []
    for genre, articles in genre_articles.items():
        for art in articles:
            items.append(
                {
                    "kind": "new",
                    "title": art.title,
                    "summary_points": _summary_points(art),
                    "why_it_matters": "",
                    "categories": [genre.capitalize()],
                    "source_name": source_name_from_url(art.url),
                    "url": art.url,
                }
            )
    return {
        "date": now.strftime("%a %d %b %Y"),
        "generated_at": now.strftime("%H:%M UTC"),
        "items": items,
    }
