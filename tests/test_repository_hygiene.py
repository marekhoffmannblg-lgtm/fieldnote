"""Offline guardrails for files that may enter the Git index."""

from __future__ import annotations

import re
import subprocess
import tempfile
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


def tracked_paths(root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def indexed_text(relative: str, root: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", "show", f":{relative}"], cwd=root, check=True, capture_output=True
    )
    return result.stdout.decode("utf-8")


def secret_violations(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    for relative in tracked_paths(root):
        try:
            content = indexed_text(relative, root)
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            violations.append(relative)
    return violations


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
        violations = secret_violations()
        self.assertEqual(violations, [], f"secret-shaped values in tracked files: {violations}")

    def test_staged_secret_is_detected_when_worktree_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked = root / "example.env"
            staged_secret = "sk-" + "abcdefghijklmnopqrst"
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            tracked.write_text(f"OPENAI_API_KEY={staged_secret}\\n", encoding="utf-8")
            subprocess.run(["git", "add", "example.env"], cwd=root, check=True)
            tracked.write_text("OPENAI_API_KEY=\\n", encoding="utf-8")

            self.assertEqual(secret_violations(root), ["example.env"])

    def test_ci_offline_gate_installs_api_dependencies(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "python -m pip install -r requirements.txt -r fieldnote-api/requirements.txt",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
