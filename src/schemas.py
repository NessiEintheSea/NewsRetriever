"""
Pydantic models for structured LLM outputs. Each LLM use-case has its own model
so responses are validated (and the model instructs the LLM with an explicit
JSON shape) rather than parsed from free text.

LLMs occasionally return the right data in the wrong JSON *type* — a list where a
string is expected, a string where a list is expected, a numeric id as a string.
``mode="before"`` coercers absorb those so a well-meaning-but-loosely-typed
response validates instead of falling back to a degraded summary.
"""
from __future__ import annotations

import json
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

CHANGE_TYPES = {"new_story", "major_update", "minor_update", "no_meaningful_change"}
SOURCE_TYPES = {"primary", "high_quality", "secondary", "aggregator"}


def _clamp01(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def _as_str(v) -> str:
    """Coerce any JSON value into a string (join lists, stringify scalars)."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return " ".join(_as_str(x) for x in v if x is not None).strip()
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _as_str_list(v) -> List[str]:
    """Coerce any JSON value into a list of non-empty strings."""
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, list):
        out = []
        for x in v:
            s = _as_str(x)
            if s:
                out.append(s)
        return out
    s = _as_str(v)
    return [s] if s else []


def _as_opt_int(v) -> Optional[int]:
    if v is None or v == "" or v == "null":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


class ArticleFacts(BaseModel):
    """Fact extraction + first-report summary for a single article."""

    headline: str = ""
    summary: str = ""
    why_it_matters: str = ""
    key_facts: List[str] = Field(default_factory=list)
    category: str = ""
    entities: List[str] = Field(default_factory=list)
    importance_score: float = 0.0
    source_type: str = "secondary"

    _coerce_str = field_validator(
        "headline", "summary", "why_it_matters", "category", mode="before"
    )(staticmethod(lambda v: _as_str(v)))
    _coerce_list = field_validator("key_facts", "entities", mode="before")(
        staticmethod(lambda v: _as_str_list(v))
    )

    @field_validator("importance_score", mode="before")
    @classmethod
    def _imp(cls, v):
        return _clamp01(v)

    @field_validator("source_type", mode="before")
    @classmethod
    def _src(cls, v):
        v = _as_str(v).lower()
        return v if v in SOURCE_TYPES else "secondary"


class StoryIdentity(BaseModel):
    """LLM's final same-story-or-not judgement."""

    same_story: bool = False
    matched_story_id: Optional[int] = None
    confidence: float = 0.0
    reason: str = ""

    _coerce_id = field_validator("matched_story_id", mode="before")(
        staticmethod(lambda v: _as_opt_int(v))
    )
    _coerce_reason = field_validator("reason", mode="before")(
        staticmethod(lambda v: _as_str(v))
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v):
        return _clamp01(v)


class UpdateDiff(BaseModel):
    """Difference judgement between a new article and an existing story."""

    change_type: str = "no_meaningful_change"
    new_facts: List[str] = Field(default_factory=list)
    changed_facts: List[str] = Field(default_factory=list)
    unchanged_facts: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""

    _coerce_lists = field_validator(
        "new_facts", "changed_facts", "unchanged_facts", mode="before"
    )(staticmethod(lambda v: _as_str_list(v)))
    _coerce_reason = field_validator("reason", mode="before")(
        staticmethod(lambda v: _as_str(v))
    )

    @field_validator("change_type", mode="before")
    @classmethod
    def _ct(cls, v):
        v = _as_str(v).lower()
        return v if v in CHANGE_TYPES else "no_meaningful_change"

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v):
        return _clamp01(v)
