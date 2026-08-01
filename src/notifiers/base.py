"""
Notifier abstraction.

The rest of the pipeline (fetch, rank, summarise) never imports a concrete
channel. It builds a channel-agnostic ``digest`` / ``update`` dict and hands it
to whatever Notifier is configured. This keeps Slack/Discord-specific formatting
and character limits out of the business logic.

Digest dict shape (all fields optional unless noted):

    {
        "date": "Tue 29 Apr 2025",        # display date string
        "generated_at": "04:00 JST",       # optional footer timestamp
        "items": [ <item>, ... ],          # required
    }

A "new" item:

    {
        "kind": "new",                     # required
        "title": str,                      # required
        "summary_points": [str, ...],
        "why_it_matters": str,
        "categories": [str, ...],
        "source_name": str,
        "url": str,
        "score": float | None,             # optional, debug only
    }

An "update" item (also the shape passed to ``send_update``):

    {
        "kind": "update",                  # required
        "title": str,                      # required (story title)
        "new_facts": [str, ...],
        "changed_facts": [str, ...],
        "unchanged_facts": [str, ...],
        "source_name": str,
        "url": str,
    }
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """Common interface every delivery channel implements."""

    def send_digest(self, digest: dict) -> None:
        """Send a full digest (a batch of new/update items)."""
        ...

    def send_update(self, update: dict) -> None:
        """Send a single story update as its own message."""
        ...
