"""Tests for delivery-time news-style summarisation + news-like rendering."""
import unittest

from src.deliver import summarize_new, summarize_update
from src.llm import LLMClient
from src.notifiers.discord import build_embeds


def _fake(payload):
    return LLMClient(generate_fn=lambda s, u, m: (payload, 5, 5))


class DeliverTests(unittest.TestCase):
    def test_summarize_new_returns_facts(self):
        llm = _fake('{"headline":"見出し","summary":"リード文。","key_facts":["要点1"],'
                    '"why_it_matters":"重要な理由","category":"AI","importance_score":0.8}')
        f = summarize_new(llm, "OpenAI ships model", "body")
        self.assertEqual(f.headline, "見出し")
        self.assertEqual(f.summary, "リード文。")
        self.assertEqual(f.key_facts, ["要点1"])

    def test_summarize_update_returns_facts(self):
        llm = _fake('{"headline":"続報見出し","summary":"新しくなった点。","key_facts":["新事実"],'
                    '"why_it_matters":"理由","category":"AI","importance_score":0.6}')
        f = summarize_update(llm, "story", "既報", ["新事実"], [])
        self.assertEqual(f.headline, "続報見出し")

    def test_summarize_new_none_on_garbage(self):
        llm = _fake("not json")
        self.assertIsNone(summarize_new(llm, "t", "b", ))


class NewsRenderingTests(unittest.TestCase):
    def test_new_embed_leads_with_lede(self):
        digest = {"items": [{
            "kind": "new",
            "title": "見出しX",
            "lede": "これはリード文です。",
            "summary_points": ["ポイントA", "ポイントB"],
            "why_it_matters": "重要な理由Y",
            "categories": ["AI"],
            "source_name": "example.com",
            "url": "https://example.com/a",
        }]}
        desc = build_embeds(digest)[0]["description"]
        # lede appears before the points block
        self.assertLess(desc.index("これはリード文です"), desc.index("ポイントA"))
        self.assertIn("💡 なぜ重要か", desc)
        self.assertIn("重要な理由Y", desc)
        self.assertIn("[example.com](https://example.com/a)", desc)

    def test_update_embed_has_lede_and_changes(self):
        digest = {"items": [{
            "kind": "update",
            "title": "続報Z",
            "lede": "続報のリード。",
            "new_facts": ["新しい事実"],
            "changed_facts": [],
            "why_it_matters": "続報が重要な理由",
            "source_name": "src",
            "url": "https://s/x",
        }]}
        desc = build_embeds(digest)[0]["description"]
        self.assertIn("続報のリード", desc)
        self.assertIn("新しい事実", desc)


if __name__ == "__main__":
    unittest.main()
