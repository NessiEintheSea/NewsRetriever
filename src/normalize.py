"""
Normalisation of article URLs and text, applied before any comparison or LLM
call so that trivially-different-but-identical articles collapse together.
"""
from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Tracking / campaign params that never identify the content itself.
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "utm_id",
    "utm_reader",
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
    "cmpid",
    "spm",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Common "— Media Name" / "| Media Name" trailing boilerplate on RSS titles.
_TITLE_TAIL_RE = re.compile(r"\s*[|\-–—]\s*[^|\-–—]{2,40}$")


def normalize_url(url: str) -> str:
    """Canonicalise a URL for comparison.

    * lowercases the scheme and host
    * removes tracking query params (utm_*, fbclid, gclid, ...)
    * drops the fragment
    * removes a trailing slash on the path
    * sorts remaining query params for a stable key
    """
    if not url:
        return ""
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS
    ]
    kept.sort()
    query = urlencode(kept)

    return urlunsplit((scheme, netloc, path, query, ""))  # fragment dropped


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    """Full text normalisation: HTML strip, Unicode NFKC, whitespace collapse."""
    if not text:
        return ""
    text = strip_html(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    return text.strip()


def normalize_title(title: str) -> str:
    """Normalise a title and strip an obvious trailing media-name suffix.

    Only strips the suffix when the remaining title stays reasonably long, to
    avoid mangling short headlines that legitimately contain a dash.
    """
    title = normalize_text(title)
    if not title:
        return ""
    stripped = _TITLE_TAIL_RE.sub("", title).strip()
    if len(stripped) >= 15:
        return stripped
    return title
