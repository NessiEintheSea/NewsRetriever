"""
Optional full-article-text extraction.

RSS descriptions are often short/truncated, which limits summary and update-diff
quality. When ``FETCH_FULL_TEXT`` is on, the ingest job fetches the article page
and pulls the main body text. Kept dependency-free (stdlib ``html.parser``); a
heavier extractor (e.g. trafilatura) can be dropped in behind ``fetch_full_text``
later. Failures return "" so ingestion falls back to the RSS description.
"""
from __future__ import annotations

import logging
from html.parser import HTMLParser
from typing import Callable, Optional

from src.normalize import normalize_text

logger = logging.getLogger(__name__)

_SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form"}
_TEXT_TAGS = {"p", "h1", "h2", "h3", "li", "blockquote"}


class _BodyExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._capture = False
        self._buf: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _TEXT_TAGS and self._skip_depth == 0:
            self._capture = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _TEXT_TAGS and self._capture:
            text = normalize_text(" ".join(self._buf))
            if len(text) >= 20:  # drop menu items / tiny fragments
                self.paragraphs.append(text)
            self._capture = False
            self._buf = []

    def handle_data(self, data):
        if self._capture and self._skip_depth == 0:
            self._buf.append(data)


def extract_text_from_html(html_str: str) -> str:
    if not html_str:
        return ""
    parser = _BodyExtractor()
    try:
        parser.feed(html_str)
    except Exception:  # malformed HTML — return whatever we captured
        pass
    return "\n".join(parser.paragraphs).strip()


def fetch_full_text(
    url: str,
    *,
    timeout: int = 10,
    max_chars: int = 4000,
    get_fn: Optional[Callable] = None,
) -> str:
    """Fetch and extract the main body text of an article, or "" on failure."""
    if not url:
        return ""
    try:
        if get_fn is None:
            import requests

            def get_fn(u, t):
                return requests.get(
                    u, timeout=t,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; NewsAgent/1.0)"},
                )

        resp = get_fn(url, timeout)
        if getattr(resp, "status_code", 200) != 200:
            return ""
        html_str = getattr(resp, "text", "") or ""
        text = extract_text_from_html(html_str)
        return text[:max_chars]
    except Exception as exc:
        logger.warning("Full-text fetch failed for %s: %s", url[:80], exc)
        return ""
