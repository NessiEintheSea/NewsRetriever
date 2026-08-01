"""Phase 5: end-to-end pipeline integration test (all external calls mocked)."""
import re
import time
import unittest

import src.fetcher as fetcher_mod
from src import pipeline, config
from src.db import Database
from src.embedding import LocalLexicalEmbedder
from src.llm import LLMClient, Metrics
from src.models import Article
from src.normalize import normalize_url, normalize_title
from src.dedup import fingerprint, content_hash


EMB = LocalLexicalEmbedder()


def _mk(title, desc, url, genre="ai"):
    canonical = normalize_url(url)
    return Article(
        title=title, description=desc, url=canonical, genre=genre,
        guid=url, canonical_url=canonical, normalized_title=normalize_title(title),
        source_name=re.sub(r"^https?://", "", url).split("/")[0],
        content_hash=content_hash(desc), fingerprint=fingerprint(title, desc),
    )


def fake_generate_factory(*, match_openai=False, diff_change="major_update"):
    def gen(system, user, max_tokens):
        if "同一の出来事" in system:
            if match_openai and "OpenAI" in user:
                m = re.search(r"story_id=(\d+)", user)
                sid = m.group(1) if m else "null"
                return (f'{{"same_story": true, "matched_story_id": {sid}, "confidence": 0.95, "reason": "s"}}', 8, 4)
            return ('{"same_story": false, "matched_story_id": null, "confidence": 0.9, "reason": "diff"}', 8, 4)
        if "change_type" in system:
            return (f'{{"change_type": "{diff_change}", "new_facts": ["API launched"], "changed_facts": [], "unchanged_facts": [], "confidence": 0.9, "reason": "r"}}', 8, 4)
        return ('{"summary": "sum", "why_it_matters": "why", "key_facts": ["fact one", "fact two"], "category": "AI", "entities": ["x"], "importance_score": 0.8, "source_type": "high_quality"}', 8, 4)
    return gen


