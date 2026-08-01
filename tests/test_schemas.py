"""Schema coercion tests: absorb common LLM type-mismatches instead of failing."""
import unittest

from src.schemas import ArticleFacts, StoryIdentity, UpdateDiff


class ArticleFactsCoercionTests(unittest.TestCase):
    def test_category_as_list_becomes_string(self):
        f = ArticleFacts.model_validate({"category": ["AI", "Tech"], "summary": "s"})
        self.assertIsInstance(f.category, str)
        self.assertIn("AI", f.category)

    def test_key_facts_as_string_becomes_list(self):
        f = ArticleFacts.model_validate({"key_facts": "single fact"})
        self.assertEqual(f.key_facts, ["single fact"])

    def test_summary_as_list_joined(self):
        f = ArticleFacts.model_validate({"summary": ["One.", "Two."]})
        self.assertEqual(f.summary, "One. Two.")

    def test_importance_as_string_number(self):
        f = ArticleFacts.model_validate({"importance_score": "0.9"})
        self.assertAlmostEqual(f.importance_score, 0.9)

    def test_source_type_as_list_falls_back(self):
        f = ArticleFacts.model_validate({"source_type": ["weird"]})
        self.assertEqual(f.source_type, "secondary")

    def test_entities_with_none_and_numbers(self):
        f = ArticleFacts.model_validate({"entities": ["OpenAI", None, 42]})
        self.assertEqual(f.entities, ["OpenAI", "42"])


class StoryIdentityCoercionTests(unittest.TestCase):
    def test_matched_id_as_string(self):
        s = StoryIdentity.model_validate({"same_story": True, "matched_story_id": "7"})
        self.assertEqual(s.matched_story_id, 7)

    def test_matched_id_null_string(self):
        s = StoryIdentity.model_validate({"matched_story_id": "null"})
        self.assertIsNone(s.matched_story_id)

    def test_reason_as_list(self):
        s = StoryIdentity.model_validate({"reason": ["a", "b"]})
        self.assertEqual(s.reason, "a b")


class UpdateDiffCoercionTests(unittest.TestCase):
    def test_change_type_invalid_defaults(self):
        d = UpdateDiff.model_validate({"change_type": "HUGE_UPDATE"})
        self.assertEqual(d.change_type, "no_meaningful_change")

    def test_facts_as_string(self):
        d = UpdateDiff.model_validate({"change_type": "major_update", "new_facts": "API launched"})
        self.assertEqual(d.new_facts, ["API launched"])


if __name__ == "__main__":
    unittest.main()
