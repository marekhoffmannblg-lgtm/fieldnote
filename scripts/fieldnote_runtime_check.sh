#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$ROOT/fieldnote-api/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="python3"
COMMAND="${1:-full}"
case "$COMMAND" in imports|pipeline|locks|images|relations|api|full) ;; *) echo "Usage: $0 {imports|pipeline|locks|images|relations|api|full}" >&2; exit 2;; esac
OUT="$ROOT/output/_FIELDNOTE_TEST_SESSION"
mkdir -p "$OUT"
LOG="$OUT/runtime_${COMMAND}.log"
env -u OPENAI_API_KEY -u FIRECRAWL_API_KEY FIELDNOTE_SKIP_STARTUP_RECOVERY=1 "$PYTHON_BIN" "$ROOT/scripts/fieldnote_runtime_check.py" "$COMMAND" >"$LOG" 2>&1 || { cat "$LOG"; exit 1; }
cat "$LOG"
