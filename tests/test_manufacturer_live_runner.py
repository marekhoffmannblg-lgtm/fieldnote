from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_manufacturer_pipeline_live import RequestCounters, attempt_provider, parse_args, preflight  # noqa: E402


class LiveRunnerPreflightTests(unittest.TestCase):
    def args(self, *items: str):
        return parse_args(["--brand", "Kinderkraft", "--model", "NEBO", "--max-sources", "1", *items])

    def test_missing_network_consent_is_explicit(self):
        result = preflight(self.args("--no-openai"))
        self.assertFalse(result["preflight_passed"])
        self.assertIn("CONSENT_FLAG_MISSING", result["blocking_reason"])

    def test_missing_openai_consent_is_explicit(self):
        result = preflight(self.args("--allow-network"))
        self.assertFalse(result["preflight_passed"])
        self.assertIn("--allow-openai", result["blocking_reason"])

    def test_no_openai_does_not_require_openai_key(self):
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            result = preflight(self.args("--allow-network", "--no-openai", "--dry-preflight"))
            self.assertNotIn("OPENAI_API_KEY", result["blocking_reason"])
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old

    def test_limits_are_exactly_one(self):
        result = preflight(parse_args(["--brand", "Kinderkraft", "--model", "NEBO", "--max-sources", "2", "--allow-network", "--allow-openai"]))
        self.assertFalse(result["preflight_passed"])
        self.assertIn("max-sources", result["blocking_reason"])

    def test_unsupported_brand_is_explicit(self):
        result = preflight(parse_args(["--brand", "Unknown", "--model", "X", "--max-sources", "1", "--allow-network", "--allow-openai"]))
        self.assertIn("UNSUPPORTED_BRAND", result["blocking_reason"])

    def test_missing_firecrawl_key_is_configuration_error(self):
        old = os.environ.pop("FIRECRAWL_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "fieldnote-api").mkdir()
                (root / "fieldnote-api" / ".env").write_text("OPENAI_API_KEY=present\n", encoding="utf-8")
                result = preflight(self.args("--allow-network", "--allow-openai"), root=root)
        finally:
            if old is not None:
                os.environ["FIRECRAWL_API_KEY"] = old
        self.assertIn("FIRECRAWL_API_KEY", result["blocking_reason"])

    def test_env_path_does_not_depend_on_current_directory(self):
        result = preflight(self.args("--allow-network", "--allow-openai", "--dry-preflight"))
        self.assertTrue(result["env_path"].endswith("fieldnote-api/.env"))

    def test_attempt_counter_is_incremented_before_provider(self):
        counters = RequestCounters()
        observed = []
        def operation():
            observed.append(counters.firecrawl_requests_attempted)
            return "ok"
        self.assertEqual(attempt_provider(counters, "firecrawl", operation), "ok")
        self.assertEqual(observed, [1])
        self.assertEqual(counters.firecrawl_requests_succeeded, 1)

    def test_provider_error_preserves_attempt_and_reason(self):
        counters = RequestCounters()
        with self.assertRaisesRegex(RuntimeError, "provider"):
            attempt_provider(counters, "openai", lambda: (_ for _ in ()).throw(RuntimeError("provider")))
        self.assertEqual(counters.openai_requests_attempted, 1)
        self.assertEqual(counters.openai_requests_failed, 1)


if __name__ == "__main__":
    unittest.main()
