from __future__ import annotations
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))
from repositories.catalog_repository import CatalogRepository, brand_key
from repositories.source_repository import SourceRepository

class FakeClient:
    def __init__(self): self.calls = []
    def select(self, table, **query):
        self.calls.append(("select", table, query))
        return [{"id": "brand-1"}] if table == "brands" else [{"product_slug": "lionelo__amber", "brand": "Lionelo", "model": "Amber"}]
    def upsert(self, table, payload, conflict): self.calls.append(("upsert", table, payload, conflict)); return []

class SupabaseRepositoryTests(unittest.TestCase):
    def test_catalog_uses_stable_product_key_and_maps_slug(self):
        client = FakeClient(); repo = CatalogRepository(client)
        self.assertEqual(repo.catalog()[0]["slug"], "lionelo__amber")
        repo.upsert_product({"product_id": "product:lionelo:amber:"})
        self.assertEqual(client.calls[-1][-1], "product_id")
    def test_source_relationships_use_stable_keys(self):
        client = FakeClient(); repo = SourceRepository(client)
        repo.upsert_source({"source_id": "manufacturer:amber"}); repo.upsert_link({"link_id": "lionelo__amber|manufacturer:amber"}); repo.upsert_evidence({"evidence_id": "e-1"})
        self.assertEqual([call[-1] for call in client.calls], ["source_id", "link_id", "evidence_id"])
    def test_multiword_brand_key_is_shared_with_catalog_lookup(self):
        self.assertEqual(brand_key("  Lionelo  Polska "), "lionelo-polska")

if __name__ == "__main__": unittest.main()
