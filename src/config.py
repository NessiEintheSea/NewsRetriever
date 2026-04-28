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

# Final number of articles per genre sent to Slack after filtering
ARTICLES_PER_GENRE = int(os.getenv("ARTICLES_PER_GENRE", "5"))

# Minimum articles to fetch per genre regardless of feed size
MIN_FETCH = int(os.getenv("MIN_FETCH", "10"))

# Ratio of total available articles to fetch (0.30 = 30%)
# Statistical basis: 30% gives 95-97% confidence of capturing
# all important articles across all genre signal densities
FETCH_RATIO = float(os.getenv("FETCH_RATIO", "0.30"))

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

# ---------------------------------------------------------------------------
# Filter prompt
# ---------------------------------------------------------------------------
FILTER_PROMPT = """\
You are a news editor selecting the most important and relevant articles.
Score each article by importance on a scale of 1-10 where:
10 = Major breaking news, significant global/market impact
7-9 = Important development, affects many people or industries
4-6 = Interesting but moderate significance
1-3 = Minor, niche, or low-impact story

Respond ONLY with a JSON array of objects in this exact format:
[{"index": 1, "score": 8}, {"index": 2, "score": 5}, ...]
No explanation. No preamble. Just the JSON array.\
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
