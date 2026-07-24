#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


def git_root(cwd: Path) -> Path:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True
        ).strip()
        return Path(value)
    except Exception:
        return cwd


payload = json.load(sys.stdin)
root = git_root(Path(payload.get("cwd") or ".").resolve())

plans = sorted(
    (root / "docs" / "plans").glob("*.md"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
) if (root / "docs" / "plans").exists() else []
reqs = sorted(
    (root / "docs" / "brainstorms").glob("*.md"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
) if (root / "docs" / "brainstorms").exists() else []
active_dirs = [
    p for p in (root / "docs" / "active").iterdir()
    if p.is_dir()
] if (root / "docs" / "active").exists() else []
active_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

parts = ["Read AGENTS.md before editing."]
if (root / "docs" / "CONCEPTS.md").exists():
    parts.append("Use docs/CONCEPTS.md for domain terminology.")
if active_dirs:
    task = active_dirs[0]
    parts.append(
        f"Active task candidate: {task.relative_to(root)}. Read its plan, context, tasks, and latest review before continuing."
    )
if reqs:
    parts.append(f"Latest requirements candidate: {reqs[0].relative_to(root)}.")
if plans:
    parts.append(f"Latest technical plan candidate: {plans[0].relative_to(root)}.")

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": " ".join(parts),
    }
}))
