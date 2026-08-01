"""
Slack notifier — kept for backwards compatibility.

Renders the channel-agnostic digest dict into Slack Block Kit and posts it via
the existing webhook transport in ``src.notifier``. This lets ``NOTIFIER=slack``
keep working exactly as before while the rest of the pipeline only speaks the
new digest format.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

_MAX_BLOCKS = 48  # Slack allows 50 blocks per message; leave headroom.


def _item_section(item: dict) -> dict:
    title = item.get("title", "").strip()
    url = (item.get("url") or "").strip()
    heading = f"*<{url}|{title}>*" if url else f"*{title}*"

    lines: list[str] = []
    lede = (item.get("lede") or "").strip()
    if item.get("kind") == "update":
        lines.append("🔄 更新")
        if lede:
            lines.append(lede)
        for fact in (item.get("new_facts", []) or []) + (item.get("changed_facts", []) or []):
            if fact:
                lines.append(f"• {fact}")
    else:
        lines.append("🆕 新規")
        if lede:
            lines.append(lede)
        for point in item.get("summary_points", []) or []:
            if point:
                lines.append(f"• {point}")
    why = (item.get("why_it_matters") or "").strip()
    if why:
        lines.append(f"_なぜ重要か:_ {why}")
    src = (item.get("source_name") or "").strip()
    if src:
        lines.append(f"_情報源:_ {src}")

    text = heading + "\n" + "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def build_blocks(digest: dict) -> list[dict]:
    date = (digest.get("date") or "").strip()
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":newspaper:  *Daily News Digest*  ·  {date}"},
        },
        {"type": "divider"},
    ]
    for item in digest.get("items", []):
        blocks.append(_item_section(item))
    return blocks[:_MAX_BLOCKS]


class SlackNotifier:
    """Posts the digest to Slack via Incoming Webhook."""

    def __init__(self, webhook_url: str, post_fn: Callable[[dict], None] | None = None):
        if not webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL is not configured.")
        self._webhook_url = webhook_url
        self._post_fn = post_fn

    def _post(self, payload: dict) -> None:
        if self._post_fn is not None:
            self._post_fn(payload)
            return
        # Import lazily so the module has no hard import-time dependency.
        from src.notifier import post_to_slack

        post_to_slack(payload)

    def send_digest(self, digest: dict) -> None:
        if not digest.get("items"):
            logger.info("Slack: nothing to send (empty digest).")
            return
        self._post({"blocks": build_blocks(digest)})
        logger.info("Slack: sent digest of %d item(s).", len(digest["items"]))

    def send_update(self, update: dict) -> None:
        item = dict(update)
        item.setdefault("kind", "update")
        self.send_digest({"date": update.get("date"), "items": [item]})
