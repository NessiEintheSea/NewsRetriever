"""Phase 2 tests: URL/text normalisation, fingerprinting, exact dedup."""
import unittest

from src.normalize import normalize_url, normalize_text, normalize_title
from src.dedup import fingerprint, content_hash, dedup_keys, is_exact_duplicate


class NormalizeUrlTests(unittest.TestCase):
    def test_strips_tracking_params(self):
        url = "https://Example.com/Article/?utm_source=x&utm_medium=y&fbclid=z&id=5"
        self.assertEqual(normalize_url(url), "https://example.com/Article?id=5")

    def test_drops_fragment_and_trailing_slash(self):
        self.assertEqual(
            normalize_url("https://example.com/path/#section"),
            "https://example.com/path",
        )

    def test_sorts_query_for_stable_key(self):
        a = normalize_url("https://e.com/x?b=2&a=1")
        b = normalize_url("https://e.com/x?a=1&b=2")
        self.assertEqual(a, b)

    def test_lowercases_host_only(self):
        self.assertEqual(
            normalize_url("HTTPS://Example.COM/Path"),
            "https://example.com/Path",
        )

    def test_empty(self):
        self.assertEqual(normalize_url(""), "")


class NormalizeTextTests(unittest.TestCase):
    def test_strips_html_and_collapses_ws(self):
        self.assertEqual(
            normalize_text("<p>hello   &amp;  world</p>\n\n"), "hello & world"
        )

    def test_unicode_nfkc(self):
        # Fullwidth digits normalise to ASCII under NFKC.
        self.assertEqual(normalize_text("ＡＢＣ"), "ABC")

    def test_title_strips_trailing_media_name(self):
        self.assertEqual(
            normalize_title("OpenAI releases a major new model - TechCrunch"),
            "OpenAI releases a major new model",
        )

    def test_title_keeps_short_headline_with_dash(self):
        # Too short after stripping -> keep original.
        self.assertEqual(normalize_title("A - B"), "A - B")


class FingerprintTests(unittest.TestCase):
    def test_identical_content_same_fingerprint(self):
        a = fingerprint("Title", "Some description")
        b = fingerprint("Title", "Some description")
        self.assertEqual(a, b)

    def test_whitespace_and_html_insensitive(self):
        a = fingerprint("Title  Here", "<b>desc</b>")
        b = fingerprint("Title Here", "desc")
        self.assertEqual(a, b)

    def test_different_content_differs(self):
        self.assertNotEqual(fingerprint("A", "x"), fingerprint("B", "y"))

    def test_content_hash_deterministic(self):
        self.assertEqual(content_hash("hello world"), content_hash("hello   world"))


class DedupTests(unittest.TestCase):
    def test_keys_and_membership(self):
        keys = dedup_keys(guid="g1", canonical_url="https://e/x", fp="abc")
        self.assertIn("guid:g1", keys)
        self.assertIn("url:https://e/x", keys)
        self.assertIn("fp:abc", keys)

    def test_exact_duplicate_detected_by_any_key(self):
        seen = {"fp:abc"}
        keys = dedup_keys(guid="new", canonical_url="https://new", fp="abc")
        self.assertTrue(is_exact_duplicate(keys, seen))

    def test_not_duplicate_when_all_keys_new(self):
        seen = {"guid:old"}
        keys = dedup_keys(guid="new", canonical_url="https://new", fp="zzz")
        self.assertFalse(is_exact_duplicate(keys, seen))


if __name__ == "__main__":
    unittest.main()
