from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from Backend.RealtimeSearchEngine import SearchWeb


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.content = text.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


class SearchFallbackTests(unittest.TestCase):
    def test_duckduckgo_html_is_parsed_semantically(self) -> None:
        page = """
        <div class="result">
          <a class="result__a" href="https://example.com/fact">Example fact</a>
          <div class="result__snippet">A useful <b>live</b> result.</div>
        </div>
        """
        with patch(
            "Backend.RealtimeSearchEngine.requests.get",
            return_value=FakeResponse(page),
        ):
            results = SearchWeb("example", limit=3)
        self.assertEqual(results[0]["url"], "https://example.com/fact")
        self.assertEqual(results[0]["snippet"], "A useful live result.")

    def test_bing_rss_is_used_when_primary_provider_fails(self) -> None:
        rss = """
        <rss><channel><item>
          <title>Fallback result</title>
          <link>https://example.org/source</link>
          <description>Fallback evidence</description>
        </item></channel></rss>
        """
        with patch(
            "Backend.RealtimeSearchEngine.requests.get",
            side_effect=[
                requests.ConnectionError("primary unavailable"),
                FakeResponse(rss),
            ],
        ):
            results = SearchWeb("fallback", limit=3)
        self.assertEqual(results[0]["title"], "Fallback result")
        self.assertEqual(results[0]["site_root"], "https://example.org")


if __name__ == "__main__":
    unittest.main()
