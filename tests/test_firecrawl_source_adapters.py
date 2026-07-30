from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from firecrawl_client import FirecrawlClient  # noqa: E402
from source_adapters import AllegroAdapter, AmazonAdapter, ManufacturerAdapter, RetailerAdapter, SourceCandidate  # noqa: E402


class AdapterTests(unittest.TestCase):
    def client(self):
        return FirecrawlClient(api_key="fixture", transport=lambda *args: (200, {"success": True, "data": {"title": "Kinderkraft NEBO stroller", "url": "https://example.test/nebo", "markdown": "Kinderkraft NEBO stroller"}}), sleep=lambda _: None)

    def test_all_external_adapters_share_provenance_contract(self):
        candidates = [
            (AllegroAdapter(), SourceCandidate("allegro:1", "allegro", "marketplace_offer", "https://allegro.pl/oferta/nebo-1", "Kinderkraft NEBO")),
            (AmazonAdapter(), SourceCandidate("amazon:1", "amazon", "marketplace_offer", "https://amazon.pl/dp/NEBO1", "Kinderkraft NEBO")),
            (RetailerAdapter(), SourceCandidate("retailer:1", "retailer", "retailer_offer", "https://shop.test/nebo", "Kinderkraft NEBO")),
            (ManufacturerAdapter(), SourceCandidate("manufacturer:1", "manufacturer", "manufacturer_product_page", "https://kinderkraft.pl/nebo", "Kinderkraft NEBO")),
        ]
        for adapter, candidate in candidates:
            fetched = adapter.fetch(candidate, {"firecrawl_client": self.client()})
            self.assertEqual(fetched.status, "fetched")
            normalized = adapter.normalize(fetched)
            self.assertEqual(set(normalized.provenance), {"source_id", "canonical_url", "domain", "content_hash", "raw_snapshot_path", "clean_snapshot_path", "metadata"})
            classification = adapter.classify(normalized, {"brand": "Kinderkraft", "model": "NEBO"})
            self.assertEqual(classification["quality_gate"], "accepted")

    def test_accessory_quality_gate_rejects_marketplace_fixture(self):
        adapter = AmazonAdapter()
        source = SourceCandidate("amazon:bag", "amazon", "marketplace_offer", "https://amazon.pl/dp/BAG", "Kinderkraft NEBO rain cover")
        normalized = adapter.normalize(source)
        result = adapter.classify(normalized, {"brand": "Kinderkraft", "model": "NEBO"})
        self.assertEqual(result["quality_gate"], "rejected")
        self.assertEqual(result["product_type"], "accessory")


if __name__ == "__main__":
    unittest.main()
