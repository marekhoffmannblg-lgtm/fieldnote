"""Offline guardrails for files that may enter the Git index."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_LOCAL_PLACEHOLDERS = {
    "input/firecrawl_listings/.gitkeep",
    "output/.gitkeep",
    "data/catalog/.gitkeep",
    "fieldnote-api/runs/.gitkeep",
    "fieldnote-frontend/src/data/generated/.gitkeep",
}
FORBIDDEN_PREFIXES = (
    "input/",
    "output/",
    "data/catalog/",
    "fieldnote-api/runs/",
    "fieldnote-frontend/src/data/generated/",
)
FORBIDDEN_PARTS = {"node_modules", ".venv", "venv", ".pnpm-store", ".vite", "__pycache__"}
FORBIDDEN_SUFFIXES = (".zip", ".sqlite", ".sqlite3", ".db", ".pyc", ".pyo")
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\bfc-(?:[A-Za-z0-9_-]{20,})\b", re.IGNORECASE),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),
)


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


class RepositoryHygieneTests(unittest.TestCase):
    def test_tracked_paths_exclude_local_artifacts_and_environment_files(self) -> None:
        violations: list[str] = []
        for path in tracked_paths():
            parts = Path(path).parts
            if Path(path).name.startswith(".env") and not path.endswith(".env.example"):
                violations.append(path)
                continue
            if path in ALLOWED_LOCAL_PLACEHOLDERS:
                continue
            if path.startswith(FORBIDDEN_PREFIXES):
                violations.append(path)
                continue
            if any(part in FORBIDDEN_PARTS for part in parts) or path.endswith(FORBIDDEN_SUFFIXES):
                violations.append(path)
        self.assertEqual(violations, [], f"tracked local artifacts: {violations}")

    def test_tracked_text_does_not_contain_secret_shaped_values(self) -> None:
        violations: list[str] = []
        for relative in tracked_paths():
            path = ROOT / relative
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                violations.append(relative)
        self.assertEqual(violations, [], f"secret-shaped values in tracked files: {violations}")


if __name__ == "__main__":
    unittest.main()
