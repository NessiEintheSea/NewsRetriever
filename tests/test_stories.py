"""Phase 3 tests: embeddings, similarity, structured LLM, story linking."""
import re
import unittest
from datetime import datetime, timezone

from src.db import Database
from src.embedding import LocalLexicalEmbedder, cosine, ensure_embedding
from src.similarity import extract_entities, find_candidates
from src.llm import LLMClient, _extract_json
from src.schemas import ArticleFacts, StoryIdentity, UpdateDiff
from src.models import Article, Story
from src import stories


EMB = LocalLexicalEmbedder()


def _article(title, desc, genre="ai"):
    a = Article(title=title, description=desc, url="https://e/" + re.sub(r"\W+", "", title),
                genre=genre, normalized_title=title)
    return a


# ── Fake LLM generation routing ──────────────────────────────────────────────
def make_fake_generate(*, match: bool, change_type: str = "major_update"):
    def gen(system: str, user: str, max_tokens: int):
        if "same_story" in system or "同一の出来事" in system:
            if match:
                m = re.search(r"story_id=(\d+)", user)
                sid = m.group(1) if m else "null"
                return (f'{{"same_story": true, "matched_story_id": {sid}, "confidence": 0.95, "reason": "same"}}', 10, 5)
            return ('{"same_story": false, "matched_story_id": null, "confidence": 0.9, "reason": "different org"}', 10, 5)
        if "change_type" in system:
            return (f'{{"change_type": "{change_type}", "new_facts": ["API launched"], "changed_facts": [], "unchanged_facts": [], "confidence": 0.9, "reason": "r"}}', 10, 5)
        # facts extraction
        return ('{"summary": "s", "why_it_matters": "w", "key_facts": ["f1"], "category": "AI", "entities": ["openai"], "importance_score": 0.7, "source_type": "high_quality"}', 10, 5)

    return gen


class EmbeddingTests(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(EMB.embed("OpenAI announces model"), EMB.embed("OpenAI announces model"))

    def test_similar_text_high_cosine(self):
        a = EMB.embed("OpenAI announces a new AI model today")
        b = EMB.embed("OpenAI announces a new AI model")
        self.assertGreater(cosine(a, b), 0.7)

    def test_unrelated_lower_cosine(self):
        a = EMB.embed("OpenAI announces a new AI model")
        b = EMB.embed("Stock markets fall amid tariff worries")
        self.assertLess(cosine(a, b), cosine(a, EMB.embed("OpenAI announces a new AI model")))


class EntityTests(unittest.TestCase):
    def test_extracts_proper_nouns(self):
        ents = extract_entities("OpenAI and Anthropic released new models")
        self.assertIn("openai", ents)
        self.assertIn("anthropic", ents)

    def test_different_orgs_no_overlap(self):
        a = extract_entities("OpenAI announces GPT model")
        b = extract_entities("Anthropic announces Claude model")
        # They may share "announces"/"model" as words but not as proper-noun orgs
        self.assertNotIn("openai", b)
        self.assertNotIn("anthropic", a)


class LLMTests(unittest.TestCase):
    def test_extract_json_from_fence(self):
        self.assertEqual(_extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_structured_validates(self):
        llm = LLMClient(generate_fn=lambda s, u, m: ('{"change_type": "minor_update", "confidence": 0.5}', 1, 1))
        out = llm.structured("x", "y", UpdateDiff)
        self.assertIsInstance(out, UpdateDiff)
        self.assertEqual(out.change_type, "minor_update")

    def test_structured_returns_none_on_garbage(self):
        llm = LLMClient(generate_fn=lambda s, u, m: ("not json at all", 1, 1))
        self.assertIsNone(llm.structured("x", "y", UpdateDiff, max_retries=1))
        self.assertGreaterEqual(llm.metrics.errors, 1)

    def test_metrics_counted(self):
        llm = LLMClient(generate_fn=lambda s, u, m: ('{"confidence":0.1}', 7, 3))
        llm.structured("x", "y", StoryIdentity)
        self.assertEqual(llm.metrics.llm_calls, 1)
        self.assertEqual(llm.metrics.llm_input_tokens, 7)
        self.assertEqual(llm.metrics.llm_output_tokens, 3)


class ProcessArticleTests(unittest.TestCase):
    def _db(self):
        return Database.connect("sqlite:///:memory:")

    def test_new_story_when_no_candidates(self):
        db = self._db()
        llm = LLMClient(generate_fn=make_fake_generate(match=True))
        art = _article("OpenAI announces new model", "The company unveiled it today.")
        result = stories.process_article(
            art, db, EMB, llm, lookback_stories=[], similarity_threshold=0.82,
            candidate_limit=10,
        )
        self.assertEqual(result.change_type, "new_story")
        self.assertIsNotNone(result.story.id)
        self.assertEqual(art.story_id, result.story.id)

    def test_update_links_to_existing_story(self):
        db = self._db()
        llm = LLMClient(generate_fn=make_fake_generate(match=True, change_type="major_update"))
        # Seed a story with an embedding close to the new article.
        seed = _article("OpenAI announces new model", "Unveiled today.")
        ensure_embedding(seed, EMB)
        story = Story(id=None, current_title=seed.title, rolling_summary="OpenAI unveiled a model.",
                      representative_embedding=seed.embedding, category="AI")
        db.insert_story(story)

        art = _article("OpenAI announces new model, now with API access", "OpenAI launched API access and pricing today.")
        result = stories.process_article(
            art, db, EMB, llm, lookback_stories=[story], similarity_threshold=0.5,
            candidate_limit=10,
        )
        self.assertEqual(result.change_type, "major_update")
        self.assertEqual(result.story.id, story.id)
        events = db.events_for_story(story.id)
        self.assertTrue(any(e.change_type == "major_update" for e in events))

    def test_similar_but_different_org_becomes_new_story(self):
        db = self._db()
        # LLM (correctly) says NOT the same story for a different company.
        llm = LLMClient(generate_fn=make_fake_generate(match=False))
        seed = _article("OpenAI announces new model", "OpenAI unveiled a model.")
        ensure_embedding(seed, EMB)
        story = Story(id=None, current_title=seed.title, rolling_summary="OpenAI unveiled a model.",
                      representative_embedding=seed.embedding, category="AI")
        db.insert_story(story)

        art = _article("Anthropic announces new model", "Anthropic unveiled a model.")
        result = stories.process_article(
            art, db, EMB, llm, lookback_stories=[story], similarity_threshold=0.5,
            candidate_limit=10,
        )
        self.assertEqual(result.change_type, "new_story")
        self.assertNotEqual(result.story.id, story.id)


if __name__ == "__main__":
    unittest.main()
