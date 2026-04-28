"""
Central configuration for the news agent.
All tuneable values live here — no magic numbers elsewhere.
"""
import os

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# Token budget per article fed to the model (title + description truncated).
# Keeps each RSS snippet to ~150 input tokens.
MAX_DESCRIPTION_CHARS = 500

# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------
ARTICLES_PER_GENRE = int(os.getenv("ARTICLES_PER_GENRE", "3"))

# Genres to run — override via env var as comma-separated list
# e.g. GENRES="tech,finance,science"
_genres_env = os.getenv("GENRES", "tech,finance,world")
GENRES: list[str] = [g.strip().lower() for g in _genres_env.split(",") if g.strip()]

# ---------------------------------------------------------------------------
# RSS feeds  (genre → list of feed URLs, tried in order until enough articles)
# ---------------------------------------------------------------------------
FEEDS: dict[str, list[str]] = {
    "tech": [
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ],
    "finance": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
    ],
    "world": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.reuters.com/reuters/worldNews",
    ],
    "science": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "https://www.sciencedaily.com/rss/all.xml",
        "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    ],
    "japan": [
        "https://www3.nhk.or.jp/rss/news/cat0.xml",
        "https://japantoday.com/feed",
        "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
    ],
    "health": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
        "https://feeds.bbci.co.uk/news/health/rss.xml",
    ],
    "sports": [
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
    ],
}

# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Summariser prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are a concise news summariser. For each article provided, write exactly \
2 sentences: one stating the core fact, one giving key context or implication. \
Use plain English. No bullet points. No preamble. No sign-off.\
"""

def validate() -> None:
    """Raise early if required secrets are missing."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not SLACK_WEBHOOK_URL:
        missing.append("SLACK_WEBHOOK_URL")
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
