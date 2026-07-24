#!/usr/bin/env bash
# One manually initiated, consented AI Product Profile run for Kinderkraft NEBO.
# This script is intentionally not called by any automated FIELDNOTE workflow.
set -euo pipefail

EXPECTED_PAYLOAD_HASH="1a1bdab40ef3fe7566ba20bf50e3abad217b047ed8ef379befd3fe5387331c00"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/fieldnote-api/.env"
PAYLOAD_FILE="${PROJECT_ROOT}/output/product_profile_review/kinderkraft_nebo_preflight/profile_input_payload.json"
VENV_PYTHON="${PROJECT_ROOT}/fieldnote-api/.venv/bin/python"

fail() {
  printf 'NEBO AI profile run stopped: %s\n' "$1" >&2
  exit 1
}

if [[ -x "${VENV_PYTHON}" ]]; then
  PYTHON_BIN="${VENV_PYTHON}"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
else
  fail "Nie znaleziono fieldnote-api/.venv ani aktywnego virtualenv z Pythonem."
fi

[[ -f "${ENV_FILE}" ]] || fail "Brak fieldnote-api/.env."
[[ -f "${PAYLOAD_FILE}" ]] || fail "Brak zatwierdzonego payloadu NEBO."

# Load local configuration without echoing it. The flag may be absent in .env;
# it is explicitly set to 1 below for this manually initiated, single run.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
[[ -n "${OPENAI_API_KEY:-}" ]] || fail "Brak OPENAI_API_KEY w fieldnote-api/.env."
export PRODUCT_PROFILE_AI_ENABLED=1
export PRODUCT_PROFILE_MAX_REQUESTS=1
export PRODUCT_PROFILE_AUTOREGENERATE=0
export FIRECRAWL_DISABLED=1

ACTUAL_HASH="$("${PYTHON_BIN}" - "${PAYLOAD_FILE}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest())
PY
)"
[[ "${ACTUAL_HASH}" == "${EXPECTED_PAYLOAD_HASH}" ]] || fail "Hash payloadu nie odpowiada zatwierdzonemu hashovi."

# Exactly one generator process is started. It has one Responses API call and
# does not retry, regenerate, fetch Firecrawl, or invoke a correction model.
if ! "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/generate_product_profile.py" \
  --product-slug kinderkraft__nebo \
  --allow-openai \
  --max-images 8 \
  --payload-path "${PAYLOAD_FILE}" \
  --expected-payload-hash "${EXPECTED_PAYLOAD_HASH}"; then
  fail "Generator zakończył się błędem. Nie wykonano retry ani nie usunięto artefaktów."
fi

# The repository gate is offline and must not start another OpenAI request.
"${PROJECT_ROOT}/scripts/check_fieldnote.sh"

printf '%s\n' 'Review folder prepared by: scripts/package_product_profile_review.py --product-slug kinderkraft__nebo'
printf '%s\n' 'To create ZIP manually from project root: ditto -c -k --sequesterRsrc --keepParent output/product_profile_review/kinderkraft_nebo output/KINDERKRAFT_NEBO_AI_PROFILE_REVIEW.zip'
