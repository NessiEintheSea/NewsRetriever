"""Quality upgrade tests: OpenAI embedder (mocked), factory, full-text extractor."""
import types
import unittest

from src.embedding import (
    LocalLexicalEmbedder,
    OpenAIEmbedder,
    get_embedder,
    cosine,
)
from src.content import extract_text_from_html, fetch_full_text


class _Resp:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        return self._payload


class OpenAIEmbedderTests(unittest.TestCase):
    def test_returns_api_vector(self):
        calls = []

        def fake_post(url, headers, payload):
            calls.append((url, headers, payload))
            return _Resp({"data": [{"embedding": [0.1, 0.2, 0.3]}]})

        emb = OpenAIEmbedder("sk-test", post_fn=fake_post)
        self.assertEqual(emb.embed("hello"), [0.1, 0.2, 0.3])
        # endpoint + auth header present, key not logged anywhere by us
        self.assertEqual(calls[0][0], OpenAIEmbedder.ENDPOINT)
        self.assertTrue(calls[0][1]["Authorization"].startswith("Bearer "))

    def test_falls_back_on_http_error(self):
        fb = LocalLexicalEmbedder()
        emb = OpenAIEmbedder("sk-test", post_fn=lambda u, h, p: _Resp({}, status=500), fallback=fb)
        got = emb.embed("some text")
        self.assertEqual(got, fb.embed("some text"))  # deterministic local fallback

    def test_falls_back_on_exception(self):
        def boom(u, h, p):
            raise RuntimeError("network down")

        fb = LocalLexicalEmbedder()
        emb = OpenAIEmbedder("sk-test", post_fn=boom, fallback=fb)
        self.assertEqual(emb.embed("x y z"), fb.embed("x y z"))

    def test_requires_key(self):
        with self.assertRaises(ValueError):
            OpenAIEmbedder("")


class FactoryTests(unittest.TestCase):
    def test_local_default(self):
        cfg = types.SimpleNamespace(EMBEDDING_PROVIDER="local")
        self.assertIsInstance(get_embedder(cfg), LocalLexicalEmbedder)

    def test_openai_selected(self):
        cfg = types.SimpleNamespace(
            EMBEDDING_PROVIDER="openai", OPENAI_API_KEY="sk-x",
            OPENAI_EMBEDDING_MODEL="text-embedding-3-small",
        )
        self.assertIsInstance(get_embedder(cfg), OpenAIEmbedder)


class CosineTests(unittest.TestCase):
    def test_true_cosine_non_normalised(self):
        # cosine of parallel vectors is 1 regardless of magnitude
        self.assertAlmostEqual(cosine([2.0, 0.0], [5.0, 0.0]), 1.0, places=6)

    def test_dimension_mismatch_is_zero(self):
        # local (256) vs openai (1536) never falsely match
        self.assertEqual(cosine([1.0, 0.0], [1.0, 0.0, 0.0]), 0.0)


class FullTextTests(unittest.TestCase):
    HTML = """
    <html><head><style>.x{color:red}</style></head>
    <body>
      <nav>Home About Contact</nav>
      <article>
        <h1>OpenAI announces a brand new model today</h1>
        <p>The company said the model is available to developers now.</p>
        <script>trackingCode()</script>
        <p>Pricing and rate limits were published alongside the release.</p>
        <li>menu</li>
      </article>
      <footer>Copyright 2026</footer>
    </body></html>
    """

    def test_extracts_body_paragraphs(self):
        text = extract_text_from_html(self.HTML)
        self.assertIn("available to developers now", text)
        self.assertIn("Pricing and rate limits", text)

    def test_drops_scripts_and_chrome(self):
        text = extract_text_from_html(self.HTML)
        self.assertNotIn("trackingCode", text)
        self.assertNotIn("Copyright", text)
        self.assertNotIn("Home About Contact", text)

    def test_fetch_full_text_with_injected_getter(self):
        resp = _Resp({}, status=200, text=self.HTML)
        got = fetch_full_text("https://e/x", get_fn=lambda u, t: resp, max_chars=1000)
        self.assertIn("available to developers now", got)

    def test_fetch_full_text_error_returns_empty(self):
        def boom(u, t):
            raise RuntimeError("timeout")

        self.assertEqual(fetch_full_text("https://e/x", get_fn=boom), "")

    def test_fetch_full_text_truncates(self):
        resp = _Resp({}, status=200, text=self.HTML)
        got = fetch_full_text("https://e/x", get_fn=lambda u, t: resp, max_chars=20)
        self.assertLessEqual(len(got), 20)


if __name__ == "__main__":
    unittest.main()
