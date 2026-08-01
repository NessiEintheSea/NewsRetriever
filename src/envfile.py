"""
Minimal ``.env`` loader (stdlib only — no python-dotenv dependency).

Loads KEY=VALUE lines from a ``.env`` file into ``os.environ`` without
overriding variables that are already set (so real environment / CI secrets
always win over the file). Call this *before* importing ``src.config``, which
reads env vars at import time.
"""
from __future__ import annotations

import os


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass
