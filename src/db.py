"""
Data-access layer.

Everything the pipeline knows about SQL lives here so a future move to
PostgreSQL only touches this module. Callers deal in ``Article`` / ``Story`` /
``StoryEvent`` objects, never in rows.

The connection string comes from ``DATABASE_URL`` (default
``sqlite:///data/news.db``). Only the ``sqlite://`` scheme is implemented today;
``postgresql://`` is recognised and raises a clear "not yet implemented" error
so the intent is documented in one place.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

from src.models import Article, Story, StoryEvent

# ── serialisation helpers (shared so JSON fields are handled consistently) ────


def dumps(value) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(text: Optional[str]):
    if text is None or text == "":
        return None
    return json.loads(text)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def sqlite_path_from_url(database_url: str) -> str:
    """Extract a filesystem path from a ``sqlite:///path`` URL.

    ``sqlite:///data/news.db``  -> ``data/news.db`` (relative)
    ``sqlite:////abs/news.db``  -> ``/abs/news.db`` (absolute)
    ``sqlite:///:memory:``      -> ``:memory:``
    """
    if not database_url.startswith("sqlite:"):
        raise ValueError(f"Not a sqlite URL: {database_url}")
    rest = database_url[len("sqlite://"):]
    # rest now starts with '/'. One extra leading slash => absolute path.
    if rest.startswith("/"):
        rest = rest[1:]
    return rest or ":memory:"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT,
    canonical_url TEXT,
    title TEXT,
    normalized_title TEXT,
    source_name TEXT,
    published_at TEXT,
    fetched_at TEXT,
    description TEXT,
    content_hash TEXT,
    fingerprint TEXT,
    embedding TEXT,
    story_id INTEGER,
    language TEXT,
    genre TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_guid ON articles(guid);
CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(canonical_url);
CREATE INDEX IF NOT EXISTS idx_articles_fp ON articles(fingerprint);
CREATE INDEX IF NOT EXISTS idx_articles_story ON articles(story_id);
CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_title TEXT,
    rolling_summary TEXT,
    representative_embedding TEXT,
    first_seen_at TEXT,
    last_updated_at TEXT,
    importance_score REAL,
    category TEXT,
    status TEXT,
    summary_json TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_stories_updated ON stories(last_updated_at);

CREATE TABLE IF NOT EXISTS story_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER,
    article_id INTEGER,
    change_type TEXT,
    new_facts TEXT,
    changed_facts TEXT,
    unchanged_facts TEXT,
    confidence REAL,
    detected_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_story ON story_events(story_id);

CREATE TABLE IF NOT EXISTS delivery_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER,
    article_id INTEGER,
    delivery_type TEXT,
    channel TEXT,
    delivered_at TEXT,
    message_id TEXT,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_delivery_story ON delivery_history(story_id);
"""


