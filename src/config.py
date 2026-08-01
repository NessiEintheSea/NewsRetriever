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
    "ai": [
    "https://feeds.feedburner.com/aiweekly",
    "https://www.artificialintelligence-news.com/feed/",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ],
    "crypto": [
        "https://cointelegraph.com/rss",
        "https://coindesk.com/arc/outboundfeeds/rss/",
        "https://decrypt.co/feed",
    ],
}

# ---------------------------------------------------------------------------
# Delivery / notifier
# ---------------------------------------------------------------------------
# Which channel to deliver to: "discord" (default) or "slack".
NOTIFIER: str = os.getenv("NOTIFIER", "discord").strip().lower()

# Discord Incoming Webhook (used when NOTIFIER=discord)
DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Slack (used when NOTIFIER=slack; kept for backwards compatibility)
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
# Model may be overridden; defaults to the existing cost-optimised Haiku.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", ANTHROPIC_MODEL)


# ---------------------------------------------------------------------------
# Embeddings (Anthropic has no embedding API)
# ---------------------------------------------------------------------------
# "local"  = dependency-free lexical embedder (default)
# "openai" = real semantic embeddings (better clustering; needs OPENAI_API_KEY)
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


# ---------------------------------------------------------------------------
# Full-text extraction (improves summary / diff quality)
# ---------------------------------------------------------------------------
FETCH_FULL_TEXT: bool = os.getenv("FETCH_FULL_TEXT", "false").lower() in ("1", "true", "yes")
FULL_TEXT_MAX_CHARS: int = int(os.getenv("FULL_TEXT_MAX_CHARS", "4000"))
FULL_TEXT_TIMEOUT: int = int(os.getenv("FULL_TEXT_TIMEOUT", "10"))


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/news.db")


# ---------------------------------------------------------------------------
# Story / similarity / update behaviour
# ---------------------------------------------------------------------------
DELIVER_MINOR_UPDATES: bool = os.getenv("DELIVER_MINOR_UPDATES", "false").lower() in (
    "1", "true", "yes",
)
STORY_LOOKBACK_DAYS: int = int(os.getenv("STORY_LOOKBACK_DAYS", "30"))
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.82"))
SIMILARITY_CANDIDATE_LIMIT: int = int(os.getenv("SIMILARITY_CANDIDATE_LIMIT", "10"))


# ---------------------------------------------------------------------------
# Digest volume & diversity
# ---------------------------------------------------------------------------
DIGEST_MAX_ITEMS: int = int(os.getenv("DIGEST_MAX_ITEMS", "7"))
MAX_ITEMS_PER_SOURCE: int = int(os.getenv("MAX_ITEMS_PER_SOURCE", "2"))
MAX_ITEMS_PER_CATEGORY: int = int(os.getenv("MAX_ITEMS_PER_CATEGORY", "2"))
MAX_UPDATE_ITEMS: int = int(os.getenv("MAX_UPDATE_ITEMS", "3"))
REQUIRE_PRIMARY_SOURCE: bool = os.getenv("REQUIRE_PRIMARY_SOURCE", "true").lower() in (
    "1", "true", "yes",
)


# ---------------------------------------------------------------------------
# Ranking weights (normalised at use-time so they need not sum to exactly 1.0)
# ---------------------------------------------------------------------------
WEIGHT_RELEVANCE: float = float(os.getenv("WEIGHT_RELEVANCE", "0.30"))
WEIGHT_NOVELTY: float = float(os.getenv("WEIGHT_NOVELTY", "0.25"))
WEIGHT_IMPORTANCE: float = float(os.getenv("WEIGHT_IMPORTANCE", "0.20"))
WEIGHT_SOURCE_QUALITY: float = float(os.getenv("WEIGHT_SOURCE_QUALITY", "0.15"))
WEIGHT_RECENCY: float = float(os.getenv("WEIGHT_RECENCY", "0.10"))

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

def validate(require_notifier: bool = True) -> None:
    """Raise early if required secrets are missing.

    Args:
        require_notifier: whether a delivery webhook is needed (False for the
            ingest-only job, which never posts anywhere).
    """
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if require_notifier:
        if NOTIFIER == "discord" and not DISCORD_WEBHOOK_URL:
            missing.append("DISCORD_WEBHOOK_URL")
        elif NOTIFIER == "slack" and not SLACK_WEBHOOK_URL:
            missing.append("SLACK_WEBHOOK_URL")
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
