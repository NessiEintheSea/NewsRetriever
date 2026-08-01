"""
Cheap exact-duplicate detection. Runs BEFORE any embedding or LLM call so that
already-seen articles never cost an API request (requirement 5 & 15).

Duplicate signals, in order of trust:
    1. RSS GUID
    2. normalized canonical URL
    3. content fingerprint  = sha256(normalize(title + description))
    4. content hash         = sha256(normalize(body or description))
"""
from __future__ import annotations

import hashlib

from src.normalize import normalize_text, normalize_title


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint(title: str, description: str) -> str:
    """Stable fingerprint of an article's title + description."""
    basis = normalize_title(title) + "\x1f" + normalize_text(description)
    return _sha256(basis)


def content_hash(body: str) -> str:
    """Hash of the article body (or description) after normalisation."""
    return _sha256(normalize_text(body))


def dedup_keys(*, guid: str, canonical_url: str, fp: str) -> list[str]:
    """The keys that identify an article as an exact duplicate."""
    keys = []
    if guid:
        keys.append(f"guid:{guid}")
    if canonical_url:
        keys.append(f"url:{canonical_url}")
    if fp:
        keys.append(f"fp:{fp}")
    return keys


def is_exact_duplicate(keys: list[str], seen: set[str]) -> bool:
    """True if any of ``keys`` is already in the ``seen`` set."""
    return any(k in seen for k in keys)
