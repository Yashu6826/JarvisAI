from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from Backend.RealtimeSearchEngine import SearchWeb


class FakeResponse:
    def __init__(self, text: str = "", json_data: dict | None = None) -> None:
        self.text = text
        self.content = text.encode("utf-8")
        self._json_data = json_data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        if self._json_data is None:
            raise ValueError("not JSON")
        return self._json_data


def no_serper_config(name: str, default: str = "") -> str:
    return "" if name == "SERPER_API_KEY" else default


class SearchFallbackTests(unittest.TestCase):
    def test_duckduckgo_html_is_parsed_semantically(self) -> None:
        page = """
        <div class="result">
          <a class="result__a" href="https://example.com/fact">Example fact</a>
          <div class="result__snippet">A useful <b>live</b> result.</div>
        </div>
        """
        with (
            patch("Backend.RealtimeSearchEngine.get_config", side_effect=no_serper_config),
            patch(
                "Backend.RealtimeSearchEngine.requests.get",
                return_value=FakeResponse(page),
            ),
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
        with (
            patch("Backend.RealtimeSearchEngine.get_config", side_effect=no_serper_config),
            patch(
                "Backend.RealtimeSearchEngine.requests.get",
                side_effect=[
                    requests.ConnectionError("primary unavailable"),
                    FakeResponse(rss),
                ],
            ),
        ):
            results = SearchWeb("fallback", limit=3)
        self.assertEqual(results[0]["title"], "Fallback result")
        self.assertEqual(results[0]["site_root"], "https://example.org")

    def test_serper_is_primary_when_api_key_is_configured(self) -> None:
        def configured(name: str, default: str = "") -> str:
            values = {
                "SERPER_API_KEY": "secret-key",
                "SERPER_COUNTRY_CODE": "in",
                "SERPER_LANGUAGE_CODE": "en",
            }
            return values.get(name, default)

        response = FakeResponse(json_data={
            "organic": [
                {
                    "title": "Best streaming services in India",
                    "link": "https://example.com/india-streaming",
                    "snippet": "Compare movie and web series streaming platforms.",
                    "date": "Aug 2026",
                }
            ]
        })
        with (
            patch("Backend.RealtimeSearchEngine.get_config", side_effect=configured),
            patch("Backend.RealtimeSearchEngine.requests.post", return_value=response) as post,
            patch("Backend.RealtimeSearchEngine.requests.get") as fallback_get,
        ):
            results = SearchWeb(
                "best streaming services India movies web series",
                limit=5,
            )

        self.assertEqual(results[0]["provider"], "serper")
        self.assertIn("Aug 2026", results[0]["snippet"])
        self.assertEqual(post.call_args.kwargs["headers"]["X-API-KEY"], "secret-key")
        self.assertEqual(post.call_args.kwargs["json"]["gl"], "in")
        fallback_get.assert_not_called()

    def test_irrelevant_and_adult_results_are_rejected(self) -> None:
        page = """
        <div class="result">
          <a class="result__a" href="https://dictionary.example/stream">Stream definition</a>
          <div class="result__snippet">The meaning of a small river.</div>
        </div>
        <div class="result">
          <a class="result__a" href="https://pornhub.example/movies">Adult movies</a>
          <div class="result__snippet">Streaming movie videos.</div>
        </div>
        <div class="result">
          <a class="result__a" href="https://trusted.example/streaming-india">India streaming guide</a>
          <div class="result__snippet">Compare services for movies and web series in India.</div>
        </div>
        """
        with (
            patch("Backend.RealtimeSearchEngine.get_config", side_effect=no_serper_config),
            patch(
                "Backend.RealtimeSearchEngine.requests.get",
                return_value=FakeResponse(page),
            ),
        ):
            results = SearchWeb(
                "best streaming services India movies web series",
                limit=5,
            )

        self.assertEqual([item["url"] for item in results], [
            "https://trusted.example/streaming-india"
        ])

    def test_low_relevance_primary_results_fall_back_to_bing(self) -> None:
        unrelated = """
        <div class="result">
          <a class="result__a" href="https://transport.example/mumbai">Mumbai transport</a>
          <div class="result__snippet">Bus timetables and station routes.</div>
        </div>
        """
        rss = """
        <rss><channel><item>
          <title>India streaming services comparison</title>
          <link>https://example.org/streaming</link>
          <description>Current movie and web series platforms in India</description>
        </item></channel></rss>
        """
        with (
            patch("Backend.RealtimeSearchEngine.get_config", side_effect=no_serper_config),
            patch(
                "Backend.RealtimeSearchEngine.requests.get",
                side_effect=[FakeResponse(unrelated), FakeResponse(rss)],
            ),
        ):
            results = SearchWeb(
                "best streaming services India movies web series",
                limit=5,
            )

        self.assertEqual(results[0]["provider"], "bing")
        self.assertEqual(results[0]["url"], "https://example.org/streaming")


if __name__ == "__main__":
    unittest.main()
