"""
Notifier: sends the formatted payload to Slack via Incoming Webhook.
Uses only the `requests` library — no Slack SDK dependency.
"""
from __future__ import annotations

import json
import logging

import requests

from src.config import SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10


def post_to_slack(payload: dict) -> None:
    """
    POST `payload` as JSON to the configured Slack webhook.
    Raises RuntimeError on any failure so the caller can handle it.
    """
    if not SLACK_WEBHOOK_URL:
        raise RuntimeError("SLACK_WEBHOOK_URL is not configured.")

    response = requests.post(
        SLACK_WEBHOOK_URL,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Slack webhook returned {response.status_code}: {response.text}"
        )

    logger.info("Slack notification sent successfully.")

