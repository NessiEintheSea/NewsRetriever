"""
Source-quality classification.

Maps an article's host (and, when available, the LLM's ``source_type`` judgement)
onto one of four tiers and a 0-1 quality score used by ranking. Also exposes the
preferred order for choosing a story's representative article.
"""
from __future__ import annotations

from urllib.parse import urlparse

# tier -> quality score (0-1)
TIER_SCORE = {
    "primary": 1.0,
    "high_quality": 0.8,
    "secondary": 0.5,
    "aggregator": 0.25,
}
TIER_ORDER = ["primary", "high_quality", "secondary", "aggregator"]

# Host substrings by tier. Order of checks: primary -> high_quality -> secondary.
_HIGH_QUALITY_HOSTS = {
    "reuters.com", "apnews.com", "bbc.co.uk", "bbci.co.uk", "nytimes.com",
    "bloomberg.com", "ft.com", "wsj.com", "nikkei.com", "nhk.or.jp",
    "washingtonpost.com", "theguardian.com", "economist.com",
}
_SECONDARY_HOSTS = {
    "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
    "engadget.com", "sciencedaily.com", "artificialintelligence-news.com",
    "japantoday.com", "decrypt.co",
}
_AGGREGATOR_HOSTS = {
    "feedburner.com", "news.google.com", "cointelegraph.com", "coindesk.com",
    "medium.com",
}
# Primary is mostly detected structurally (gov/press/official) plus these:
_PRIMARY_HOSTS = {
    "arxiv.org", "github.com", "openai.com", "anthropic.com", "blog.google",
    "prnewswire.com", "businesswire.com", "globenewswire.com",
}
_PRIMARY_SUFFIXES = (".gov", ".go.jp", ".gov.uk", ".edu", ".ac.jp")


def _host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def classify_source(url: str, llm_source_type: str = "") -> str:
    """Return the tier for a URL, optionally biased by the LLM's judgement."""
    host = _host(url)
    if host:
        if host in _PRIMARY_HOSTS or host.endswith(_PRIMARY_SUFFIXES):
            return "primary"
        if any(host.endswith(h) for h in _HIGH_QUALITY_HOSTS):
            return "high_quality"
        if any(host.endswith(h) for h in _AGGREGATOR_HOSTS):
            return "aggregator"
        if any(host.endswith(h) for h in _SECONDARY_HOSTS):
            return "secondary"
    # Fall back to the LLM's judgement, else secondary.
    if llm_source_type in TIER_SCORE:
        return llm_source_type
    return "secondary"


def quality_score(tier: str) -> float:
    return TIER_SCORE.get(tier, 0.5)


def is_primary(tier: str) -> bool:
    return tier == "primary"
