"""Phase 4 tests: source quality, multi-factor ranking, diversity/MMR."""
import unittest

from src.source_quality import classify_source, quality_score, is_primary
from src.ranking import Candidate, score_candidate, rank
from src.diversity import select


WEIGHTS = {
    "WEIGHT_RELEVANCE": 0.30,
    "WEIGHT_NOVELTY": 0.25,
    "WEIGHT_IMPORTANCE": 0.20,
    "WEIGHT_SOURCE_QUALITY": 0.15,
    "WEIGHT_RECENCY": 0.10,
}
INTERESTS = {"ai", "tech", "crypto"}


def _cand(story_id, kind="new", change_type="new_story", source="a.com",
          category="AI", tier="secondary", importance=0.5, age=1.0,
          embedding=None, title="OpenAI ships AI model"):
    return Candidate(
        story_id=story_id, kind=kind, change_type=change_type, title=title,
        url=f"https://{source}/x", source_name=source, category=category,
        tier=tier, is_primary=(tier == "primary"), importance=importance,
        age_hours=age, embedding=embedding or [1.0, 0.0],
    )


class SourceQualityTests(unittest.TestCase):
    def test_primary_hosts_and_suffixes(self):
        self.assertEqual(classify_source("https://openai.com/blog/x"), "primary")
        self.assertEqual(classify_source("https://www.mext.go.jp/a"), "primary")

    def test_high_quality(self):
        self.assertEqual(classify_source("https://feeds.reuters.com/x"), "high_quality")

    def test_aggregator(self):
        self.assertEqual(classify_source("https://cointelegraph.com/x"), "aggregator")

    def test_llm_fallback(self):
        self.assertEqual(classify_source("https://unknown-blog.example/x", "primary"), "primary")

    def test_scores_ordered(self):
        self.assertGreater(quality_score("primary"), quality_score("aggregator"))
        self.assertTrue(is_primary("primary"))


class RankingTests(unittest.TestCase):
    def test_breakdown_has_all_factors(self):
        c = score_candidate(_cand(1), WEIGHTS, INTERESTS)
        for k in ("relevance", "novelty", "importance", "source_quality", "recency", "final"):
            self.assertIn(k, c.breakdown)
        self.assertGreaterEqual(c.score, 0.0)
        self.assertLessEqual(c.score, 1.0)

    def test_primary_recent_outranks_old_aggregator(self):
        strong = _cand(1, tier="primary", importance=0.9, age=1.0)
        weak = _cand(2, tier="aggregator", importance=0.2, age=47.0, change_type="minor_update", kind="update")
        ranked = rank([weak, strong], WEIGHTS, INTERESTS)
        self.assertEqual(ranked[0].story_id, 1)

    def test_weights_normalised(self):
        # Non-normalised weights should still yield a score in [0,1].
        c = score_candidate(_cand(1), {k: v * 10 for k, v in WEIGHTS.items()}, INTERESTS)
        self.assertLessEqual(c.score, 1.0001)


class DiversityTests(unittest.TestCase):
    def _scored(self, cands):
        return rank(cands, WEIGHTS, INTERESTS)

    def test_max_items(self):
        cands = self._scored([_cand(i, source=f"s{i}.com", category=f"c{i}") for i in range(10)])
        out = select(cands, max_items=3, max_per_source=2, max_per_category=2,
                     max_updates=3, require_primary=False)
        self.assertEqual(len(out), 3)

    def test_max_per_source(self):
        cands = self._scored([_cand(i, source="same.com", category=f"c{i}") for i in range(5)])
        out = select(cands, max_items=7, max_per_source=2, max_per_category=5,
                     max_updates=3, require_primary=False)
        self.assertLessEqual(sum(1 for c in out if c.source_name == "same.com"), 2)

    def test_max_per_category(self):
        cands = self._scored([_cand(i, source=f"s{i}.com", category="AI") for i in range(5)])
        out = select(cands, max_items=7, max_per_source=5, max_per_category=2,
                     max_updates=3, require_primary=False)
        self.assertLessEqual(sum(1 for c in out if c.category == "AI"), 2)

    def test_max_updates(self):
        cands = self._scored([
            _cand(i, kind="update", change_type="major_update", source=f"s{i}.com", category=f"c{i}")
            for i in range(6)
        ])
        out = select(cands, max_items=7, max_per_source=5, max_per_category=5,
                     max_updates=2, require_primary=False)
        self.assertLessEqual(sum(1 for c in out if c.kind == "update"), 2)

    def test_one_per_story(self):
        cands = self._scored([_cand(1, source=f"s{i}.com", category=f"c{i}") for i in range(3)])
        out = select(cands, max_items=7, max_per_source=5, max_per_category=5,
                     max_updates=3, require_primary=False)
        self.assertEqual(len(out), 1)

    def test_require_primary_promotes_primary(self):
        cands = self._scored([
            _cand(1, source="s1.com", category="c1", tier="secondary", importance=0.9),
            _cand(2, source="s2.com", category="c2", tier="secondary", importance=0.85),
            _cand(3, source="openai.com", category="c3", tier="primary", importance=0.4),
        ])
        out = select(cands, max_items=2, max_per_source=2, max_per_category=2,
                     max_updates=3, require_primary=True)
        self.assertTrue(any(c.is_primary for c in out))

    def test_require_primary_relaxes_when_none(self):
        cands = self._scored([_cand(i, source=f"s{i}.com", category=f"c{i}", tier="secondary") for i in range(3)])
        out = select(cands, max_items=2, max_per_source=2, max_per_category=2,
                     max_updates=3, require_primary=True)
        self.assertEqual(len(out), 2)  # no error, just no primary

    def test_mmr_prefers_diverse(self):
        # Two identical-embedding high scorers + one distinct; MMR should include the distinct one.
        a = _cand(1, source="s1.com", category="c1", importance=0.9, embedding=[1.0, 0.0])
        b = _cand(2, source="s2.com", category="c2", importance=0.88, embedding=[1.0, 0.0])
        c = _cand(3, source="s3.com", category="c3", importance=0.6, embedding=[0.0, 1.0])
        out = select(self._scored([a, b, c]), max_items=2, max_per_source=5,
                     max_per_category=5, max_updates=3, require_primary=False)
        ids = {x.story_id for x in out}
        self.assertIn(3, ids)  # the diverse one made it in


if __name__ == "__main__":
    unittest.main()
