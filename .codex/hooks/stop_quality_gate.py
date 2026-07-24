#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

payload = json.load(sys.stdin)
if payload.get("stop_hook_active"):
    print(json.dumps({
        "continue": True,
        "systemMessage": "Quality gate was already requested once in this turn; inspect any remaining failures before claiming completion.",
    }))
    raise SystemExit(0)

cwd = Path(payload.get("cwd") or ".").resolve()
try:
    root = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True
        ).strip()
    )
except Exception:
    print(json.dumps({"continue": True}))
    raise SystemExit(0)

try:
    changed = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    )
except Exception:
    changed = ""

if not changed.strip():
    print(json.dumps({"continue": True}))
    raise SystemExit(0)

failures: list[str] = []
py_files: list[str] = []
for line in changed.splitlines():
    rel = line[3:].strip()
    if " -> " in rel:
        rel = rel.split(" -> ", 1)[1]
    path = root / rel
    if path.suffix == ".py" and path.exists():
        py_files.append(str(path))

if py_files:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", *py_files],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        failures.append(
            "Python compile failed:\n" + (result.stderr or result.stdout)[-3000:]
        )

if (root / "tsconfig.json").exists() and (root / "node_modules" / ".bin" / "tsc").exists():
    result = subprocess.run(
        [
            str(root / "node_modules" / ".bin" / "tsc"),
            "--noEmit",
            "--pretty",
            "false",
        ],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        failures.append(
            "TypeScript check failed:\n" + (result.stdout or result.stderr)[-3000:]
        )

if failures:
    reason = (
        "Lightweight quality gate failed. Fix these issues before finishing:\n\n"
        + "\n\n".join(failures)
    )
    print(json.dumps({"decision": "block", "reason": reason}))
else:
    print(json.dumps({"continue": True}))