class Database:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # -- lifecycle ------------------------------------------------------------
    @classmethod
    def connect(cls, database_url: str) -> "Database":
        if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
            raise NotImplementedError(
                "PostgreSQL backend is not implemented yet. "
                "Use a sqlite:/// URL, or add a psycopg-based Database subclass."
            )
        path = sqlite_path_from_url(database_url)
        if path != ":memory:":
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(path)
        db = cls(conn)
        db.init_schema()
        return db

    def init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Idempotently add columns introduced after a DB was first created."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(stories)")}
        if "summary_json" not in cols:
            self.conn.execute("ALTER TABLE stories ADD COLUMN summary_json TEXT")

    def close(self) -> None:
        self.conn.close()

    # -- articles -------------------------------------------------------------
    def seen_dedup_keys(self, since: Optional[datetime] = None) -> set[str]:
        """Return the set of exact-dedup keys for known articles.

        Keys mirror ``dedup.dedup_keys``: ``guid:``, ``url:``, ``fp:``.
        Optionally limited to articles fetched at/after ``since``.
        """
        sql = "SELECT guid, canonical_url, fingerprint FROM articles"
        params: tuple = ()
        if since is not None:
            sql += " WHERE fetched_at >= ?"
            params = (_iso(since),)
        seen: set[str] = set()
        for row in self.conn.execute(sql, params):
            if row["guid"]:
                seen.add(f"guid:{row['guid']}")
            if row["canonical_url"]:
                seen.add(f"url:{row['canonical_url']}")
            if row["fingerprint"]:
                seen.add(f"fp:{row['fingerprint']}")
        return seen

    def insert_article(self, article: Article) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO articles
              (guid, canonical_url, title, normalized_title, source_name,
               published_at, fetched_at, description, content_hash, fingerprint,
               embedding, story_id, language, genre, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                article.guid,
                article.canonical_url,
                article.title,
                article.normalized_title,
                article.source_name,
                _iso(article.published_at),
                _iso(article.fetched_at),
                article.description,
                article.content_hash,
                article.fingerprint,
                dumps(article.embedding),
                article.story_id,
                article.language,
                article.genre,
                _iso(datetime.now(timezone.utc)),
            ),
        )
        self.conn.commit()
        article.id = cur.lastrowid
        return cur.lastrowid

    def set_article_story(self, article_id: int, story_id: int) -> None:
        self.conn.execute(
            "UPDATE articles SET story_id = ? WHERE id = ?", (story_id, article_id)
        )
        self.conn.commit()

    def recent_articles(self, since: datetime) -> list[Article]:
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE fetched_at >= ? ORDER BY fetched_at DESC",
            (_iso(since),),
        ).fetchall()
        return [self._row_to_article(r) for r in rows]

    @staticmethod
    def _row_to_article(row: sqlite3.Row) -> Article:
        return Article(
            id=row["id"],
            title=row["title"] or "",
            description=row["description"] or "",
            url=row["canonical_url"] or "",
            genre=row["genre"] or "",
            guid=row["guid"] or "",
            canonical_url=row["canonical_url"] or "",
            normalized_title=row["normalized_title"] or "",
            source_name=row["source_name"] or "",
            published_at=_parse_dt(row["published_at"]),
            fetched_at=_parse_dt(row["fetched_at"]) or datetime.now(timezone.utc),
            content_hash=row["content_hash"] or "",
            fingerprint=row["fingerprint"] or "",
            language=row["language"] or "",
            embedding=loads(row["embedding"]),
            story_id=row["story_id"],
        )

    # -- stories --------------------------------------------------------------
    def insert_story(self, story: Story) -> int:
        now = _iso(datetime.now(timezone.utc))
        cur = self.conn.execute(
            """
            INSERT INTO stories
              (current_title, rolling_summary, representative_embedding,
               first_seen_at, last_updated_at, importance_score, category,
               status, summary_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                story.current_title,
                story.rolling_summary,
                dumps(story.representative_embedding),
                _iso(story.first_seen_at),
                _iso(story.last_updated_at),
                story.importance_score,
                story.category,
                story.status,
                dumps(story.summary_json),
                now,
                now,
            ),
        )
        self.conn.commit()
        story.id = cur.lastrowid
        return cur.lastrowid

    def update_story(self, story: Story) -> None:
        self.conn.execute(
            """
            UPDATE stories
               SET current_title = ?, rolling_summary = ?,
                   representative_embedding = ?, last_updated_at = ?,
                   importance_score = ?, category = ?, status = ?,
                   summary_json = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                story.current_title,
                story.rolling_summary,
                dumps(story.representative_embedding),
                _iso(story.last_updated_at),
                story.importance_score,
                story.category,
                story.status,
                dumps(story.summary_json),
                _iso(datetime.now(timezone.utc)),
                story.id,
            ),
        )
        self.conn.commit()

    def recent_stories(self, since: datetime) -> list[Story]:
        rows = self.conn.execute(
            "SELECT * FROM stories WHERE last_updated_at >= ? ORDER BY last_updated_at DESC",
            (_iso(since),),
        ).fetchall()
        return [self._row_to_story(r) for r in rows]

    @staticmethod
    def _row_to_story(row: sqlite3.Row) -> Story:
        return Story(
            id=row["id"],
            current_title=row["current_title"] or "",
            rolling_summary=row["rolling_summary"] or "",
            representative_embedding=loads(row["representative_embedding"]),
            first_seen_at=_parse_dt(row["first_seen_at"]) or datetime.now(timezone.utc),
            last_updated_at=_parse_dt(row["last_updated_at"]) or datetime.now(timezone.utc),
            importance_score=row["importance_score"] or 0.0,
            category=row["category"] or "",
            status=row["status"] or "active",
            summary_json=loads(row["summary_json"]),
        )

    def get_story(self, story_id: int) -> Optional[Story]:
        row = self.conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        return self._row_to_story(row) if row else None

    # -- story events ---------------------------------------------------------
    def insert_story_event(self, event: StoryEvent) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO story_events
              (story_id, article_id, change_type, new_facts, changed_facts,
               unchanged_facts, confidence, detected_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                event.story_id,
                event.article_id,
                event.change_type,
                dumps(event.new_facts),
                dumps(event.changed_facts),
                dumps(event.unchanged_facts),
                event.confidence,
                _iso(event.detected_at),
            ),
        )
        self.conn.commit()
        event.id = cur.lastrowid
        return cur.lastrowid

    def recent_events(self, since: datetime) -> list[StoryEvent]:
        rows = self.conn.execute(
            "SELECT * FROM story_events WHERE detected_at >= ? ORDER BY detected_at",
            (_iso(since),),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def articles_for_story(self, story_id: int) -> list[Article]:
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE story_id = ? ORDER BY fetched_at DESC",
            (story_id,),
        ).fetchall()
        return [self._row_to_article(r) for r in rows]

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> StoryEvent:
        return StoryEvent(
            id=r["id"],
            story_id=r["story_id"],
            article_id=r["article_id"],
            change_type=r["change_type"],
            new_facts=loads(r["new_facts"]) or [],
            changed_facts=loads(r["changed_facts"]) or [],
            unchanged_facts=loads(r["unchanged_facts"]) or [],
            confidence=r["confidence"] or 0.0,
            detected_at=_parse_dt(r["detected_at"]) or datetime.now(timezone.utc),
        )

    def events_for_story(self, story_id: int) -> list[StoryEvent]:
        rows = self.conn.execute(
            "SELECT * FROM story_events WHERE story_id = ? ORDER BY detected_at",
            (story_id,),
        ).fetchall()
        return [
            StoryEvent(
                id=r["id"],
                story_id=r["story_id"],
                article_id=r["article_id"],
                change_type=r["change_type"],
                new_facts=loads(r["new_facts"]) or [],
                changed_facts=loads(r["changed_facts"]) or [],
                unchanged_facts=loads(r["unchanged_facts"]) or [],
                confidence=r["confidence"] or 0.0,
                detected_at=_parse_dt(r["detected_at"]) or datetime.now(timezone.utc),
            )
            for r in rows
        ]

    # -- delivery history -----------------------------------------------------
    def record_delivery(
        self,
        *,
        story_id: Optional[int],
        article_id: Optional[int],
        delivery_type: str,
        channel: str,
        status: str,
        message_id: str = "",
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO delivery_history
              (story_id, article_id, delivery_type, channel, delivered_at,
               message_id, status)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                story_id,
                article_id,
                delivery_type,
                channel,
                _iso(datetime.now(timezone.utc)),
                message_id,
                status,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def was_delivered(self, story_id: int) -> bool:
        return self.last_delivery_at(story_id) is not None

    def last_delivery_at(self, story_id: int) -> Optional[datetime]:
        row = self.conn.execute(
            "SELECT MAX(delivered_at) AS ts FROM delivery_history "
            "WHERE story_id = ? AND status = 'success'",
            (story_id,),
        ).fetchone()
        return _parse_dt(row["ts"]) if row and row["ts"] else None
