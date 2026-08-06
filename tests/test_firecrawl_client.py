from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from firecrawl_client import FirecrawlClient, FirecrawlError  # noqa: E402


class FirecrawlClientTests(unittest.TestCase):
    def test_search_retries_429_and_returns_usage(self):
        calls = []

        def transport(url, method, payload, timeout, headers):
            calls.append((url, payload, headers))
            if len(calls) == 1:
                return 429, {"error": "rate limited"}
            return 200, {"success": True, "data": {"items": [{"url": "https://example.test/p"}], "total": 1}, "usage": {"creditsUsed": 2}, "requestId": "req-1"}

        client = FirecrawlClient(api_key="fixture-key", max_retries=1, backoff_seconds=0, transport=transport, sleep=lambda _: None)
        response = client.search("Kinderkraft NEBO")
        self.assertTrue(response.ok)
        self.assertEqual(response.attempts, 2)
        self.assertEqual(response.usage.credits_used, 2)
        self.assertEqual(response.data["items"][0]["url"], "https://example.test/p")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer fixture-key")

    def test_non_retryable_error_is_not_success(self):
        client = FirecrawlClient(api_key="fixture-key", transport=lambda *args: (400, {"error": "bad request"}))
        with self.assertRaises(FirecrawlError) as error:
            client.scrape("https://example.test")
        self.assertEqual(error.exception.status_code, 400)

    def test_cache_does_not_require_api_key_or_network(self):
        called = []
        client = FirecrawlClient(api_key="", transport=lambda *args: called.append(args))
        response = client.scrape("https://example.test", cache={"markdown": "cached", "title": "Fixture"})
        self.assertTrue(response.cached)
        self.assertEqual(response.data["markdown"], "cached")
        self.assertFalse(called)

    def test_timeout_retries_and_normalizes_exhausted_transport(self):
        calls = []

        def transport(*args):
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("fixture timeout")
            return 200, {"success": True, "data": {"markdown": "ok"}}

        response = FirecrawlClient(api_key="fixture-key", max_retries=1, backoff_seconds=0, transport=transport, sleep=lambda _: None).scrape("https://example.test")
        self.assertEqual(response.attempts, 2)
        self.assertEqual(len(calls), 2)

        def always_timeout(*args):
            raise TimeoutError("fixture timeout")

        with self.assertRaises(FirecrawlError) as error:
            FirecrawlClient(api_key="fixture-key", max_retries=1, backoff_seconds=0, transport=always_timeout, sleep=lambda _: None).scrape("https://example.test")
        self.assertEqual(error.exception.attempts, 2)
        self.assertTrue(error.exception.timeout)


if __name__ == "__main__":
    unittest.main()
