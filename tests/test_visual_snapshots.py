"""Offline regression coverage for the shared visual source layer."""

from __future__ import annotations

import json
import sys
import unittest
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from visual_snapshots import (  # noqa: E402
    artifact_id,
    artifact_relative,
    extract_visual_context,
    read_jsonl,
    redact_json_payload,
    source_visual_paths,
)


class VisualSnapshotsTests(unittest.TestCase):
    NEBO = "manufacturer:kinderkraft:4c4e9b6f5353861e"
    ORFEO = "manufacturer:cybex:52c8810b9c29e1cc"
    ALLEGRO = "allegro:18405722631"

    def backfill(self, source_id: str, slug: str) -> tuple[dict, list[dict], list[dict]]:
        result = extract_visual_context(source_id, product_slug=slug, refresh=True)
        snapshot_path, blocks_path, media_path = source_visual_paths(source_id, slug)
        self.assertIsNotNone(snapshot_path)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        return snapshot, read_jsonl(blocks_path), read_jsonl(media_path)

    def test_nebo_video_and_same_card_text(self) -> None:
        snapshot, blocks, media = self.backfill(self.NEBO, "kinderkraft__nebo")
        self.assertEqual(snapshot["capture_status"], "partial")
        self.assertTrue(any(item["media_type"] == "video" and ".webm" in str(item["original_url"]) for item in media))
        self.assertTrue(any(block.get("heading") and block.get("body_text") for block in blocks))
        # Desktop/mobile clones collapse to six semantic feature cards.
        self.assertEqual(len(blocks), 6)

    def test_orfeo_feature_and_recommendations_excluded(self) -> None:
        _snapshot, blocks, _media = self.backfill(self.ORFEO, "cybex__orfeo")
        luggage = next((item for item in blocks if item.get("heading") == "Hand Luggage Compatible"), None)
        self.assertIsNotNone(luggage)
        self.assertIn("flight", str(luggage.get("body_text", "")).casefold())
        self.assertFalse(any(item.get("region") == "recommendation" for item in blocks))

    def test_allegro_is_limited_to_gallery_and_description(self) -> None:
        snapshot, blocks, media = self.backfill(self.ALLEGRO, "kinderkraft__nebo")
        self.assertEqual(snapshot["capture_status"], "partial")
        self.assertLessEqual(len(media), 12)
        self.assertTrue({item.get("region") for item in blocks}.issubset({"gallery", "description"}))
        self.assertTrue(any(item.get("region") == "description" for item in blocks))

    def test_resume_and_crop_rules(self) -> None:
        first = extract_visual_context(self.NEBO, product_slug="kinderkraft__nebo", refresh=True)
        second = extract_visual_context(self.NEBO, product_slug="kinderkraft__nebo")
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(first["blocks"], second["blocks"])
        _snapshot, blocks, _media = self.backfill(self.NEBO, "kinderkraft__nebo")
        self.assertTrue(all(item.get("section_screenshot_path") is None and item.get("bounding_box") is None for item in blocks))

    def test_artifact_ids_are_relative_and_redacted_json_stays_valid(self) -> None:
        encoded = artifact_id("input/firecrawl_offer_pages/1/visual/full_page.webp")
        self.assertEqual(artifact_relative(encoded), "input/firecrawl_offer_pages/1/visual/full_page.webp")
        self.assertIsNone(artifact_relative(artifact_id("../../etc/passwd")))
        redacted = redact_json_payload({"authorization": "Bearer sk-example-secret", "nested": ["fc-secret-token"]})
        self.assertNotIn("sk-example-secret", json.dumps(redacted))
        self.assertIsInstance(json.loads(json.dumps(redacted)), dict)

    @unittest.skipUnless(importlib.util.find_spec("fastapi") is not None, "FastAPI jest instalowane w środowisku fieldnote-api.")
    def test_api_payload_hides_paths_and_rejects_traversal(self) -> None:
        api_root = ROOT / "fieldnote-api"
        if str(api_root) not in sys.path:
            sys.path.insert(0, str(api_root))
        import app as api  # Local API module; no server and no network involved.
        payload, blocks, media = api.visual_source_payload(self.NEBO)
        self.assertNotIn("full_page_screenshot_path", payload)
        self.assertTrue(all("section_screenshot_path" not in block for block in blocks))
        self.assertTrue(all("local_path" not in item for item in media))
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            api.visual_artifact(artifact_id("../../etc/passwd"))


if __name__ == "__main__":
    unittest.main()
