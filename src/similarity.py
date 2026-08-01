"""
Similarity helpers used for story linking:

* ``find_candidates`` — cheap embedding-cosine shortlist of existing stories.
* ``extract_entities`` — heuristic proper-noun / product / org extraction so we
  can require entity overlap before treating two articles as the same story
  (this is what stops "OpenAI announces X" and "Anthropic announces X" from
  collapsing on lexical similarity alone).
"""
from __future__ import annotations

import re
from typing import Iterable

from src.embedding import cosine
from src.normalize import normalize_text

# Sequences of Capitalized Words (latin proper nouns / product names).
_PROPER_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\b")
# Katakana runs (Japanese product / company names).
_KATAKANA_RE = re.compile(r"[゠-ヿ]{2,}")
# Quoted terms.
_QUOTED_RE = re.compile(r"[\"“”『「]([^\"“”』」]{2,40})[\"“”』」]")

_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "and", "to", "with", "as",
    "new", "news", "report", "update", "breaking", "why", "how",
}


def extract_entities(text: str) -> set[str]:
    text = normalize_text(text)
    ents: set[str] = set()
    for m in _PROPER_RE.findall(text):
        token = m.strip().lower()
        if token and token not in _STOPWORDS and len(token) > 1:
            ents.add(token)
    for m in _KATAKANA_RE.findall(text):
        ents.add(m)
    for m in _QUOTED_RE.findall(text):
        ents.add(m.strip().lower())
    return ents


def entity_overlap(a: set[str], b: set[str]) -> int:
    return len(a & b)


def find_candidates(article, stories: Iterable, limit: int, floor: float = 0.30):
    """Return ``[(story, score), ...]`` sorted by embedding cosine, best first."""
    scored = []
    for story in stories:
        score = cosine(article.embedding, story.representative_embedding)
        if score >= floor:
            scored.append((story, score))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]
