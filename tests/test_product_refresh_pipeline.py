import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fieldnote-api"))
from services.product_refresh_service import MemoryRefreshHistory, MemoryRefreshStorage, ProductRefreshService


class Provider:
    def __init__(self, text="Lionelo Amber 3w1 stroller"):
        self.text = text; self.searches = 0; self.scrapes = 0
    def search(self, query, *, limit):
        self.searches += 1
        return {"data": {"items": [{"url": "https://allegro.pl/oferta/amber-123456", "title": "Lionelo Amber 3w1 stroller", "offer_id": "123456"}]}}
    def scrape(self, url):
        self.scrapes += 1
        return {"data": {"markdown": self.text}}


class ProductRefreshTests(unittest.TestCase):
    def make(self, provider):
        history, storage = MemoryRefreshHistory(), MemoryRefreshStorage()
        return ProductRefreshService(provider, storage, history), history, storage

    def test_always_fresh_and_identical_hash_deduplicates_snapshot(self):
        service, history, storage = self.make(Provider())
        first = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        second = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(first["status"], "succeeded"); self.assertEqual(second["status"], "succeeded")
        self.assertEqual(len(history.runs), 4)  # running + terminal for each invocation
        self.assertEqual(len(history.sources), 1)
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


if __name__ == "__main__": unittest.main()
