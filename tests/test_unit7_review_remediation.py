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
from discover_manufacturer_catalog import discover_catalog, load_fixture_records  # noqa: E402
from auth.roles import Principal  # noqa: E402
from services.brand_catalog_service import BrandCatalogService  # noqa: E402

try:
    from fastapi import HTTPException  # noqa: E402
    from routers.brand_catalogs import CatalogRefreshRequest, discover_brand_catalog  # noqa: E402
    ROUTER_AVAILABLE = True
except ModuleNotFoundError:
    CatalogRefreshRequest = discover_brand_catalog = HTTPException = None
    ROUTER_AVAILABLE = False


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

    def test_pdf_resume_does_not_skip_legacy_html_artifact(self):
        root = Path(tempfile.mkdtemp())
        original_root = manufacturer_fetcher.SOURCES_ROOT
        original_fetch = manufacturer_fetcher.fetch_bytes
        manufacturer_fetcher.SOURCES_ROOT = root
        calls = []
        try:
            canonical = manufacturer_fetcher.canonicalize_url("https://brand.test/manual.pdf")
            source_id = manufacturer_fetcher.source_identifier("Brand", canonical)
            target = root / "brand__model" / source_id
            target.mkdir(parents=True)
            (target / "metadata.json").write_text(json.dumps({"canonical_url": canonical}), encoding="utf-8")
            (target / "document.pdf").write_bytes(b"<html>legacy artifact</html>")
            valid_pdf = b"%PDF-1.4 refreshed fixture"
            manufacturer_fetcher.fetch_bytes = lambda *args, **kwargs: (calls.append(kwargs.get("expect_pdf")) or (valid_pdf, {"Content-Type": "application/pdf"}, 200))
            result = manufacturer_fetcher.write_source(brand="Brand", model="Model", url="https://brand.test/manual.pdf", is_pdf=True, resume=True)
            self.assertFalse(result[1])
            self.assertEqual(calls, [True])
            self.assertEqual((target / "document.pdf").read_bytes(), valid_pdf)
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

        outside = Path(tempfile.mkdtemp())
        link = ROOT / "fixtures" / "firecrawl" / "manufacturer" / ".unit7-fixture-link"
        try:
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                service.discover("Kinderkraft", fixture_root=link)
        finally:
            if link.is_symlink():
                link.unlink()

        if ROUTER_AVAILABLE:
            with self.assertRaises(HTTPException) as route_error:
                discover_brand_catalog(CatalogRefreshRequest(brand="Kinderkraft", fixture_root=str(outside)), Principal("admin", "admin@test", "admin", False), service)
            self.assertEqual(getattr(route_error.exception, "status_code", None), 422)

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

    def test_discovery_provider_failure_is_controlled_partial(self):
        calls = []

        class Client:
            def crawl(self, url, **kwargs):
                calls.append(url)
                raise FirecrawlError("429 fixture", status_code=429, attempts=3)

        report = BrandCatalogService().discover("Kinderkraft", client=Client())
        self.assertEqual(calls, ["https://kinderkraft.pl"])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["quality_gate"], "review")

    def test_empty_official_catalog_payload_is_controlled_partial(self):
        class Client:
            def crawl(self, url, **kwargs):
                return type("Response", (), {"data": {}})()

        report = BrandCatalogService().discover("Kinderkraft", client=Client())
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["quality_gate"], "review")

    def test_catalog_deduplication_is_order_independent(self):
        records = [
            {"brand": "Brand", "model": "Combi", "title": "Brand Combi Black stroller", "benchmark_group": "standard_stroller"},
            {"brand": "Brand", "model": "Combi", "title": "Brand Combi White stroller"},
        ]
        first = discover_catalog(brand="Brand", fixture_root=self._fixture_for_records(records))
        second = discover_catalog(brand="Brand", fixture_root=self._fixture_for_records(list(reversed(records))))
        self.assertEqual((first["items"], first["counts"], first["quality_gate"]), (second["items"], second["counts"], second["quality_gate"]))

    def test_catalog_conflicting_duplicate_groups_requires_review(self):
        records = [
            {"brand": "Brand", "model": "Combi", "title": "Brand Combi 2w1", "benchmark_group": "light_stroller"},
            {"brand": "Brand", "model": "Combi", "title": "Brand Combi 2w1 white", "benchmark_group": "standard_stroller"},
        ]
        report = discover_catalog(brand="Brand", fixture_root=self._fixture_for_records(records))
        self.assertEqual(report["quality_gate"], "review")
        self.assertEqual(report["counts"]["review_required"], 1)

    def test_catalog_conflicting_group_fields_requires_review(self):
        records = [
            {
                "brand": "Brand",
                "model": "Combi",
                "title": "Brand Combi Black",
                "benchmark_group": "light_stroller",
                "benchmark_group_key": "standard_stroller",
            },
            {
                "brand": "Brand",
                "model": "Combi",
                "title": "Brand Combi White",
                "benchmark_group": "light_stroller",
            },
        ]
        for order in (records, list(reversed(records))):
            report = discover_catalog(brand="Brand", fixture_root=self._fixture_for_records(order))
            self.assertEqual(report["quality_gate"], "review")
            self.assertEqual(report["counts"]["review_required"], 1)
            self.assertEqual(report["items"][0]["classification_reason"], "conflicting_benchmark_groups")

    @staticmethod
    def _fixture_for_records(records):
        root = Path(tempfile.mkdtemp())
        (root / "catalog.json").write_text(json.dumps({"pages": records}), encoding="utf-8")
        return root


if __name__ == "__main__":
    unittest.main()
