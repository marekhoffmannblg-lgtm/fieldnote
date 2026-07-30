from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "fieldnote-api"))

from firecrawl_client import FirecrawlError  # noqa: E402
import fetch_firecrawl_offer_pages as offer_fetcher  # noqa: E402
import fetch_manufacturer_sources as manufacturer_fetcher  # noqa: E402
from discover_manufacturer_catalog import load_fixture_records  # noqa: E402
from services.brand_catalog_service import BrandCatalogService  # noqa: E402


class Unit7RemediationTests(unittest.TestCase):
    def test_offer_fetch_persists_firecrawl_error_without_nameerror(self):
        root = Path(tempfile.mkdtemp())
        queue_path = root / "queue.csv"
        offer_root = root / "input" / "firecrawl_offer_pages"
        row = {
            "queue_id": "offer-1", "offer_id": "offer-1", "normalized_url": "https://allegro.pl/oferta/nebo",
            "brand": "Kinderkraft", "category": "strollers", "detected_model": "NEBO", "status": "pending",
            "output_dir": "input/firecrawl_offer_pages/offer-1/", "fetched_at": "", "error_message": "",
            "retry_count": "0", "last_attempt_at": "", "last_error_at": "",
        }
        with queue_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=offer_fetcher.QUEUE_COLUMNS)
            writer.writeheader()
            writer.writerow(row)

        original_require = offer_fetcher.require_api_key
        original_scrape = offer_fetcher.scrape_offer
        try:
            offer_fetcher.require_api_key = lambda: "fixture-key"
            offer_fetcher.scrape_offer = lambda *args, **kwargs: (_ for _ in ()).throw(FirecrawlError("429 fixture", status_code=429, attempts=3))
            result = offer_fetcher.fetch_pending_rows(1, False, queue_path=queue_path, root_dir=root, offer_pages_root=offer_root, capture_visuals=False)
        finally:
            offer_fetcher.require_api_key = original_require
            offer_fetcher.scrape_offer = original_scrape

        self.assertEqual(result.fetch_status, "failed")
        with queue_path.open(encoding="utf-8", newline="") as handle:
            saved = next(csv.DictReader(handle))
        self.assertEqual(saved["status"], "error")
        self.assertIn("429 fixture", saved["error_message"])

    def test_pdf_requires_pdf_magic_and_preserves_valid_bytes(self):
        root = Path(tempfile.mkdtemp())
        original_root = manufacturer_fetcher.SOURCES_ROOT
        original_fetch = manufacturer_fetcher.fetch_bytes
        manufacturer_fetcher.SOURCES_ROOT = root
        try:
            manufacturer_fetcher.fetch_bytes = lambda *args, **kwargs: (b"<html>not pdf</html>", {"Content-Type": "text/html"}, 200)
            with self.assertRaises(ValueError):
                manufacturer_fetcher.write_source(brand="Brand", model="Model", url="https://brand.test/manual.pdf", is_pdf=True, resume=False)
            self.assertFalse(list(root.rglob("document.pdf")))

            pdf_bytes = b"%PDF-1.4 fixture bytes"
            manufacturer_fetcher.fetch_bytes = lambda *args, **kwargs: (pdf_bytes, {"Content-Type": "application/pdf"}, 200)
            manufacturer_fetcher.write_source(brand="Brand", model="Model", url="https://brand.test/manual.pdf", is_pdf=True, resume=False)
            document = next(root.rglob("document.pdf"))
            self.assertEqual(document.read_bytes(), pdf_bytes)
        finally:
            manufacturer_fetcher.SOURCES_ROOT = original_root
            manufacturer_fetcher.fetch_bytes = original_fetch

    def test_catalog_fixture_root_is_contained_and_brand_is_configured(self):
        service = BrandCatalogService()
        with self.assertRaises(ValueError):
            service.discover("Kinderkraft", fixture_root=Path(tempfile.mkdtemp()))
        with self.assertRaises(ValueError):
            service.discover("Unknown brand", fixture_root=ROOT / "fixtures" / "firecrawl" / "manufacturer")
        report = service.discover("Kinderkraft", fixture_root=ROOT / "fixtures" / "firecrawl" / "manufacturer")
        self.assertEqual(report["brand"], "Kinderkraft")

        fixture_dir = Path(tempfile.mkdtemp())
        (fixture_dir / "catalog.json").write_text(json.dumps({"pages": [{"brand": "Brand", "model": "Model", "title": "Brand Model", "secret": "must-not-leak"}]}), encoding="utf-8")
        safe_records = load_fixture_records(fixture_dir)
        self.assertEqual(safe_records, [{"brand": "Brand", "model": "Model", "title": "Brand Model"}])

    def test_current_catalog_reports_review_required_models(self):
        root = Path(tempfile.mkdtemp())
        catalog = root / "products.json"
        catalog.write_text(json.dumps({"products": [{"brand": "Brand", "model": "Future", "title": "Brand Future stroller"}]}), encoding="utf-8")
        report = BrandCatalogService(catalog_path=catalog).current("Brand")
        self.assertEqual(report["counts"]["unclassified_real_products"], 1)
        self.assertEqual(report["quality_gate"], "review")

    def test_discovery_uses_configured_official_url_with_injected_client(self):
        calls = []

        class Client:
            def crawl(self, url, **kwargs):
                calls.append(url)
                return type("Response", (), {"data": {"products": [{"model": "NEBO", "title": "NEBO stroller", "benchmark_group": "standard_stroller"}]}})()

        report = BrandCatalogService().discover("Kinderkraft", client=Client())
        self.assertEqual(calls, ["https://kinderkraft.pl"])
        self.assertEqual(report["quality_gate"], "pass")


if __name__ == "__main__":
    unittest.main()
