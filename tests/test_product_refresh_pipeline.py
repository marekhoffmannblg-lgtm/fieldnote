import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fieldnote-api"))
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from services.product_refresh_service import MemoryRefreshHistory, MemoryRefreshStorage, ProductRefreshService, RefreshLimits
from firecrawl_client import FirecrawlClient


class Provider:
    def __init__(self, text="Waga: 9,5 kg Maksymalne obciążenie: 22 kg"):
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
        provider.scrape = lambda url: Response({"markdown": "Waga: 9,5 kg Maksymalne obciążenie: 22 kg"})
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
        self.assertEqual(result["status"], "cancelled"); self.assertEqual(provider.searches, 1)

    def test_positive_page_cap_and_cancel_between_scrapes(self):
        class Multi(Provider):
            def __init__(self): super().__init__(); self.items = [
                {"url": "https://allegro.pl/oferta/a", "title": "Lionelo Amber 3w1 stroller", "offer_id": "a"},
                {"url": "https://allegro.pl/oferta/b", "title": "Lionelo Amber 3w1 stroller", "offer_id": "b"},
            ]
            def search(self, query, *, limit): self.searches += 1; return {"data": {"items": self.items}}
            def scrape(self, url):
                self.scrapes += 1
                return {"data": {"markdown": "same"}}
        provider = Multi(); checks = [0]
        service, history, _ = self.make(provider)
        def cancel_before_second_scrape():
            checks[0] += 1
            return checks[0] == 4  # search, first scrape, post-first-scrape, second scrape
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", limits=RefreshLimits(max_pages=2, max_candidates=10), cancel_check=cancel_before_second_scrape)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(provider.scrapes, 1)
        self.assertEqual(len(history.sources), 1)

    def test_provider_timeout_preserves_last_known_good(self):
        def transport(*_):
            raise TimeoutError("fixture deadline")
        client = FirecrawlClient(api_key="fixture", max_retries=0, backoff_seconds=0, transport=transport, sleep=lambda _: None)
        service, _, _ = self.make(client)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", limits=RefreshLimits(timeout_seconds=0.01))
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["result"]["last_known_good_preserved"])

    def test_schema_facts_have_field_evidence_and_limited_injected_ai_fallback(self):
        provider = Provider("Waga: 9,5 kg")
        calls = []
        service, _, _ = self.make(provider)
        service.ai_extractor = lambda *, text, fields, max_tokens: calls.append((text, fields, max_tokens)) or {"facts": {"maksymalne_obciazenie_kg": 22}, "usage": {"total_tokens": 3, "complete": True}}
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        state = result["result"]["scoped_commit"]["semantic_state"]
        self.assertEqual(state["facts"], {"waga_wozka_kg": 9.5, "maksymalne_obciazenie_kg": 22})
        self.assertTrue(state["openai"]["requested"])
        self.assertLessEqual(len(calls[0][1]), 3)
        self.assertEqual({candidate["field"] for candidate in state["candidates"]}, {"waga_wozka_kg", "maksymalne_obciazenie_kg"})

    def test_missing_ai_adapter_is_controlled_partial_without_semantic_commit(self):
        service, _, _ = self.make(Provider("Waga: 9,5 kg"))
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["result"]["no_mutation"])
        self.assertNotIn("scoped_commit", result["result"])

    def test_conflicting_facts_are_not_selected_by_source_order(self):
        provider = Provider()
        provider.search = lambda query, limit: {"data": {"items": [
            {"url": "https://allegro.pl/oferta/a", "title": "Lionelo Amber 3w1 stroller", "offer_id": "a"},
            {"url": "https://allegro.pl/oferta/b", "title": "Lionelo Amber 3w1 stroller", "offer_id": "b"},
        ]}}
        texts = iter(("Waga: 9 kg Maksymalne obciążenie: 22 kg", "Waga: 10 kg Maksymalne obciążenie: 22 kg"))
        provider.scrape = lambda url: {"data": {"markdown": next(texts)}}
        service, _, _ = self.make(provider)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", limits=RefreshLimits(max_pages=2))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["result"]["reason"], "unresolved_fields_without_ai_adapter")
        self.assertTrue(any(candidate["field"] == "waga_wozka_kg" and candidate["status"] == "conflict" for candidate in result["result"]["candidates"]))

    def test_ai_failure_is_partial_without_semantic_commit(self):
        service, _, _ = self.make(Provider("Waga: 9,5 kg"))
        service.ai_extractor = lambda **_: (_ for _ in ()).throw(TimeoutError("ai unavailable"))
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["result"]["reason"], "ai_extractor_error")
        self.assertNotIn("scoped_commit", result["result"])

    def test_incomplete_ai_response_is_partial_without_semantic_commit(self):
        service, _, _ = self.make(Provider("Waga: 9,5 kg"))
        service.ai_extractor = lambda **_: {"facts": {}, "usage": {"total_tokens": 3, "complete": True}}
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["result"]["reason"], "ai_response_incomplete")
        self.assertNotIn("scoped_commit", result["result"])

    def test_cancel_after_last_scrape_prevents_semantic_commit(self):
        provider = Provider("Waga: 9,5 kg")
        checks = [0]
        def cancel():
            checks[0] += 1
            return checks[0] == 4
        service, _, _ = self.make(provider)
        result = service.refresh(product_id="p1", product_slug="lionelo__amber", brand="Lionelo", model="Amber", configuration="3w1", cancel_check=cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("scoped_commit", result["result"])


if __name__ == "__main__": unittest.main()
