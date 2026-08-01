"""
News Agent — main entrypoint.

Two jobs (see README):

    python main.py ingest    # fetch → dedup → embed → story linking → persist
    python main.py digest    # rank → diversify → summarise → deliver → record
    python main.py run       # ingest then digest (default; good for local runs)

Environment overrides: GENRES, ARTICLES_PER_GENRE, NOTIFIER, ... (see .env.example)
"""
from __future__ import annotations

import logging
import sys
import time

# Load .env before importing config (config reads env vars at import time).
from src.envfile import load_dotenv

load_dotenv()

from src import config
from src.db import Database
from src.embedding import get_embedder
from src.llm import LLMClient, Metrics
from src.notifiers import get_notifier
from src.pipeline import run_ingest, run_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("news_agent")


def _build_context():
    db = Database.connect(config.DATABASE_URL)
    embedder = get_embedder(config)
    metrics = Metrics()
    llm = LLMClient(
        api_key=config.ANTHROPIC_API_KEY,
        model=config.ANTHROPIC_MODEL,
        metrics=metrics,
    )
    return db, embedder, llm, metrics


def cmd_ingest() -> None:
    config.validate(require_notifier=False)
    db, embedder, llm, metrics = _build_context()
    start = time.time()
    run_ingest(db, embedder, llm, metrics=metrics)
    logger.info("API usage: %s  |  elapsed=%.1fs", metrics.as_dict(), time.time() - start)
    db.close()


def cmd_digest() -> None:
    config.validate(require_notifier=True)
    db, embedder, llm, metrics = _build_context()
    notifier = get_notifier()
    start = time.time()
    try:
        run_digest(db, embedder, llm, notifier, channel_name=config.NOTIFIER, metrics=metrics)
    except RuntimeError as exc:
        logger.error("%s", exc)
        logger.info("API usage: %s  |  elapsed=%.1fs", metrics.as_dict(), time.time() - start)
        db.close()
        sys.exit(1)
    logger.info("API usage: %s  |  elapsed=%.1fs", metrics.as_dict(), time.time() - start)
    db.close()


def cmd_run() -> None:
    """Ingest then digest in a single process (local / all-in-one use)."""
    config.validate(require_notifier=True)
    db, embedder, llm, metrics = _build_context()
    notifier = get_notifier()
    start = time.time()
    run_ingest(db, embedder, llm, metrics=metrics)
    try:
        run_digest(db, embedder, llm, notifier, channel_name=config.NOTIFIER, metrics=metrics)
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    finally:
        logger.info("API usage: %s  |  elapsed=%.1fs", metrics.as_dict(), time.time() - start)
        db.close()


_COMMANDS = {"ingest": cmd_ingest, "digest": cmd_digest, "run": cmd_run}


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    handler = _COMMANDS.get(command)
    if handler is None:
        logger.error("Unknown command '%s'. Use one of: %s", command, ", ".join(_COMMANDS))
        sys.exit(2)
    try:
        handler()
    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
