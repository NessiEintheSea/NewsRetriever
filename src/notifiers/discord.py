"""
Discord notifier — posts digests/updates to a Discord Incoming Webhook using
rich embeds.

Design notes
------------
* Webhook only for now. The public surface (``send_digest`` / ``send_update``)
  is Bot-agnostic, so switching to a Bot later only touches ``_post``.
* Discord enforces hard limits; we split safely rather than get a 400:
    - content:            2000 chars
    - embed title:         256 chars
    - embed description:  4096 chars
    - embeds per message:   10
    - total chars/message: 6000 (summed across a message's embeds)
* The webhook URL is a secret and is never logged.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable

import requests

logger = logging.getLogger(__name__)

# ── Discord hard limits ──────────────────────────────────────────────────────
MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_EMBEDS_PER_MESSAGE = 10
MAX_TOTAL_CHARS_PER_MESSAGE = 6000

_TIMEOUT_SECONDS = 10

# Colours (decimal) for the accent bar.
_COLOR_NEW = 0x2ECC71     # green
_COLOR_UPDATE = 0x3498DB  # blue


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _split_text(text: str, limit: int) -> list[str]:
    """Split ``text`` into chunks each <= ``limit``, preferring line breaks."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _new_item_description(item: dict) -> str:
    parts: list[str] = []
    lede = (item.get("lede") or "").strip()
    if lede:
        parts.append(lede + "\n")
    block = _points_block("📌 ポイント", item.get("summary_points", []))
    if block:
        parts.append(block)
    why = (item.get("why_it_matters") or "").strip()
    if why:
        parts.append(f"**💡 なぜ重要か**\n{why}\n")
    cats = [c for c in (item.get("categories") or []) if c]
    tag = f"🏷 {' / '.join(cats)}" if cats else ""
    src = _source_line(item)
    footer = "　".join([x for x in (tag, src) if x])
    if footer:
        parts.append(footer)
    return "\n".join(parts).strip()


def _update_item_description(item: dict) -> str:
    parts: list[str] = []
    lede = (item.get("lede") or "").strip()
    if lede:
        parts.append(lede + "\n")
    block = _points_block("🆕 前回からの変更", item.get("new_facts", []))
    if block:
        parts.append(block)
    changed = _points_block("✏️ 変更された内容", item.get("changed_facts", []))
    if changed:
        parts.append(changed)
    why = (item.get("why_it_matters") or "").strip()
    if why:
        parts.append(f"**💡 なぜ重要か**\n{why}\n")
    src = _source_line(item)
    if src:
        parts.append(src)
    return "\n".join(p for p in parts if p).strip()


def _points_block(header: str, points: list[str]) -> str:
    points = [p for p in (points or []) if p and p.strip()]
    if not points:
        return ""
    lines = "\n".join(f"・{p.strip()}" for p in points)
    return f"**{header}**\n{lines}\n"


def _source_line(item: dict) -> str:
    name = (item.get("source_name") or "").strip()
    url = (item.get("url") or "").strip()
    if name and url:
        return f"📰 [{name}]({url})"
    if url:
        return f"📰 {url}"
    return ""


def build_embeds(digest: dict) -> list[dict]:
    """Convert a channel-agnostic digest dict into a list of Discord embeds.

    Each item becomes one embed. Over-long descriptions are split into
    continuation embeds so nothing exceeds Discord's per-embed limit.
    """
    embeds: list[dict] = []
    for item in digest.get("items", []):
        kind = item.get("kind", "new")
        if kind == "update":
            emoji, color = "🔄 更新", _COLOR_UPDATE
            description = _update_item_description(item)
        else:
            emoji, color = "🆕 新規", _COLOR_NEW
            description = _new_item_description(item)

        title = _truncate(f"{emoji}  {item.get('title', '').strip()}", MAX_TITLE)
        chunks = _split_text(description, MAX_DESCRIPTION) or [""]
        for idx, chunk in enumerate(chunks):
            embeds.append(
                {
                    "title": title if idx == 0 else _truncate(f"{title} (続き)", MAX_TITLE),
                    "description": chunk,
                    "color": color,
                }
            )
    return embeds


def _chunk_embeds(embeds: list[dict]) -> list[list[dict]]:
    """Group embeds into per-message batches respecting count + char limits."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    for embed in embeds:
        size = len(embed.get("title", "")) + len(embed.get("description", ""))
        too_many = len(current) >= MAX_EMBEDS_PER_MESSAGE
        too_big = current and current_chars + size > MAX_TOTAL_CHARS_PER_MESSAGE
        if too_many or too_big:
            batches.append(current)
            current, current_chars = [], 0
        current.append(embed)
        current_chars += size
    if current:
        batches.append(current)
    return batches


class DiscordNotifier:
    """Posts to a Discord Incoming Webhook.

    ``post_fn`` is injectable so tests never touch the network.
    """

    def __init__(self, webhook_url: str, post_fn: Callable[[str, dict], object] | None = None):
        if not webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL is not configured.")
        self._webhook_url = webhook_url
        self._post_fn = post_fn or self._default_post

    # -- transport ------------------------------------------------------------
    @staticmethod
    def _default_post(url: str, payload: dict):
        return requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT_SECONDS,
        )

    def _send_payload(self, payload: dict) -> None:
        response = self._post_fn(self._webhook_url, payload)
        status = getattr(response, "status_code", 204)
        if status not in (200, 204):
            text = getattr(response, "text", "")
            # Never include the webhook URL in the message.
            raise RuntimeError(f"Discord webhook returned {status}: {text}")

    # -- public API -----------------------------------------------------------
    def send_digest(self, digest: dict) -> None:
        embeds = build_embeds(digest)
        if not embeds:
            logger.info("Discord: nothing to send (empty digest).")
            return

        header = self._header_content(digest)
        batches = _chunk_embeds(embeds)
        for i, batch in enumerate(batches):
            payload: dict = {"embeds": batch}
            if i == 0 and header:
                payload["content"] = _truncate(header, 2000)
            self._send_payload(payload)
            if i < len(batches) - 1:
                time.sleep(0.4)  # be gentle with the webhook rate limit
        logger.info(
            "Discord: sent digest of %d item(s) in %d message(s).",
            len(digest.get("items", [])),
            len(batches),
        )

    def send_update(self, update: dict) -> None:
        item = dict(update)
        item.setdefault("kind", "update")
        self.send_digest({"date": update.get("date"), "items": [item]})

    @staticmethod
    def _header_content(digest: dict) -> str:
        date = (digest.get("date") or "").strip()
        generated = (digest.get("generated_at") or "").strip()
        bits = ["🗞 **Daily News Digest**"]
        if date:
            bits.append(f"· {date}")
        line = "  ".join(bits)
        if generated:
            line += f"\n_generated {generated}_"
        return line