class FakeNotifier:
    def __init__(self):
        self.digests = []
        self.fail = False

    def send_digest(self, digest):
        if self.fail:
            raise RuntimeError("boom")
        self.digests.append(digest)

    def send_update(self, update):
        self.digests.append({"items": [update]})


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._orig_fetch = fetcher_mod.fetch_all
        self.db = Database.connect("sqlite:///:memory:")

    def tearDown(self):
        fetcher_mod.fetch_all = self._orig_fetch

    def _patch_fetch(self, articles_by_genre):
        fetcher_mod.fetch_all = lambda genres, keep=None: articles_by_genre

    def test_full_cycle_new_then_update(self):
        # ── Cycle 1: two brand-new stories ───────────────────────────────────
        self._patch_fetch({
            "ai": [_mk("OpenAI announces new model", "OpenAI unveiled a model today.", "https://openai.com/a")],
            "crypto": [_mk("Bitcoin hits new high", "Bitcoin surged past a record price.", "https://cointelegraph.com/b", "crypto")],
        })
        llm = LLMClient(generate_fn=fake_generate_factory(match_openai=True))
        stats1 = pipeline.run_ingest(self.db, EMB, llm, metrics=Metrics())
        self.assertEqual(stats1.new_stories, 2)
        self.assertEqual(stats1.exact_dups, 0)

        notifier = FakeNotifier()
        digest1, dstats1 = pipeline.run_digest(self.db, EMB, llm, notifier, since_hours=24)
        self.assertEqual(len(notifier.digests), 1)
        self.assertEqual(len(digest1["items"]), 2)
        self.assertTrue(all(i["kind"] == "new" for i in digest1["items"]))
        # facts came from cache (no re-summarise call needed at digest time)
        self.assertIn("fact one", digest1["items"][0]["summary_points"])
        self.assertEqual(dstats1.delivered, 2)

        time.sleep(0.02)  # ensure the update timestamp is strictly after delivery

        # ── Cycle 2: a follow-up that updates the OpenAI story ────────────────
        self._patch_fetch({
            "ai": [_mk("OpenAI announces new model, now with API access and pricing",
                       "OpenAI launched API access and pricing today.", "https://openai.com/c")],
        })
        stats2 = pipeline.run_ingest(self.db, EMB, llm, metrics=Metrics())
        self.assertEqual(stats2.major_updates, 1)
        self.assertEqual(stats2.new_stories, 0)

        notifier2 = FakeNotifier()
        digest2, dstats2 = pipeline.run_digest(self.db, EMB, llm, notifier2, since_hours=24)
        # Only the OpenAI story delivers, as a delta update.
        self.assertEqual(len(digest2["items"]), 1)
        self.assertEqual(digest2["items"][0]["kind"], "update")
        # new_facts are now the delivery-time polished facts (non-empty), and a
        # readable lede is generated for the update.
        self.assertTrue(digest2["items"][0]["new_facts"])
        self.assertTrue(digest2["items"][0].get("lede"))
        self.assertGreaterEqual(dstats2.skipped_already_delivered, 1)

    def test_exact_duplicate_not_reprocessed(self):
        art = _mk("Same story", "Same body text here.", "https://openai.com/dup")
        self._patch_fetch({"ai": [art]})
        llm = LLMClient(generate_fn=fake_generate_factory())
        pipeline.run_ingest(self.db, EMB, llm, metrics=Metrics())
        # Re-ingest the identical article -> should be an exact dup, no LLM call.
        self._patch_fetch({"ai": [_mk("Same story", "Same body text here.", "https://openai.com/dup")]})
        llm2 = LLMClient(generate_fn=fake_generate_factory())
        stats = pipeline.run_ingest(self.db, EMB, llm2, metrics=llm2.metrics)
        self.assertEqual(stats.exact_dups, 1)
        self.assertEqual(stats.processed, 0)
        self.assertEqual(llm2.metrics.llm_calls, 0)  # cost saved

    def test_delivery_failure_records_failed_status(self):
        self._patch_fetch({"ai": [_mk("A story", "Body.", "https://openai.com/x")]})
        llm = LLMClient(generate_fn=fake_generate_factory())
        pipeline.run_ingest(self.db, EMB, llm, metrics=Metrics())
        notifier = FakeNotifier()
        notifier.fail = True
        with self.assertRaises(RuntimeError):
            pipeline.run_digest(self.db, EMB, llm, notifier, since_hours=24)
        # A failed delivery must be recorded (not silently lost).
        row = self.db.conn.execute(
            "SELECT status FROM delivery_history WHERE status='failed'"
        ).fetchone()
        self.assertIsNotNone(row)


class MinorGatingTests(unittest.TestCase):
    def test_minor_update_gated_by_config(self):
        db = Database.connect("sqlite:///:memory:")
        llm = LLMClient(generate_fn=fake_generate_factory(match_openai=True, diff_change="minor_update"))
        import src.fetcher as fm
        orig = fm.fetch_all
        try:
            fm.fetch_all = lambda g, keep=None: {
                "ai": [_mk("OpenAI model", "OpenAI unveiled a model.", "https://openai.com/a")]
            }
            pipeline.run_ingest(db, EMB, llm, metrics=Metrics())
            n = FakeNotifier()
            pipeline.run_digest(db, EMB, llm, n, since_hours=24)  # delivers as new
            time.sleep(0.02)
            fm.fetch_all = lambda g, keep=None: {
                "ai": [_mk("OpenAI model minor tweak", "OpenAI added a small clarification.", "https://openai.com/d")]
            }
            pipeline.run_ingest(db, EMB, llm, metrics=Metrics())

            old = config.DELIVER_MINOR_UPDATES
            config.DELIVER_MINOR_UPDATES = False
            try:
                n2 = FakeNotifier()
                digest, stats = pipeline.run_digest(db, EMB, llm, n2, since_hours=24)
                self.assertEqual(len(digest["items"]), 0)
                self.assertGreaterEqual(stats.skipped_minor, 1)
            finally:
                config.DELIVER_MINOR_UPDATES = old
        finally:
            fm.fetch_all = orig


if __name__ == "__main__":
    unittest.main()
