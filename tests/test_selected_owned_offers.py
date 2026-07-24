from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_model_research_pipeline import (  # noqa: E402
    REQUIRED_OFFER_SNAPSHOTS,
    materialize_selected_offers,
    prepare_selected_offer_queue,
)


class SelectedOwnedOffersTests(unittest.TestCase):
    def write_csv(self, path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def listing(self, directory: Path) -> Path:
        path = directory / "listing.csv"
        self.write_csv(path, ["offer_id", "title", "canonical_url"], [
            {"offer_id": "reused", "title": "known", "canonical_url": "https://allegro.pl/oferta/reused"},
            {"offer_id": "error", "title": "failed", "canonical_url": "https://allegro.pl/oferta/error"},
            {"offer_id": "new", "title": "new", "canonical_url": "https://allegro.pl/oferta/new"},
            {"offer_id": "unselected", "title": "candidate only", "canonical_url": "https://allegro.pl/oferta/unselected"},
        ])
        return path

    def queue(self, directory: Path) -> Path:
        path = directory / "queue.csv"
        self.write_csv(path, ["offer_id", "status"], [
            {"offer_id": "reused", "status": "fetched"},
            {"offer_id": "error", "status": "error"},
        ])
        return path

    def complete_artifacts(self, pages: Path, offer_id: str) -> None:
        source = pages / offer_id
        source.mkdir(parents=True)
        for filename in REQUIRED_OFFER_SNAPSHOTS:
            (source / filename).write_text("ok", encoding="utf-8")

    def test_selected_known_complete_offer_is_reused_without_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pages = root / "pages"
            self.complete_artifacts(pages, "reused")
            rows = materialize_selected_offers(self.listing(root), root / "selected.csv", {"reused"}, queue_path=self.queue(root), offer_pages_root=pages)
            self.assertEqual(rows[0]["owned_run_status"], "reused")
            self.assertTrue((pages / "reused" / "technical_clean.md").exists())

    def test_selected_known_error_offer_is_scheduled_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = self.queue(root)
            rows = materialize_selected_offers(self.listing(root), root / "selected.csv", {"error"}, queue_path=queue, offer_pages_root=root / "pages")
            self.assertEqual(rows[0]["owned_run_status"], "fetch")
            self.assertEqual(prepare_selected_offer_queue({"error"}, queue), {"error"})
            with queue.open(encoding="utf-8", newline="") as handle:
                statuses = {row["offer_id"]: row["status"] for row in csv.DictReader(handle)}
            self.assertEqual(statuses["error"], "pending")

    def test_selected_new_offer_is_scheduled_for_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = materialize_selected_offers(self.listing(root), root / "selected.csv", {"new"}, queue_path=self.queue(root), offer_pages_root=root / "pages")
            self.assertEqual(rows[0]["owned_run_status"], "fetch")
            self.assertEqual(prepare_selected_offer_queue({"new"}, root / "queue.csv"), set())

    def test_unselected_candidate_does_not_enter_owned_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = materialize_selected_offers(self.listing(root), root / "selected.csv", {"new"}, queue_path=self.queue(root), offer_pages_root=root / "pages")
            self.assertEqual([row["external_offer_id"] for row in rows], ["new"])


if __name__ == "__main__":
    unittest.main()
