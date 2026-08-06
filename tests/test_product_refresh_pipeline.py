import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fieldnote-api"))
from services.product_refresh_service import MemoryRefreshHistory, MemoryRefreshStorage, ProductRefreshService, RefreshLimits


class Provider:
    def __init__(self, text="Lionelo Amber 3w1 stroller"):
        self.text = text; self.searches = 0; self.scrapes = 0
    def search(self, query, *, limit):
        self.searches += 1
        return {"data": {"items": [{"url": "https://allegro.pl/oferta/amber-123456", "title": "Lionelo Amber 3w1 stroller", "offer_id": "123456"}]}}
    def scrape(self, url):
        self.scrapes += 1
        return {"data": {"markdown": self.text}}


class Response:
    def __init__(self, data): self.data = data


class ProductRefreshTests(unittest.TestCase):
    def make(self, provider):
        history, storage = MemoryRefreshHistory(), MemoryRefreshStorage()
        return ProductRefreshService(provider, storage, history), history, storage

    def test_always_fresh_and_identical_hash_deduplicates_snapshot(self):
        provider = Provider(); service, history, storage = self.make(provider)
        first = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        second = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(first["status"], "succeeded"); self.assertEqual(second["status"], "succeeded")
        self.assertEqual(len(history.runs), 4)  # running + terminal for each invocation
        self.assertEqual(len(history.sources), 1)
        self.assertEqual(len(history.run_sources), 2)
        self.assertEqual(provider.searches, 2)
        self.assertEqual(provider.scrapes, 2)
        self.assertEqual(len(storage.objects), 2)

    def test_changed_content_hash_creates_new_source_snapshot(self):
        provider = Provider("old"); service, history, _ = self.make(provider)
        service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        provider.text = "new"
        service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(len(history.sources), 2)

    def test_non_exact_match_is_not_scraped(self):
        provider = Provider(); provider.search = lambda query, limit: {"data": {"items": [{"url": "https://x", "title": "Adapter do Lionelo Amber"}]}}
        service, history, _ = self.make(provider)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "partial"); self.assertEqual(provider.scrapes, 0); self.assertEqual(len(history.sources), 0)

    def test_storage_failure_preserves_last_known_good(self):
        provider = Provider(); history = MemoryRefreshHistory()
        class Broken(MemoryRefreshStorage):
            def put(self, path, content, *, content_type): raise OSError("storage unavailable")
        result = ProductRefreshService(provider, Broken(), history).refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "failed"); self.assertTrue(result["result"]["last_known_good_preserved"])

    def test_real_firecrawl_response_shape_and_canonical_source(self):
        provider = Provider(); provider.search = lambda query, limit: Response({"items": [{"url": "https://allegro.pl/oferta/amber-123456", "title": "Lionelo Amber 3w1 stroller", "offer_id": "123456"}]})
        provider.scrape = lambda url: Response({"markdown": "fixture"})
        service, history, _ = self.make(provider)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(history.sources[0]["source_id"], "allegro:123456")

    def test_untrusted_exact_title_is_not_scraped(self):
        provider = Provider(); provider.search = lambda query, limit: {"data": {"items": [{"url": "http://127.0.0.1/admin", "title": "Lionelo Amber 3w1 stroller", "offer_id": "123456"}]}}
        service, history, _ = self.make(provider)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "partial"); self.assertEqual(provider.scrapes, 0); self.assertEqual(history.sources, [])

    def test_custom_identity_gate_cannot_bypass_url_validation(self):
        provider = Provider(); provider.search = lambda query, limit: {"data": {"items": [{"url": "https://evil.example/x", "title": "Lionelo Amber 3w1 stroller"}]}}
        service, _, _ = self.make(provider); service.identity_gate = lambda **_: "exact_match"
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "partial"); self.assertEqual(provider.scrapes, 0)

    def test_same_clean_text_different_raw_has_immutable_storage_paths(self):
        provider = Provider("same"); calls = []
        provider.scrape = lambda url: {"data": {"markdown": "same", "request_id": str(len(calls))}} or calls.append(1)
        # Replace with two explicit payloads while retaining identical clean text.
        payloads = iter(({"data": {"markdown": "same", "request_id": "a"}}, {"data": {"markdown": "same", "request_id": "b"}}))
        provider.scrape = lambda url: next(payloads)
        service, history, storage = self.make(provider)
        service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(len(history.sources), 1)
        self.assertEqual(len(storage.objects), 4)

    def test_limits_and_cancel_are_enforced_before_scrape(self):
        provider = Provider(); history = MemoryRefreshHistory(); cancelled = [False]
        service = ProductRefreshService(provider, MemoryRefreshStorage(), history)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", limits=RefreshLimits(max_pages=0, max_candidates=10), cancel_check=lambda: cancelled[0])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(provider.searches, 1); self.assertEqual(provider.scrapes, 0)
        cancelled[0] = True
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", cancel_check=lambda: cancelled[0])
        self.assertEqual(result["status"], "partial"); self.assertEqual(provider.searches, 1)

    def test_positive_page_cap_and_cancel_between_scrapes(self):
        class Multi(Provider):
            def __init__(self): super().__init__(); self.items = [
                {"url": "https://allegro.pl/oferta/a", "title": "Lionelo Amber 3w1 stroller", "offer_id": "a"},
                {"url": "https://allegro.pl/oferta/b", "title": "Lionelo Amber 3w1 stroller", "offer_id": "b"},
            ]
            def search(self, query, *, limit): self.searches += 1; return {"data": {"items": self.items}}
            def scrape(self, url):
                self.scrapes += 1
                if self.scrapes == 1: self.cancel = True
                return {"data": {"markdown": "same"}}
        provider = Multi(); provider.cancel = False
        service, history, _ = self.make(provider)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", limits=RefreshLimits(max_pages=1, max_candidates=10), cancel_check=lambda: provider.cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(provider.scrapes, 1)

    def test_provider_timeout_preserves_last_known_good(self):
        class Hanging(Provider):
            def search(self, query, *, limit):
                import time; time.sleep(0.2); return {"data": {"items": []}}
        service, _, _ = self.make(Hanging())
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", limits=RefreshLimits(timeout_seconds=0.01))
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["result"]["last_known_good_preserved"])


if __name__ == "__main__": unittest.main()
