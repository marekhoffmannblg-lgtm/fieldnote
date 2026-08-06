"""Offline contract tests for competitive benchmark manifests."""
from __future__ import annotations

import hashlib
import sys
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fieldnote-api"))

import app as api  # noqa: E402


ANCHOR = "product:lionelo:agia:unknown"
COMPETITOR = "product:bugaboo:butterfly-2:none"
LIONELO_PARTICIPANT = "product:lionelo:bess:none"
OTHER_GROUP = "product:cybex:balios-s:none"
UNCLASSIFIED = "product:other:unclassified:none"
ANCHOR_NO_GROUP = "product:lionelo:unclassified:none"


def fixture_products() -> list[dict[str, str]]:
    return [
        {"product_id": ANCHOR, "brand": " Lionelo ", "model": "Agia", "configuration": "", "benchmark_group": "light_stroller", "created_at": "2026-01-01T00:00:00Z"},
        {"product_id": COMPETITOR, "brand": "Bugaboo", "model": "Butterfly 2", "configuration": "", "benchmark_group": "light_stroller"},
        {"product_id": LIONELO_PARTICIPANT, "brand": "Lionelo", "model": "Bess", "configuration": "", "benchmark_group": "light_stroller", "created_at": "2026-01-02T00:00:00Z"},
        {"product_id": OTHER_GROUP, "brand": "CYBEX", "model": "Balios S", "configuration": "", "benchmark_group": "standard_stroller"},
        {"product_id": UNCLASSIFIED, "brand": "Other", "model": "Unknown", "configuration": "", "benchmark_group": ""},
        {"product_id": ANCHOR_NO_GROUP, "brand": "Lionelo", "model": "Unclassified", "configuration": "", "benchmark_group": ""},
    ]


def payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "benchmark_group_key": "light_stroller",
        "anchor_product_id": ANCHOR,
        "participant_product_ids": [COMPETITOR],
        "title": "Lionelo Agia vs rynek",
        "status": "draft",
    }
    value.update(overrides)
    return value


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompetitiveBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name) / "benchmarks"
        self.products = fixture_products()
        self.patch_root = patch.object(api, "BENCHMARKS_ROOT", self.root)
        self.patch_products = patch.object(api, "load_products", return_value=self.products)
        self.patch_states = patch.object(api, "load_product_states", return_value={})
        self.patch_links = patch.object(api, "read_product_source_links", return_value=[])
        self.patch_root.start(); self.patch_products.start(); self.patch_states.start(); self.patch_links.start()

    def tearDown(self) -> None:
        self.patch_links.stop(); self.patch_states.stop(); self.patch_products.stop(); self.patch_root.stop(); self.temp.cleanup()

    def create(self, body: dict[str, object] | None = None):
        return api.create_competitive_benchmark(api.CompetitiveBenchmarkCreateRequest(**(body or payload())))

    def test_create_read_and_list_manifest(self) -> None:
        manifest = self.create()
        self.assertTrue(manifest["benchmark_id"].startswith("benchmark_"))
        self.assertEqual(manifest["benchmark_type"], "competitive")
        self.assertNotIn("anchor_product_id", manifest)
        self.assertNotIn("participant_product_ids", manifest)
        self.assertEqual(manifest["anchor"]["product_id"], ANCHOR)
        self.assertEqual(manifest["participants"][0]["product_id"], COMPETITOR)
        self.assertEqual(manifest["participant_count"], 1)
        forbidden = {"evidence", "snapshot", "profile", "coverage", "fields", "parameters"}
        self.assertTrue(forbidden.isdisjoint(manifest))

        stored = self.root / manifest["benchmark_id"] / "manifest.json"
        self.assertTrue(stored.is_file())
        self.assertFalse(any(path.suffix == ".tmp" for path in self.root.rglob("*")))

        listed = api.list_competitive_benchmarks()
        self.assertEqual(len(listed), 1)
        api.CompetitiveBenchmarkSummary(**listed[0])
        self.assertEqual(set(listed[0]), {"benchmark_id", "title", "status", "benchmark_group_key", "anchor_product_id", "participant_count", "created_at", "updated_at"})

        detail = api.get_competitive_benchmark(manifest["benchmark_id"])
        api.CompetitiveBenchmarkDetail(**detail)
        self.assertEqual(detail["participants"][0]["product_id"], COMPETITOR)
        self.assertEqual(detail["participants"][0]["source_count"], 0)
        with self.assertRaises(HTTPException) as missing:
            api.get_competitive_benchmark("benchmark_not-a-uuid")
        self.assertEqual(missing.exception.status_code, 404)

    def test_detail_passes_manifest_participants_to_runtime_projection(self) -> None:
        manifest = {**payload(), "benchmark_id": "benchmark_test", "created_at": "", "updated_at": ""}
        captured: dict[str, object] = {}

        def fake_runtime(slug: str, group: str, participant_product_ids=None, **_kwargs):
            captured["ids"] = participant_product_ids
            return ({"status": "ok", "participant_product_ids": list(participant_product_ids or [])}, {"status": "no_data", "median": None, "min": None, "max": None, "seller_count": 0})

        with patch.object(api, "runtime_semantic_benchmark", side_effect=fake_runtime):
            result = api.competitive_benchmark_detail(manifest)
        self.assertEqual(captured["ids"], [COMPETITOR])
        self.assertEqual(result["semantic_benchmark"]["participant_product_ids"], [COMPETITOR])

    def test_internal_detail_exposes_runtime_price_summary(self) -> None:
        expected = {"status": "ok", "median": 110.0, "min": 100.0, "max": 120.0, "seller_count": 2}
        with patch.object(api, "runtime_semantic_benchmark", return_value=({"status": "ok"}, expected)):
            result = api.get_internal_benchmark("light_stroller")
        self.assertEqual(result["price_summary"], expected)

    def test_runtime_competitive_scope_uses_manifest_participant_and_price(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            products = [
                {"product_id": ANCHOR, "brand": "Lionelo", "model": "Agia", "configuration": "2w1", "benchmark_group": "light_stroller"},
                {"product_id": COMPETITOR, "brand": "Bugaboo", "model": "Butterfly 2", "configuration": "2w1", "benchmark_group": "light_stroller"},
                {"product_id": LIONELO_PARTICIPANT, "brand": "Lionelo", "model": "Bess", "configuration": "2w1", "benchmark_group": "light_stroller"},
            ]
            for product in products:
                group_dir = root / "output" / "model_groups" / product["product_id"].replace(":", "_")
                group_dir.mkdir(parents=True)
                (group_dir / "group.json").write_text(__import__("json").dumps({
                    "group_key": product["product_id"], "product_id": product["product_id"],
                    "brand": product["brand"], "model": product["model"], "configuration": "2w1",
                    "benchmark_group": "light_stroller", "sources": [{"seller_id": product["product_id"], "price": 100 if product["product_id"] == COMPETITOR else 999, "observed_at": "2026-01-01"}],
                }), encoding="utf-8")
                (group_dir / "model_state.json").write_text('{"fields":{}}', encoding="utf-8")
            with patch.object(api, "PROJECT_ROOT", root), patch.object(api, "load_products", return_value=products):
                semantic, prices = api.runtime_semantic_benchmark(
                    api.product_slug_for("Lionelo", "Agia", "2w1"), "light_stroller", [COMPETITOR], benchmark_type="competitive"
                )
        self.assertEqual(semantic["participant_product_ids"], [COMPETITOR])
        self.assertEqual({item["seller_id"] for item in prices["observations"]}, {ANCHOR, COMPETITOR})

    def test_internal_detail_aggregates_real_group_prices(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            products = []
            for index, price in enumerate((100, 120, 140), start=1):
                product_id = f"product:lionelo:internal-{index}:2w1"
                product = {"product_id": product_id, "brand": "Lionelo", "model": f"Internal {index}", "configuration": "2w1", "benchmark_group": "compact"}
                products.append(product)
                group_dir = root / "output" / "model_groups" / f"internal-{index}"
                group_dir.mkdir(parents=True)
                (group_dir / "group.json").write_text(__import__("json").dumps({"group_key": product_id, "product_id": product_id, "brand": "Lionelo", "model": product["model"], "configuration": "2w1", "benchmark_group": "compact", "sources": [{"seller_id": f"seller-{index}", "price": price, "observed_at": "2026-01-01"}]}), encoding="utf-8")
                (group_dir / "model_state.json").write_text('{"fields":{}}', encoding="utf-8")
            with patch.object(api, "PROJECT_ROOT", root), patch.object(api, "load_products", return_value=products), patch.object(api, "read_product_source_links", return_value=[]), patch.object(api, "load_product_states", return_value={}):
                result = api.get_internal_benchmark("compact")
        self.assertEqual(result["price_summary"]["median"], 120.0)
        self.assertEqual(result["price_summary"]["min"], 100.0)
        self.assertEqual(result["price_summary"]["max"], 140.0)

    def test_missing_catalog_product_in_manifest_is_controlled_error(self) -> None:
        manifest = self.create()
        stored = self.root / manifest["benchmark_id"] / "manifest.json"
        value = __import__("json").loads(stored.read_text(encoding="utf-8"))
        value["participant_product_ids"] = ["product:missing:none"]
        stored.write_text(__import__("json").dumps(value), encoding="utf-8")
        with self.assertRaises(HTTPException) as rejected:
            api.get_competitive_benchmark(manifest["benchmark_id"])
        self.assertEqual(rejected.exception.status_code, 422)
        self.assertIn("product:missing:none", str(rejected.exception.detail))

    def test_internal_groups_are_dynamic_and_not_written(self) -> None:
        self.assertFalse(self.root.exists())
        listed = api.list_internal_benchmarks()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["benchmark_group_key"], "light_stroller")
        self.assertEqual(listed[0]["participant_count"], 2)
        api.InternalBenchmarkSummary(**listed[0])
        detail = api.get_internal_benchmark("light_stroller")
        api.InternalBenchmarkDetail(**detail)
        self.assertEqual(detail["benchmark_type"], "internal")
        self.assertIsNone(detail["anchor"])
        self.assertIsNotNone(detail["updated_at"])
        self.assertEqual({item["product_id"] for item in detail["participants"]}, {ANCHOR, LIONELO_PARTICIPANT})
        self.assertFalse(self.root.exists())
        with self.assertRaises(HTTPException) as missing:
            api.get_internal_benchmark("standard_stroller")
        self.assertEqual(missing.exception.status_code, 404)

    def test_rejects_invalid_relationships(self) -> None:
        cases = [
            ("anchor_innej_marki", payload(anchor_product_id=COMPETITOR), "musi być produktem marki Lionelo"),
            ("anchor_nieistniejacy", payload(anchor_product_id="product:missing:none"), "Nie istnieje produkt anchor"),
            ("anchor_bez_grupy", payload(anchor_product_id=ANCHOR_NO_GROUP), "nie ma przypisanej grupy"),
            ("uczestnik_lionelo", payload(participant_product_ids=[LIONELO_PARTICIPANT]), "nie może być produktem marki Lionelo"),
            ("inna_grupa", payload(participant_product_ids=[OTHER_GROUP]), "należy do grupy"),
            ("brak_grupy", payload(participant_product_ids=[UNCLASSIFIED]), "nie ma przypisanej grupy"),
            ("nieistniejacy", payload(participant_product_ids=["product:missing:none"]), "Nie istnieje uczestnik"),
            ("duplikat", payload(participant_product_ids=[COMPETITOR, COMPETITOR]), "zduplikowany"),
            ("anchor_jako_uczestnik", payload(participant_product_ids=[ANCHOR]), "Anchor nie może"),
            ("pusta_lista", payload(participant_product_ids=[]), "co najmniej jednego"),
            ("inna_klasa", payload(benchmark_group_key="standard_stroller"), "musi być równy"),
        ]
        for name, body, message in cases:
            with self.subTest(name=name):
                with self.assertRaises(HTTPException) as rejected:
                    self.create(body)
                self.assertEqual(rejected.exception.status_code, 422)
                self.assertIn(message, str(rejected.exception.detail))

    def test_rejects_mismatched_configuration(self) -> None:
        self.products[0]["configuration"] = "2w1"
        self.products[1]["configuration"] = "3w1"
        with self.assertRaises(HTTPException) as rejected:
            self.create()
        self.assertEqual(rejected.exception.status_code, 422)
        self.assertIn("configuration", str(rejected.exception.detail))

    def test_generated_identifier_conflict_returns_409(self) -> None:
        first = self.create()
        generated_uuid = uuid.UUID(first["benchmark_id"].removeprefix("benchmark_"))
        with patch("benchmark_storage.uuid.uuid4", return_value=generated_uuid), self.assertRaises(HTTPException) as conflict:
            self.create()
        self.assertEqual(conflict.exception.status_code, 409)

    def test_catalog_and_research_files_are_not_changed(self) -> None:
        catalog = ROOT / "data" / "catalog" / "products.json"
        states = sorted((ROOT / "output" / "model_groups").glob("*/model_state.json"))
        profiles = sorted((ROOT / "output" / "product_profiles").glob("**/*"))
        catalog_before = file_hash(catalog)
        states_before = {path: file_hash(path) for path in states}
        profiles_before = {path: file_hash(path) for path in profiles if path.is_file()}
        self.create()
        self.assertEqual(file_hash(catalog), catalog_before)
        self.assertEqual({path: file_hash(path) for path in states}, states_before)
        self.assertEqual({path: file_hash(path) for path in profiles if path.is_file()}, profiles_before)
