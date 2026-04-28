"""
Summarizer: sends all articles in a single Claude Haiku API call.

Token-efficiency strategy:
- One API call per agent run (not one per article).
- Input = numbered list of title + description snippets.
- Output = numbered list of 2-sentence summaries, parsed back to a dict.
- If the model response can't be parsed, falls back to the raw description.
"""
from __future__ import annotations

import logging
import re

import anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    SYSTEM_PROMPT,
)
from src.fetcher import Article

logger = logging.getLogger(__name__)


def _build_user_prompt(articles: list[Article]) -> str:
    """
    Format articles as a numbered list for the model.
    Each item: index, title, and truncated description.
    """
    lines = []
    for i, art in enumerate(articles, start=1):
        lines.append(f"{i}. TITLE: {art.title}")
        if art.description:
            lines.append(f"   DESC: {art.description}")
    return (
        "Summarise each article below in exactly 2 sentences. "
        "Respond with a numbered list matching the input numbering. "
        "Format each item as:\n"
        "N. <two-sentence summary>\n\n"
        + "\n".join(lines)
    )


def _parse_response(text: str, count: int) -> dict[int, str]:
    """
    Parse the model's numbered list into {1-based index: summary}.
    Robust to minor formatting variations.
    """
    summaries: dict[int, str] = {}
    pattern = re.compile(r"^\s*(\d+)\.\s+(.+)", re.MULTILINE)

    current_idx: int | None = None
    current_lines: list[str] = []

    def flush():
        if current_idx is not None and current_lines:
            summaries[current_idx] = " ".join(current_lines).strip()

    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            flush()
            current_idx = int(m.group(1))
            current_lines = [m.group(2).strip()]
        elif current_idx is not None and line.strip():
            current_lines.append(line.strip())

    flush()

    # Fill any gaps with empty string (will fall back to description)
    for i in range(1, count + 1):
        summaries.setdefault(i, "")

    return summaries


def summarize(articles: list[Article]) -> list[Article]:
    """
    Attach a `.summary` attribute to each Article in-place.
    Returns the same list with summaries filled in.
    Falls back to truncated description if API call fails.
    """
    if not articles:
        return articles

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_prompt = _build_user_prompt(articles)

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
        logger.info(
            "Summarizer: %d input tokens, %d output tokens",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        summaries = _parse_response(raw_text, len(articles))

    except Exception as exc:
        logger.error("Anthropic API call failed: %s", exc)
        summaries = {}

    for i, art in enumerate(articles, start=1):
        summary = summaries.get(i, "").strip()
        art.summary = summary if summary else art.description  # type: ignore[attr-defined]

    return articles

