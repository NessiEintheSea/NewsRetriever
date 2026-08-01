"""
Embeddings.

Anthropic has no embedding endpoint, and the constraints are: no new heavy
dependency, and no external API in tests. So the default embedder is a
deterministic, offline lexical embedder — hashed word + character n-grams into a
fixed-size L2-normalised vector. Cosine similarity over these vectors gives a
usable "semantic-ish" signal for candidate retrieval.

Crucially this is only a *candidate* signal: story identity is never decided by
embedding similarity alone (see ``stories.py`` — entity overlap + LLM judgement
are also required).

``Embedder`` is a Protocol so a real provider (Voyage, OpenAI, a local model)
can be dropped in later without touching callers.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Callable, Optional, Protocol

from src.normalize import normalize_text

logger = logging.getLogger(__name__)

DIM = 256
_WORD_RE = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]:
        ...


def _hash_bucket(token: str) -> int:
    h = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % DIM


def _tokens(text: str) -> list[str]:
    text = normalize_text(text).lower()
    words = _WORD_RE.findall(text)
    grams: list[str] = list(words)
    # word bigrams (capture short multi-word entities)
    grams += [f"{a}_{b}" for a, b in zip(words, words[1:])]
    # character 3-grams over the whole string (helps CJK where words don't split)
    compact = text.replace(" ", "")
    grams += [compact[i : i + 3] for i in range(len(compact) - 2)]
    return grams


class LocalLexicalEmbedder:
    """Deterministic offline embedder — no network, no extra deps."""

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        for tok in _tokens(text):
            vec[_hash_bucket(tok)] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


class OpenAIEmbedder:
    """Real semantic embeddings via OpenAI's embeddings endpoint.

    Anthropic has no embedding API, so when higher-quality clustering is wanted
    this provider is used for embeddings *only* (Claude still does all the LLM
    work). Called over plain ``requests`` to avoid adding the openai SDK; the
    transport is injectable so tests never hit the network.

    On any failure it falls back to the local lexical embedding. The two live in
    different vector spaces / dimensions, so ``cosine`` returns 0.0 across a
    mismatch — a fallback never produces a false "same story" match, it just
    won't cluster until the item is re-embedded.
    """

    ENDPOINT = "https://api.openai.com/v1/embeddings"

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        post_fn: Optional[Callable] = None,
        fallback: Optional["Embedder"] = None,
    ):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI embedder.")
        self._api_key = api_key
        self._model = model
        self._post_fn = post_fn or self._default_post
        self._fallback = fallback or LocalLexicalEmbedder()

    def _default_post(self, url: str, headers: dict, payload: dict):
        import requests

        return requests.post(url, headers=headers, json=payload, timeout=15)

    def embed(self, text: str) -> list[float]:
        text = (text or "").strip()
        if not text:
            return []
        headers = {
            "Authorization": f"Bearer {self._api_key}",  # never logged
            "Content-Type": "application/json",
        }
        try:
            resp = self._post_fn(self.ENDPOINT, headers, {"model": self._model, "input": text})
            status = getattr(resp, "status_code", 200)
            if status != 200:
                raise RuntimeError(f"OpenAI embeddings returned {status}")
            vec = resp.json()["data"][0]["embedding"]
            if not isinstance(vec, list) or not vec:
                raise RuntimeError("OpenAI embeddings returned an empty vector")
            return [float(x) for x in vec]
        except Exception as exc:
            logger.warning("OpenAI embedding failed, using local fallback: %s", exc)
            return self._fallback.embed(text)


def get_embedder(config=None) -> "Embedder":
    """Build the embedder selected by ``EMBEDDING_PROVIDER`` (default: local)."""
    if config is None:
        from src import config as config
    provider = (getattr(config, "EMBEDDING_PROVIDER", "local") or "local").strip().lower()
    if provider == "openai":
        return OpenAIEmbedder(
            api_key=getattr(config, "OPENAI_API_KEY", ""),
            model=getattr(config, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
    return LocalLexicalEmbedder()


def cosine(a: Optional[list[float]], b: Optional[list[float]]) -> float:
    # Different providers (local vs OpenAI) use different dimensions/spaces;
    # a length mismatch means "not comparable" -> 0.0 (never a false match).
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


def ensure_embedding(article, embedder: Embedder, metrics=None) -> list[float]:
    """Compute (and cache on the article) an embedding if absent."""
    if article.embedding:
        return article.embedding
    text = f"{article.normalized_title or article.title}. {article.description}"
    article.embedding = embedder.embed(text)
    if metrics is not None:
        metrics.embedding_calls += 1
    return article.embedding
