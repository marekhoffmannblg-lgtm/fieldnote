from __future__ import annotations
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from migrate_validated_state_to_supabase import migrate

class FakeCatalog:
    def __init__(self): self.brands = {}; self.products = {}
    def upsert_brand(self, key, name): self.brands[key] = name
    def upsert_product(self, item): self.products[item["product_id"]] = item
class FakeSources:
    def __init__(self): self.sources = {}; self.links = {}; self.evidence = {}
    def upsert_source(self, item): self.sources[item["source_id"]] = item
    def upsert_link(self, item): self.links[item["link_id"]] = item
    def upsert_evidence(self, item): self.evidence[item["evidence_id"]] = item

def payload():
    products = [{"product_id": f"product:lionelo:{i}:", "brand": "Lionelo", "brand_slug": "lionelo", "model": str(i), "product_slug": f"lionelo__{i}", "group_key": f"lionelo|{i}", "scope": "lionelo", "category_classification_status": "classified", "is_lionelo": True} for i in range(34)]
    products += [{"product_id":"product:competitor:ok:","brand":"Other","model":"OK","product_slug":"other__ok","group_key":"other|ok","scope":"competitor","category_classification_status":"classified"},{"product_id":"product:bad:","brand":"Other","model":"Accessory / part","scope":"competitor","category":"Accessory / part"}]
    return {"schema_version":"1","products":products,"sources":[{"source_id":"s-1"}],"links":[{"link_id":"l-1","product_id":"product:lionelo:0:","source_id":"s-1"},{"link_id":"bad-link","product_id":"product:bad:","source_id":"missing"}],"evidence":[{"evidence_id":"e-1","product_id":"product:lionelo:0:","source_id":"s-1","product_source_link_id":"l-1"},{"evidence_id":"e-bad","product_id":"product:lionelo:1:","source_id":"s-1","product_source_link_id":"l-1"}]}

class SelectiveMigrationTests(unittest.TestCase):
    def test_migrates_34_lionelo_and_valid_provenance_idempotently(self):
        catalog, sources = FakeCatalog(), FakeSources(); first = migrate(payload(), catalog, sources); second = migrate(payload(), catalog, sources)
        self.assertEqual(sum(1 for item in catalog.products.values() if item.get("is_lionelo")), 34); self.assertNotIn("product:bad:", catalog.products); self.assertEqual((len(sources.sources), len(sources.links), len(sources.evidence)), (1, 1, 1)); self.assertEqual((first.products, second.products), (35, 35)); self.assertTrue(any(item["id"] == "bad-link" for item in first.rejected)); self.assertTrue(any(item["id"] == "e-bad" for item in first.rejected))

if __name__ == "__main__": unittest.main()
