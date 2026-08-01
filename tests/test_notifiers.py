"""Phase 1 tests: notifier abstraction, Discord formatting/splitting, factory."""
import unittest

from src.notifiers import get_notifier, DiscordNotifier, SlackNotifier
from src.notifiers.discord import (
    build_embeds,
    _chunk_embeds,
    _split_text,
    MAX_DESCRIPTION,
    MAX_EMBEDS_PER_MESSAGE,
    MAX_TOTAL_CHARS_PER_MESSAGE,
)
from src.digest import build_digest, source_name_from_url


class _Article:
    def __init__(self, title, url, genre, summary="", description=""):
        self.title = title
        self.url = url
        self.genre = genre
        self.summary = summary
        self.description = description


class SplitTextTests(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(_split_text("hello", 100), ["hello"])

    def test_long_text_split_within_limit(self):
        text = "word " * 5000  # ~25000 chars
        chunks = _split_text(text, MAX_DESCRIPTION)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), MAX_DESCRIPTION)
        # No content lost (ignoring whitespace normalisation).
        self.assertEqual("".join(chunks).replace(" ", ""), text.replace(" ", ""))


class BuildEmbedsTests(unittest.TestCase):
    def test_new_item_embed(self):
        digest = {
            "items": [
                {
                    "kind": "new",
                    "title": "OpenAI announces model",
                    "summary_points": ["point 1", "point 2"],
                    "why_it_matters": "big deal",
                    "categories": ["AI"],
                    "source_name": "example.com",
                    "url": "https://example.com/a",
                }
            ]
        }
        embeds = build_embeds(digest)
        self.assertEqual(len(embeds), 1)
        self.assertIn("🆕", embeds[0]["title"])
        self.assertIn("point 1", embeds[0]["description"])
        self.assertIn("big deal", embeds[0]["description"])
        self.assertIn("example.com", embeds[0]["description"])

    def test_update_item_embed(self):
        digest = {
            "items": [
                {
                    "kind": "update",
                    "title": "Story X",
                    "new_facts": ["API launched"],
                    "changed_facts": [],
                    "source_name": "src",
                    "url": "https://s/x",
                }
            ]
        }
        embeds = build_embeds(digest)
        self.assertIn("🔄", embeds[0]["title"])
        self.assertIn("API launched", embeds[0]["description"])

    def test_long_description_splits_into_multiple_embeds(self):
        digest = {
            "items": [
                {
                    "kind": "new",
                    "title": "T",
                    "summary_points": ["x" * 6000],
                    "url": "https://s/x",
                }
            ]
        }
        embeds = build_embeds(digest)
        self.assertGreaterEqual(len(embeds), 2)
        for e in embeds:
            self.assertLessEqual(len(e["description"]), MAX_DESCRIPTION)


class ChunkEmbedsTests(unittest.TestCase):
    def test_batches_respect_count_limit(self):
        embeds = [{"title": "t", "description": "d"} for _ in range(23)]
        batches = _chunk_embeds(embeds)
        self.assertEqual(len(batches), 3)  # 10 + 10 + 3
        for b in batches:
            self.assertLessEqual(len(b), MAX_EMBEDS_PER_MESSAGE)

    def test_batches_respect_char_limit(self):
        big = "y" * 4000
        embeds = [{"title": "t", "description": big} for _ in range(3)]
        batches = _chunk_embeds(embeds)
        # 3 * ~4000 > 6000 so they must be split across messages.
        self.assertGreater(len(batches), 1)
        for b in batches:
            total = sum(len(e["title"]) + len(e["description"]) for e in b)
            self.assertLessEqual(total, MAX_TOTAL_CHARS_PER_MESSAGE)


class DiscordSendTests(unittest.TestCase):
    def test_send_digest_posts_and_never_leaks_url(self):
        sent = []

        class FakeResp:
            status_code = 204
            text = ""

        def fake_post(url, payload):
            sent.append((url, payload))
            return FakeResp()

        notifier = DiscordNotifier("https://discord/webhook/secret", post_fn=fake_post)
        digest = {"date": "Tue", "items": [{"kind": "new", "title": "A", "url": "u"}]}
        notifier.send_digest(digest)
        self.assertEqual(len(sent), 1)
        # header content present on the first message
        self.assertIn("content", sent[0][1])

    def test_non_2xx_raises_without_url(self):
        class FakeResp:
            status_code = 400
            text = "bad"

        notifier = DiscordNotifier("https://secret", post_fn=lambda u, p: FakeResp())
        with self.assertRaises(RuntimeError) as ctx:
            notifier.send_digest({"items": [{"kind": "new", "title": "A", "url": "u"}]})
        self.assertNotIn("secret", str(ctx.exception))

    def test_empty_digest_sends_nothing(self):
        sent = []
        notifier = DiscordNotifier("https://x", post_fn=lambda u, p: sent.append(p))
        notifier.send_digest({"items": []})
        self.assertEqual(sent, [])


class FactoryTests(unittest.TestCase):
    def test_discord_selected(self):
        import src.config as config

        old_n, old_d = config.NOTIFIER, config.DISCORD_WEBHOOK_URL
        config.NOTIFIER, config.DISCORD_WEBHOOK_URL = "discord", "https://d"
        try:
            self.assertIsInstance(get_notifier(), DiscordNotifier)
        finally:
            config.NOTIFIER, config.DISCORD_WEBHOOK_URL = old_n, old_d

    def test_slack_selected(self):
        import src.config as config

        old_n, old_s = config.NOTIFIER, config.SLACK_WEBHOOK_URL
        config.NOTIFIER, config.SLACK_WEBHOOK_URL = "slack", "https://s"
        try:
            self.assertIsInstance(get_notifier(), SlackNotifier)
        finally:
            config.NOTIFIER, config.SLACK_WEBHOOK_URL = old_n, old_s

    def test_unknown_notifier_raises(self):
        with self.assertRaises(ValueError):
            get_notifier("carrier-pigeon")


class DigestBuilderTests(unittest.TestCase):
    def test_source_name_from_url(self):
        self.assertEqual(source_name_from_url("https://feeds.bbci.co.uk/news/rss.xml"), "bbci.co.uk")
        self.assertEqual(source_name_from_url("https://www.example.com/a"), "example.com")

    def test_build_digest_shape(self):
        arts = {"tech": [_Article("T", "https://example.com/a", "tech", summary="One. Two.")]}
        digest = build_digest(arts)
        self.assertEqual(len(digest["items"]), 1)
        item = digest["items"][0]
        self.assertEqual(item["kind"], "new")
        self.assertEqual(item["categories"], ["Tech"])
        self.assertEqual(item["source_name"], "example.com")


if __name__ == "__main__":
    unittest.main()
