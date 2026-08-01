"""Phase 2 tests: SQLite data-access layer round-trips + dedup key retrieval."""
import unittest
from datetime import datetime, timedelta, timezone

from src.db import Database, sqlite_path_from_url
from src.models import Article, Story, StoryEvent


def _db() -> Database:
    return Database.connect("sqlite:///:memory:")


class SqliteUrlTests(unittest.TestCase):
    def test_relative_path(self):
        self.assertEqual(sqlite_path_from_url("sqlite:///data/news.db"), "data/news.db")

    def test_memory(self):
        self.assertEqual(sqlite_path_from_url("sqlite:///:memory:"), ":memory:")

    def test_postgres_raises(self):
        with self.assertRaises(NotImplementedError):
            Database.connect("postgresql://user@host/db")


class ArticleRoundTripTests(unittest.TestCase):
    def test_insert_and_dedup_keys(self):
        db = _db()
        art = Article(
            title="T", description="D", url="https://e/x", genre="tech",
            guid="g1", canonical_url="https://e/x",
            fingerprint="fp1", embedding=[0.1, 0.2, 0.3],
        )
        aid = db.insert_article(art)
        self.assertIsInstance(aid, int)

        seen = db.seen_dedup_keys()
        self.assertIn("guid:g1", seen)
        self.assertIn("url:https://e/x", seen)
        self.assertIn("fp:fp1", seen)

    def test_embedding_json_roundtrip(self):
        db = _db()
        art = Article("T", "D", "https://e/y", "tech", embedding=[1.0, 2.5])
        db.insert_article(art)
        got = db.recent_articles(datetime.now(timezone.utc) - timedelta(days=1))
        self.assertEqual(got[0].embedding, [1.0, 2.5])

    def test_recent_articles_respects_since(self):
        db = _db()
        old = Article("old", "d", "https://e/old", "tech")
        old.fetched_at = datetime.now(timezone.utc) - timedelta(days=40)
        db.insert_article(old)
        db.insert_article(Article("new", "d", "https://e/new", "tech"))
        recent = db.recent_articles(datetime.now(timezone.utc) - timedelta(days=7))
        titles = {a.title for a in recent}
        self.assertIn("new", titles)
        self.assertNotIn("old", titles)


class StoryRoundTripTests(unittest.TestCase):
    def test_story_and_event_and_delivery(self):
        db = _db()
        story = Story(id=None, current_title="OpenAI model", category="AI",
                      representative_embedding=[0.5, 0.5])
        sid = db.insert_story(story)
        self.assertIsInstance(sid, int)

        event = StoryEvent(
            id=None, story_id=sid, article_id=None, change_type="major_update",
            new_facts=["API launched"], confidence=0.9,
        )
        db.insert_story_event(event)
        events = db.events_for_story(sid)
        self.assertEqual(events[0].new_facts, ["API launched"])
        self.assertEqual(events[0].change_type, "major_update")

        self.assertFalse(db.was_delivered(sid))
        db.record_delivery(story_id=sid, article_id=None,
                           delivery_type="new", channel="discord", status="success")
        self.assertTrue(db.was_delivered(sid))

    def test_recent_stories(self):
        db = _db()
        s = Story(id=None, current_title="X")
        db.insert_story(s)
        got = db.recent_stories(datetime.now(timezone.utc) - timedelta(days=1))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].current_title, "X")


if __name__ == "__main__":
    unittest.main()
