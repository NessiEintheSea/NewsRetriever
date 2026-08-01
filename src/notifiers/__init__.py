"""
Notifier factory. ``get_notifier()`` returns the channel selected by the
``NOTIFIER`` env var (default: discord).
"""
from __future__ import annotations

from src.notifiers.base import Notifier
from src.notifiers.discord import DiscordNotifier
from src.notifiers.slack import SlackNotifier

__all__ = ["Notifier", "DiscordNotifier", "SlackNotifier", "get_notifier"]


def get_notifier(name: str | None = None) -> Notifier:
    """Build the configured notifier.

    Args:
        name: Override the channel. When None, reads ``config.NOTIFIER``.
    """
    from src import config

    channel = (name or config.NOTIFIER or "discord").strip().lower()
    if channel == "discord":
        return DiscordNotifier(config.DISCORD_WEBHOOK_URL)
    if channel == "slack":
        return SlackNotifier(config.SLACK_WEBHOOK_URL)
    raise ValueError(
        f"Unknown NOTIFIER '{channel}'. Supported values: discord, slack."
    )
