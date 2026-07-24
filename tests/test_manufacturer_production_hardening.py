"""Offline regression checks for the production manufacturer lifecycle."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_manufacturer_pipeline_live import (  # noqa: E402
    LiveRunnerError,
    STAGE_NAMES,
    StageTracker,
    api_verification,
)
from source_lifecycle import read_product_source_links, read_source_records  # noqa: E402


class ManufacturerProductionHardeningTests(unittest.TestCase):
    def test_stage_tracker_has_stable_identity_for_every_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tracker = StageTracker(Path(directory), run_id="run-1", source_id="manufacturer:test")
            self.assertEqual(set(tracker.payload["stages"]), set(STAGE_NAMES))
            self.assertEqual(tracker.payload["stages"]["fetch"]["id"], "run-1:fetch")
            with self.assertRaisesRegex(LiveRunnerError, "lifecycle"):
                tracker.succeed()

    def test_cancel_marks_only_the_active_stage_without_committing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tracker = StageTracker(Path(directory), run_id="run-cancel", source_id="manufacturer:test")
            tracker.start("fetch")
            tracker.cancel(tracker.active_stage())
            self.assertEqual(tracker.payload["status"], "cancelled")
            self.assertEqual(tracker.payload["stages"]["fetch"]["status"], "cancelled")
            self.assertEqual(tracker.payload["stages"]["lifecycle_commit"]["status"], "pending")

    def test_cache_resume_never_attempts_network_or_openai(self) -> None:
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "check_manufacturer_pipeline_live.py"),
                "--brand", "Kinderkraft", "--model", "NEBO", "--max-sources", "1",
                "--resume", "--no-fetch", "--no-openai",
            ],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("firecrawl_requests_attempted=0", completed.stdout)
        self.assertIn("openai_requests_attempted=0", completed.stdout)
        self.assertIn("terminal_status=success", completed.stdout)

    def test_orfeo_source_link_and_api_artifacts_are_idempotent(self) -> None:
        source_id = "manufacturer:cybex:52c8810b9c29e1cc"
        product_slug = "cybex__orfeo"
        self.assertEqual(sum(item.get("source_id") == source_id for item in read_source_records()), 1)
        self.assertEqual(sum(item.get("link_id") == f"{product_slug}|{source_id}" for item in read_product_source_links()), 1)
        self.assertTrue(api_verification(product_slug, source_id))

    def test_identity_mismatch_cannot_be_an_api_success(self) -> None:
        self.assertFalse(api_verification("cybex__orfeo", "manufacturer:cybex:not-orfeo"))


if __name__ == "__main__":
    unittest.main()
