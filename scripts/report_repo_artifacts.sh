#!/usr/bin/env bash
# Read-only repository hygiene report. It never removes user files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[FIELDNOTE] Large working artifacts (>= 10 MB)"
if command -v find >/dev/null 2>&1; then
  find . -type f -size +10M -not -path './.git/*' -print 2>/dev/null || true
fi

echo
echo "[FIELDNOTE] Ignored local artifacts present"
for path in fieldnote-api/.env fieldnote-api/.venv fieldnote-frontend/node_modules fieldnote-frontend/dist; do
  if [[ -e "$path" ]]; then
    echo "$path"
  fi
done

echo
echo "[FIELDNOTE] Temporary run work directories"
if [[ -d output/runs ]]; then
  find output/runs -type d -name work -print 2>/dev/null || true
fi
