#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

payload = json.load(sys.stdin)
cwd = Path(payload.get("cwd") or ".").resolve()
try:
    root = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True
    ).strip())
except Exception:
    print(json.dumps({"continue": True}))
    raise SystemExit(0)

active = [p for p in (root / "docs" / "active").iterdir() if p.is_dir()]     if (root / "docs" / "active").exists() else []
if not active:
    print(json.dumps({"continue": True}))
    raise SystemExit(0)

active.sort(key=lambda p: p.stat().st_mtime, reverse=True)
rel = active[0].relative_to(root)
message = (
    f"Before compaction, persist the current implementation state for {rel}. "
    f"Use the dev-docs-update workflow, record branch, commit, dirty files, tests, blockers, and the exact next step."
)
print(json.dumps({"continue": True, "systemMessage": message}))
