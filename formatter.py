"""
Formatter: converts summarised articles into a Slack Block Kit payload.

Layout per genre:
  [Header]  🗞 Tech  ·  Tue 29 Apr 2025
  [Article] *Title*  <url|link>
             2-sentence summary.
  [Divider]
"""
from __future__ import annotations

from datetime import datetime, timezone
from src.fetcher import Article


_GENRE_EMOJI: dict[str, str] = {
    "tech":    ":computer:",
    "finance": ":chart_with_upwards_trend:",
    "world":   ":earth_asia:",
    "science": ":microscope:",
    "japan":   ":jp:",
    "health":  ":health:",
    "sports":  ":trophy:",
}


def _genre_header(genre: str, date_str: str) -> dict:
    emoji = _GENRE_EMOJI.get(genre, ":newspaper:")
    label = genre.capitalize()
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{emoji}  {label}  ·  {date_str}",
            "emoji": True,
        },
    }


def _article_block(art: Article) -> dict:
    summary = getattr(art, "summary", art.description)
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*<{art.url}|{art.title}>*\n{summary}",
        },
    }


def _divider() -> dict:
    return {"type": "divider"}


def build_payload(
    genre_articles: dict[str, list[Article]],
) -> dict:
    """
    Build the complete Slack Incoming Webhook payload.
    Returns a dict ready to be JSON-serialised and POSTed.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%a %d %b %Y")

    blocks: list[dict] = []

    # Top-level intro
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f":newspaper:  *Daily News Digest*  ·  {date_str}",
        },
    })
    blocks.append(_divider())

    for genre, articles in genre_articles.items():
        if not articles:
            continue
        blocks.append(_genre_header(genre, date_str))
        for art in articles:
            blocks.append(_article_block(art))
        blocks.append(_divider())

    # Footer
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"Powered by Claude Haiku 4.5  ·  "
                    f"Generated {now.strftime('%H:%M UTC')}"
                ),
            }
        ],
    })

    return {"blocks": blocks}
