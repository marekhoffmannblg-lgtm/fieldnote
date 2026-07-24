"""Offline regression coverage for the shared manufacturer post-fetch commit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from provenance_v1 import build_evidence_item
from source_commit import _source_record
from source_lifecycle import default_product_source_link, read_product_source_links, read_source_records


SOURCE_ID = "manufacturer:cybex:52c8810b9c29e1cc"
PRODUCT_SLUG = "cybex__orfeo"


class ManufacturerPostFetchTests(unittest.TestCase):
    def test_source_record_is_global_and_has_cached_snapshots(self) -> None:
        records = {str(item.get("source_id")): item for item in read_source_records()}
        record = records.get(SOURCE_ID, {})
        self.assertEqual(record.get("schema_version"), "2")
        self.assertEqual(record.get("source_type"), "manufacturer")
        self.assertEqual(record.get("fetch", {}).get("status"), "fetched")
        self.assertEqual(record.get("cleaning", {}).get("status"), "cleaned")
        self.assertTrue(record.get("content", {}).get("snapshot_available"))
        self.assertTrue(record.get("content", {}).get("raw_snapshot_path"))
        self.assertTrue(record.get("content", {}).get("clean_snapshot_path"))

    def test_product_link_is_unique_and_assigned(self) -> None:
        links = [item for item in read_product_source_links() if item.get("link_id") == f"{PRODUCT_SLUG}|{SOURCE_ID}"]
        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertTrue(link.get("selection", {}).get("selected"))
        self.assertEqual(link.get("selection", {}).get("role"), "manufacturer")
        self.assertEqual(link.get("assignment", {}).get("status"), "assigned")

    def test_evidence_item_references_the_source_and_link(self) -> None:
        source = {SOURCE_ID: {"source_id": SOURCE_ID, "source_type": "manufacturer", "marketplace": "manufacturer", "content": {"content_hash": "hash"}}}
        link = {SOURCE_ID: default_product_source_link(PRODUCT_SLUG, SOURCE_ID)}
        item = build_evidence_item(
            product_slug=PRODUCT_SLUG, field_name="Waga", current_value="6 kg",
            raw={"source_id": SOURCE_ID, "value": "6 kg", "excerpt": "Waga: 6 kg", "validation_status": "valid", "extraction_method": "deterministic"},
            index=0, source_by_id=source, link_by_source=link, field_validation="valid",
        )
        self.assertEqual(item["source_id"], SOURCE_ID)
        self.assertEqual(item["product_source_link_id"], f"{PRODUCT_SLUG}|{SOURCE_ID}")
        self.assertEqual(item["source_authority"], "manufacturer")
        self.assertEqual(item["extraction_method"], "deterministic")

    def test_record_builder_never_includes_product_assignment(self) -> None:
        directory = ROOT / "input" / "manufacturer_sources" / PRODUCT_SLUG / SOURCE_ID
        record = _source_record(
            source_id=SOURCE_ID, source_type="manufacturer", brand="CYBEX", model="ORFEO",
            original_url="https://www.cybex-online.com/en/row/p/10102511.html",
            canonical_url="https://www.cybex-online.com/en/row/p/10102511.html",
            raw_snapshot_path=directory / "markdown.md", clean_snapshot_path=directory / "technical_clean.md",
            content_hash="hash", content_family_id="manufacturer:hash", title="CYBEX ORFEO",
        )
        self.assertEqual(record.get("schema_version"), "2")
        self.assertNotIn("product_slug", record)
        self.assertNotIn("selection", record)


if __name__ == "__main__":
    unittest.main()
